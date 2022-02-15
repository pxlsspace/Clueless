import numpy as np
import asyncio
import re
import copy
from PIL import Image
from numba import jit
from urllib.parse import parse_qs, urlparse
from io import BytesIO

from utils.utils import get_content
from utils.setup import stats, db_templates
from utils.pxls.template import get_rgba_palette, reduce


class Template():
    def __init__(self, url: str, stylized_url: str, title: str, image_array: np.ndarray, ox: int, oy: int, canvas_code) -> None:
        # template metadata
        self.url = url
        self.stylized_url = stylized_url
        self.title = title
        self.ox = ox
        self.oy = oy
        self.canvas_code = canvas_code
        # used for the template tracker
        self.owner_id = None
        self.hidden = None
        self.name = None

        # template image and array
        self.image_array = image_array  # array of RGBA
        self.palettized_array: np.ndarray = reduce(image_array, get_rgba_palette())  # array of palette indexes

        # template size and dimensions
        self.width = self.image_array.shape[1]
        self.height = self.image_array.shape[0]
        self.total_size = int(np.sum(self.image_array[:, :, 3] == 255))
        self.placeable_mask = self.make_placeable_mask()
        self.total_placeable = int(np.sum(self.placeable_mask))

        # progress (init with self.update_progress())
        self.placed_mask = None
        self.current_progress = None

    def make_placeable_mask(self) -> np.ndarray:
        """Make a mask of the template shape where the placeable pixels are True."""
        # get the placemap cropped to the template size
        cropped_placemap = self.crop_array_to_template(stats.placemap_array)
        # create a mask with all the non-transparent pixels on the template image (True = non-transparent)
        placeable_mask = self.palettized_array != 255
        # exclude pixels outside of the placemap
        placeable_mask[cropped_placemap == 255] = False
        return placeable_mask

    def make_placed_mask(self) -> np.ndarray:
        """Make a mask of the template shape where the correct pixels are True."""
        # get the current board cropped to the template size
        cropped_board = self.crop_array_to_template(stats.board_array)
        # create a mask with the pixels of the template matching the board
        placed_mask = self.palettized_array == cropped_board
        # exclude the pixels outside of the placemap
        placed_mask[~self.placeable_mask] = False
        return placed_mask

    def update_progress(self) -> int:
        """Update the mask with the correct pixels and the number of correct pixels."""
        self.placed_mask = self.make_placed_mask()
        self.current_progress = int(np.sum(self.placed_mask))
        return self.current_progress

    def crop_array_to_template(self, array: np.ndarray) -> np.ndarray:
        """Crop an array to fit in the template bounds
        (used to crop the board and placemap to the template size for previews and such)
        :param array: a palettized numpy array of indexes"""
        # deal with out of bounds coords:
        # to do that we copy the part of the array matching the template area
        # and we paste it on a new array with the template size at the correct coords
        y0 = min(max(0, self.oy), array.shape[0])
        y1 = max(0, min(array.shape[0], self.oy + self.height))
        x0 = min(max(0, self.ox), array.shape[1])
        x1 = max(0, min(array.shape[1], self.ox + self.width))
        _cropped_array = array[y0:y1, x0:x1].copy()
        cropped_array = np.full_like(self.palettized_array, 255)
        cropped_array[y0 - self.oy : y1 - self.oy, x0 - self.ox : x1 - self.ox] = _cropped_array

        return cropped_array

    def get_progress_image(self, opacity=0.65) -> Image.Image:
        """
        Get an image with the canvas progress colored as such:
        - Green = correct
        - Red = incorrect
        - Blue = not placeable
        - Transparent = outside of the template

        If the `opacity` is < 1, layer this progress image with the chosen opacity
        """
        if self.placed_mask is None:
            self.update_progress()
        progress_array = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        progress_array[self.placed_mask] = [0, 255, 0, 255 * opacity]  # correct pixels = green
        progress_array[~self.placed_mask] = [255, 0, 0, 255 * opacity]  # incorrect pixels = red
        progress_array[~self.placeable_mask] = [0, 0, 255, 255]  # not placeable = blue
        progress_array[self.palettized_array == 255] = [0, 0, 0, 0]  # outside of the template = transparent
        progress_image = Image.fromarray(progress_array)

        # layer the board under the progress image if the progress opacity is less than 1
        if opacity < 1:
            cropped_board = self.crop_array_to_template(stats.board_array)
            # remove the pixels outside of the template visible pixels area
            cropped_board[self.palettized_array == 255] = 255
            board_image = Image.fromarray(stats.palettize_array(cropped_board))
            res_image = Image.new("RGBA", board_image.size)
            res_image = Image.alpha_composite(res_image, board_image)
            res_image = Image.alpha_composite(res_image, progress_image)
        else:
            res_image = progress_image

        return res_image


class TemplateManager():
    """A low level object with a list of tracked templates"""
    def __init__(self) -> None:
        self.list: list[Template] = []
        self.bot_owner_id = None

    def check_duplicate_image(self, template: Template):
        """Check if there is already a template with the same image.

        Return the template if it is found or None."""
        if template.hidden:
            # check the private templates with the same owner and image
            list_to_search = self.get_hidden_templates(template.owner_id)
        else:
            # check the public templates with the same image
            list_to_search = self.get_all_public_templates()
        for t in list_to_search:
            if (
                template.palettized_array.shape == t.palettized_array.shape
                and (template.palettized_array == t.palettized_array).all()
            ):
                return t
        return None

    def check_valid_name(self, name: str):
        """Check if a name is valid:
        - if it's only alphanumeric chars or '-' or '_'.
        - between 2 and 40 characters

        Raise ValueError if invalid name or return the name"""
        if not re.match(r"^[A-Za-z0-9_-]*$", name):
            raise ValueError("The template name can only contain letters, numbers, hyphens (`-`) and underscores (`_`).")
        if len(name) < 2 or len(name) > 40:
            raise ValueError("The template name must be between 2 and 40 characters.")
        return name.lower()

    async def save(self, template: Template, name: str, owner_id: int, hidden: bool = False):
        """Save the template:
        - as a template object in the tracked_templates list
        - as a database entry in the database

        Throw an error:
        - if there is a template with the same name
        - if there is a template with the same image"""

        template.name = name.lower()
        template.owner_id = owner_id
        template.hidden = hidden

        # check on the name
        template.name = self.check_valid_name(template.name)

        # check duplicate template names
        same_name_template = self.get_template(template.name, template.owner_id, template.hidden)
        if same_name_template:
            raise ValueError(f"There is already a template with the name `{template.name}`.")

        # check duplicate images
        same_image_template = self.check_duplicate_image(template)
        if same_image_template:
            raise ValueError(f"There is already a template with the same image named `{same_image_template.name}`.")

        # save in db
        await db_templates.create_template(template)
        # save in list
        self.list.append(template)

    def get_template(self, name, owner_id=None, hidden=False):
        """Get a template from its name, get the owner's hidden Template if hidden is True,
        Return None if not found."""
        for temp in self.list:
            if temp.name == name.lower():
                if hidden:
                    if temp.hidden and temp.owner_id == owner_id:
                        return temp
                else:
                    if not temp.hidden:
                        return temp
        return None

    async def delete_template(self, name, command_user_id, hidden):
        temp = self.get_template(name.lower(), command_user_id, hidden)
        if not temp:
            raise ValueError(f"No template named `{name}` found.")
        if temp.owner_id != command_user_id and command_user_id != self.bot_owner_id:
            raise ValueError("You cannot delete a template that you don't own.")

        await db_templates.delete_template(temp)
        self.list.remove(temp)

    async def update_template(self, current_name, command_user_id, new_url=None, new_name=None, new_owner_id=None):
        current_name = current_name.lower()
        old_temp = self.get_template(current_name, command_user_id, False)
        if not old_temp:
            raise ValueError(f"No template named `{current_name}` found.")
        if old_temp.owner_id != command_user_id and command_user_id != self.bot_owner_id:
            raise ValueError("You cannot edit a template that you don't own.")

        if new_url:
            new_temp = await get_template_from_url(new_url)
            if new_temp.total_placeable == 0:
                raise ValueError("The template seems to be outside the canvas, make sure it's correctly positioned.")
            temp_same_image = self.check_duplicate_image(new_temp)
            if temp_same_image:
                raise ValueError(f"There is already a template with the same image named `{temp_same_image.name}`.")
            new_temp.name = old_temp.name
            new_temp.owner_id = old_temp.owner_id
            new_temp.hidden = old_temp.hidden
        else:
            new_temp = copy.deepcopy(old_temp)

        if new_name:
            # check valid name (this raises a ValueError if the name isn't valid)
            new_name = self.check_valid_name(new_name)
            # check duplicate name
            temp_with_same_name = self.get_template(new_name)
            if temp_with_same_name:
                raise ValueError(f"There is already a template with the name `{new_name}`.")
            new_temp.name = new_name
        if new_owner_id:
            new_temp.owner_id = new_owner_id
        new_temp.hidden = False
        if not await db_templates.update_template(old_temp, new_temp.url, new_temp.name, new_temp.owner_id):
            raise ValueError("There was an error while updating the template.")
        self.list.remove(old_temp)
        self.list.append(new_temp)

    def get_all_public_templates(self):
        return [t for t in self.list if not t.hidden]

    def get_hidden_templates(self, owner_id):
        return [t for t in self.list if t.hidden and t.owner_id == owner_id]

    async def load_all_templates(self):
        import time
        start = time.time()
        canvas_code = await stats.get_canvas_code()
        db_list = await db_templates.get_all_templates(canvas_code)
        count = 0
        for db_temp in db_list:
            name = db_temp["name"]
            owner_id = db_temp["owner_id"]
            hidden = db_temp["hidden"]
            url = db_temp["url"]
            try:
                temp = await get_template_from_url(url)
                temp.name = name
                temp.owner_id = int(owner_id)
                temp.hidden = bool(hidden)
                temp.canvas_code = canvas_code
                self.list.append(temp)
                count += 1
            except Exception as e:
                print("Failed to load template {}: {}".format(name, e))
        end = time.time()
        print(f"{count}/{len(db_list)} Templates loaded (time: {round(end-start, 2)}s)")


@jit(nopython=True)
def fast_detemplatize(array, true_height, true_width, block_size):

    result = np.zeros((true_height, true_width, 4), dtype=np.uint8)

    for y in range(true_height):
        for x in range(true_width):
            for j in range(block_size):
                for i in range(block_size):
                    py = y * block_size + j
                    px = x * block_size + i
                    alpha = array[py, px, 3]
                    if alpha > 128:
                        result[y, x] = array[py, px]
                        result[y, x, 3] = 255
                        break
                # to break out of the double loop
                else:
                    continue
                break
    return result


def detemplatize(img_raw: np.ndarray, true_width: int) -> np.ndarray:
    """
    Convert a styled template image back to its original version.
    """
    if true_width <= 0 or img_raw.shape[1] // true_width == 1:  # Nothing to do :D
        return img_raw
    block_size = img_raw.shape[1] // true_width
    true_height = img_raw.shape[0] // block_size
    img_array = np.array(img_raw, dtype=np.uint8)
    img = fast_detemplatize(img_array, true_height, true_width, block_size)
    return img


def parse_template(template_url: str):
    """Get the parameters from a template URL, return `None` if the template is invalid"""
    for e in ["http", "://", "template", "tw", "ox", "oy"]:
        if e not in template_url:
            return None
    parsed_template = urlparse(template_url)
    params = parse_qs(parsed_template.fragment)
    for e in ["template", "tw", "ox", "oy"]:
        if e not in params.keys():
            return None
    # because 'parse_qs()' puts the parameters in arrays
    for k in params.keys():
        params[k] = params[k][0]
    return params


async def get_template_from_url(template_url: str) -> Template:
    """Make a Template object from a template URL"""
    params = parse_template(template_url)

    if params is None:
        raise ValueError("The template URL is invalid.")

    image_url = params["template"]
    true_width = int(params["tw"])

    try:
        image_bytes = await get_content(image_url, "image")
    except Exception:
        raise ValueError("Couldn't download the template image.")
    canvas_code = await stats.get_canvas_code()

    def _get_template():
        template_image = Image.open(BytesIO(image_bytes))
        if template_image.mode != "RGBA":
            template_image = template_image.convert("RGBA")
        template_array = np.array(template_image)

        detemp_array = detemplatize(template_array, true_width)
        ox = int(params["ox"])
        oy = int(params["oy"])
        return Template(template_url, image_url, params.get("title"), detemp_array, ox, oy, canvas_code)

    loop = asyncio.get_running_loop()
    # run this part of the code in executor to make it not blocking
    template = await loop.run_in_executor(None, _get_template)
    return template
