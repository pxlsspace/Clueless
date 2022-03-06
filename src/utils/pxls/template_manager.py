import sqlite3
import numpy as np
import asyncio
import re
import copy
import time
import urllib.parse
import disnake
from datetime import datetime, timedelta
from PIL import Image
from numba import jit
from urllib.parse import parse_qs, urlparse
from io import BytesIO
from cogs.pixel_art.highlight import highlight_image
from utils.font.font_manager import PixelText
from utils.image.gif_saver import save_transparent_gif
from utils.time_converter import round_minutes_down, td_format

from utils.utils import get_content
from utils.setup import stats, db_templates
from utils.pxls.template import get_rgba_palette, reduce
from utils.log import get_logger

logger = get_logger("template_manager")
tracker_logger = get_logger("template_tracker", file="templates.log", in_console=False)


class Template:
    def __init__(
        self,
        url: str,
        stylized_url: str,
        title: str,
        image_array: np.ndarray,
        ox: int,
        oy: int,
        canvas_code,
    ) -> None:
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
        self.palettized_array: np.ndarray = reduce(
            image_array, get_rgba_palette()
        )  # array of palette indexes

        # template size and dimensions
        self.width = self.palettized_array.shape[1]
        self.height = self.palettized_array.shape[0]
        self.total_size = int(np.sum(self.palettized_array != 255))
        self.placeable_mask = self.make_placeable_mask()
        self.total_placeable = int(np.sum(self.placeable_mask))

        # progress (init with self.update_progress())
        self.placed_mask = None
        self.current_progress = None

    def get_array(self) -> np.ndarray:
        """Return the combo image as an array of RGB colors"""
        return stats.palettize_array(self.palettized_array)

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
        cropped_array[
            y0 - self.oy : y1 - self.oy, x0 - self.ox : x1 - self.ox
        ] = _cropped_array

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
        # correct pixels = green
        progress_array[self.placed_mask] = [0, 255, 0, 255 * opacity]
        # incorrect pixels = red
        progress_array[~self.placed_mask] = [255, 0, 0, 255 * opacity]
        # not placeable = blue
        progress_array[~self.placeable_mask] = [0, 0, 255, 255]
        # outside of the template = transparent
        progress_array[self.palettized_array == 255] = [0, 0, 0, 0]
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

    async def get_progress_at(self, dt: datetime):
        """Get the template at a given datetime
        (or None if the template doesnt have data)"""
        progress = await db_templates.get_template_progress(self, dt)
        if progress:
            return progress["datetime"], progress["progress"]
        else:
            return None, None

    def get_virgin_abuse(self):
        """Return the number of correct pixels that are also virgin pixels"""
        template_virginmap = self.crop_array_to_template(stats.virginmap_array)
        abuse_mask = np.logical_and(template_virginmap, self.placed_mask)
        return int(np.sum(abuse_mask))

    async def get_eta(self, as_string=True):
        now = round_minutes_down(datetime.utcnow())
        td = timedelta(days=7)
        old_datetime, old_progress = await self.get_progress_at(now - td)
        now_datetime, now_progress = await self.get_progress_at(now)
        if not old_progress or not now_progress:
            return None

        diff_pixels = now_progress - old_progress
        diff_time = now_datetime - old_datetime
        togo = self.total_placeable - now_progress
        if togo == 0:
            return "done" if as_string else 0
        if diff_time == timedelta(0):
            return None
        speed = diff_pixels / (diff_time / timedelta(hours=1))
        if speed == 0:
            return "Never" if as_string else None
        eta = togo / speed
        if eta <= 0:
            eta = now_progress / speed
            if as_string:
                return "-" + td_format(
                    timedelta(hours=-eta),
                    short_format=True,
                    hide_seconds=True,
                    max_unit="day",
                )
            else:
                return timedelta(hours=eta)
        if as_string:
            return td_format(
                timedelta(hours=eta), short_format=True, hide_seconds=True, max_unit="day"
            )
        else:
            return timedelta(hours=eta)

    def generate_url(self, template_image_url=None, default_scale=4, open_on_togo=False):
        """Generate the template URL

        Parameters
        ----------
        template_image_url: the image to use for the template (use the Template.stylized_image if None)
        scale: the scale at which to display the template (if open_on_togo is False)
        open_on_togo: open the template zoomed on an inccorect pixel"""
        template_image_url = template_image_url or self.stylized_url
        template_title = f"&title={urllib.parse.quote(self.title)}" if self.title else ""

        # coords
        x = y = None
        if open_on_togo:
            # open on the pixels to place
            (x, y) = self.find_coords()
            scale = 40

        if x is None or y is None:
            # open on the center of the template
            x = self.ox + self.width // 2
            y = self.oy + self.height // 2
            scale = default_scale

        template_url = "https://pxls.space/#x={}&y={}&scale={}&template={}&ox={}&oy={}&tw={}&oo=1{}".format(
            x,
            y,
            scale,
            urllib.parse.quote(template_image_url),
            self.ox,
            self.oy,
            self.width,
            template_title,
        )
        return template_url

    def find_coords(self, chunk_size=10):
        """Find the coordinates at which there are the most pixels to placed

        chunk_size: the size of the chunks we're dividing the template into"""

        def to_chunks(arr, nrows, ncols):
            """divide arr into chunks of size nrows x ncols"""
            h, w = arr.shape
            assert h % nrows == 0, f"{h} rows is not evenly divisible by {nrows}"
            assert w % ncols == 0, f"{w} cols is not evenly divisible by {ncols}"
            return (
                arr.reshape(h // nrows, nrows, -1, ncols)
                .swapaxes(1, 2)
                .reshape(-1, nrows, ncols)
            )

        # mask with all the pixels to place
        togo_mask = np.logical_and(~self.placed_mask, self.placeable_mask)

        # pad the mask to be dividable by the block size
        right_pad = chunk_size - togo_mask.shape[1] % chunk_size
        bottom_pad = chunk_size - togo_mask.shape[0] % chunk_size
        togo_mask = np.pad(togo_mask, [(0, bottom_pad), (0, right_pad)])

        # convert to a list of chunk size sub-arrays
        chunked_mask = to_chunks(togo_mask, chunk_size, chunk_size)

        # find the chunk with the most pixels to place
        max_index = fast_max_chunk(chunked_mask)
        if max_index == -1:
            # there are no chunk with pixels to placed
            return (None, None)

        # convert the chunk index to coords in the the template
        highest_chunk_coords = np.unravel_index(
            max_index, [c // chunk_size for c in togo_mask.shape]
        )

        # get the coordinate at the center of the block
        coords_in_template = [
            (c * chunk_size) + chunk_size // 2 for c in highest_chunk_coords
        ]

        # add the template ox and oy to get the final coords in the canvas
        coords_in_canvas = (
            coords_in_template[1] + self.ox,
            coords_in_template[0] + self.oy,
        )
        return coords_in_canvas


class Combo(Template):
    """Extension of template to contain a combo template"""

    def __init__(
        self,
        title: str,
        palettized_array: np.ndarray,
        ox: int,
        oy: int,
        name,
        bot_id,
        canvas_code,
    ) -> None:
        # template metadata
        self.title = title
        self.ox = ox
        self.oy = oy
        self.canvas_code = canvas_code
        self.url = None
        self.stylized_url = None

        # used for the template tracker
        self.owner_id = bot_id
        self.hidden = False
        self.name = name

        self.palettized_array: np.ndarray = palettized_array

        # template size and dimensions
        self.width = self.palettized_array.shape[1]
        self.height = self.palettized_array.shape[0]
        self.total_size = int(np.sum(self.palettized_array != 255))
        self.placeable_mask = None
        self.total_placeable = None

        # progress (init with self.update_progress())
        self.placed_mask = None
        self.current_progress = None


class TemplateManager:
    """A low level object with a list of tracked templates"""

    def __init__(self) -> None:
        self.list: list[Template] = []
        self.bot_owner_id: int = None
        self.combo: Combo = None

    def check_duplicate_template(self, template: Template):
        """Check if there is already a template with the same image and same coordinates.

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
                and (template.oy == t.oy and template.ox == t.ox)
            ):
                return t
        return None

    def check_valid_name(self, name: str):
        """Check if a name is valid:
        - if it's only alphanumeric chars or '-' or '_'.
        - between 2 and 40 characters
        - cannot be "@combo"

        Raise ValueError if invalid name or return the name"""
        if not re.match(r"^[A-Za-z0-9_-]*$", name):
            raise ValueError(
                "The template name can only contain letters, numbers, hyphens (`-`) and underscores (`_`)."
            )
        if len(name) < 2 or len(name) > 40:
            raise ValueError("The template name must be between 2 and 40 characters.")
        if name == "@combo":
            raise ValueError("This name is reserved for the @combo template.")
        return name

    async def save(
        self, template: Template, name: str, owner: disnake.User, hidden: bool = False
    ):
        """Save the template:
        - as a template object in the tracked_templates list
        - as a database entry in the database

        Throw an error:
        - if there is a template with the same name
        - if there is a template with the same image"""

        template.name = name
        template.owner_id = owner.id
        template.hidden = hidden

        # check on the name
        template.name = self.check_valid_name(template.name)

        # check duplicate template names
        same_name_template = self.get_template(
            template.name, template.owner_id, template.hidden
        )
        if same_name_template:
            raise ValueError(
                f"There is already a template with the name `{template.name}`."
            )

        # check duplicate images/coords
        same_image_template = self.check_duplicate_template(template)
        if same_image_template:
            raise ValueError(
                f"There is already a template with the same image and coords named `{same_image_template.name}`."
            )

        # save in db
        await db_templates.create_template(template)
        # save in list
        self.list.append(template)
        # update the @combo
        self.update_combo()
        # log
        tracker_logger.info(f"Template added: '{template.name}' by {owner} ({owner.id})")

    def get_template(self, name, owner_id=None, hidden=False):
        """Get a template from its name, get the owner's hidden Template if hidden is True,
        Return None if not found."""
        if name == "@combo" and self.combo is not None:
            return self.combo
        for temp in self.list:
            if temp.name.lower() == name.lower():
                if hidden:
                    if temp.hidden and temp.owner_id == owner_id:
                        return temp
                else:
                    if not temp.hidden:
                        return temp
        return None

    async def delete_template(self, name, command_user, hidden):
        command_user_id = command_user.id
        temp = self.get_template(name, command_user_id, hidden)
        if not temp:
            raise ValueError(f"No template named `{name}` found.")
        if temp.owner_id != command_user_id and command_user_id != self.bot_owner_id:
            raise ValueError("You cannot delete a template that you don't own.")
        if isinstance(temp, Combo):
            raise ValueError("You cannot delete the combo.")

        await db_templates.delete_template(temp)
        self.list.remove(temp)
        self.update_combo()
        tracker_logger.info(
            f"Template deleted: '{temp.name}' by {command_user} ({command_user.id})"
        )
        return temp

    async def update_template(
        self, current_name, command_user, new_url=None, new_name=None, new_owner=None
    ):
        command_user_id = command_user.id
        old_temp = self.get_template(current_name, command_user_id, False)
        if not old_temp:
            raise ValueError(f"No template named `{current_name}` found.")
        if old_temp.owner_id != command_user_id and command_user_id != self.bot_owner_id:
            raise ValueError("You cannot edit a template that you don't own.")
        if isinstance(old_temp, Combo):
            raise ValueError("You cannot edit the combo.")

        if new_url:
            new_temp = await get_template_from_url(new_url)
            if new_temp.total_placeable == 0:
                raise ValueError(
                    "The template seems to be outside the canvas, make sure it's correctly positioned."
                )
            temp_same_image = self.check_duplicate_template(new_temp)
            if temp_same_image:
                raise ValueError(
                    f"There is already a template with the same image and coords named `{temp_same_image.name}`."
                )
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
            if temp_with_same_name and temp_with_same_name != old_temp:
                raise ValueError(
                    f"There is already a template with the name `{new_name}`."
                )
            new_temp.name = new_name
        if new_owner:
            new_owner_id = new_owner.id
            new_temp.owner_id = new_owner_id
        new_temp.hidden = False
        try:
            temp_id = await db_templates.update_template(
                old_temp, new_temp.url, new_temp.name, new_temp.owner_id
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                "You cannot transfer the ownership to a user that has never used the bot."
            )
        if not temp_id:
            raise ValueError("There was an error while updating the template.")
        old_temp_index = self.list.index(old_temp)
        self.list.remove(old_temp)
        self.list.insert(old_temp_index, new_temp)
        self.update_combo()
        tracker_logger.info(
            "Template updated: '{}' by {} ({}):{}{}{}".format(
                old_temp.name,
                command_user,
                command_user.id,
                " URL changed" if new_url else "",
                f" name changed (new name: {new_temp.name})" if new_name else "",
                f" owner changed (new owner: {new_owner} ({new_owner.id}))"
                if new_owner
                else "",
            )
        )
        return old_temp, new_temp

    def get_all_public_templates(self):
        return [t for t in self.list if not t.hidden]

    def get_hidden_templates(self, owner_id):
        return [t for t in self.list if t.hidden and t.owner_id == owner_id]

    async def load_all_templates(self, canvas_code):
        """Load all the templates from the database in self.list"""
        logger.info("Loading templates...")
        start = time.time()
        db_list = await db_templates.get_all_templates(canvas_code)
        count = 0
        has_combo = False
        for db_temp in db_list:
            name = db_temp["name"]
            owner_id = db_temp["owner_id"]
            hidden = db_temp["hidden"]
            url = db_temp["url"]
            if name != "@combo":
                try:
                    temp = await get_template_from_url(url)
                    temp.name = name
                    temp.owner_id = int(owner_id)
                    temp.hidden = bool(hidden)
                    temp.canvas_code = canvas_code
                    self.list.append(temp)
                    count += 1
                    logger.debug(
                        f"template {temp.name} loaded ({count}/{len(db_list)-1})"
                    )
                except Exception as e:
                    logger.warn("Failed to load template {}: {}".format(name, e))
            else:
                has_combo = True
        end = time.time()
        nb_templates = len(db_list) - (1 if has_combo else 0)
        logger.info(
            f"{count}/{nb_templates} Templates loaded (time: {round(end-start, 2)}s)"
        )

    def make_combo_image(self) -> np.ndarray:
        """Make an index array combining all the template arrays in self.list"""
        combo = np.full((stats.board_array.shape[0], stats.board_array.shape[1]), 255)
        # reverse order to put the new templates at the bottom
        for template in self.list[::-1]:
            ox = template.ox
            oy = template.oy
            # paste the template on the combo image but exclude transparent pixels
            current_combo_at_temp_coords = template.crop_array_to_template(combo)
            template_mask = template.palettized_array != 255
            current_combo_at_temp_coords[template_mask] = template.palettized_array[
                template_mask
            ]
            paste(combo, current_combo_at_temp_coords, (oy, ox))
        return combo

    def update_combo(self, bot_id=None, canvas_code=None) -> Combo:
        """Update the combo template or create it if it doesn't exist"""
        palettized_array = self.make_combo_image()
        if self.combo is None:
            if bot_id and canvas_code:
                self.combo = Combo(
                    "@clueless-combo",
                    palettized_array,
                    0,
                    0,
                    "@combo",
                    bot_id,
                    canvas_code,
                )
            else:
                raise Exception("Cannot init the combo with empty bot_id or canvas_code")
        else:
            self.combo.palettized_array = palettized_array

        # remove the non placeable pixels
        self.combo.palettized_array[stats.placemap_array == 255] = 255
        # update the placeable mask
        self.combo.placeable_mask = self.combo.make_placeable_mask()
        self.combo.total_placeable = int(np.sum(self.combo.placeable_mask))
        return self.combo


@jit(nopython=True, cache=True)
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
        return Template(
            template_url,
            image_url,
            params.get("title"),
            detemp_array,
            ox,
            oy,
            canvas_code,
        )

    loop = asyncio.get_running_loop()
    # run this part of the code in executor to make it not blocking
    template = await loop.run_in_executor(None, _get_template)
    return template


def paste_slices(tup):
    pos, w, max_w = tup
    wall_min = max(pos, 0)
    wall_max = min(pos + w, max_w)
    block_min = -min(pos, 0)
    block_max = max_w - max(pos + w, max_w)
    block_max = block_max if block_max != 0 else None
    return slice(wall_min, wall_max), slice(block_min, block_max)


def paste(wall, block, loc):
    loc_zip = zip(loc, block.shape, wall.shape)
    wall_slices, block_slices = zip(*map(paste_slices, loc_zip))
    wall[wall_slices] = block[block_slices]


def crop_array_to_shape(array1, height, width, oy, ox):
    y0 = min(max(0, oy), array1.shape[0])
    y1 = max(0, min(array1.shape[0], oy + height))
    x0 = min(max(0, ox), array1.shape[1])
    x1 = max(0, min(array1.shape[1], ox + width))
    _cropped_array = array1[y0:y1, x0:x1].copy()
    cropped_array = np.full((height, width), 255)
    cropped_array[y0 - oy : y1 - oy, x0 - ox : x1 - ox] = _cropped_array
    return cropped_array


def make_before_after_gif(
    old_temp: Template, new_temp: Template, extra_padding=5, with_text=True
) -> Image.Image:
    """
    Make a before/after GIF comparing 2 templates images layered over the canvas

    Parameters
    ----------
    old_temp: the template that will show first on the GIF
    new_temp: the template that will show last on the GIF
    extra_padding: the number of pixels to add around the image
    with_text: add a "Before" and "After" text on the image if set to True
    """

    if with_text:
        before_text = PixelText("Before", "roman", (255, 255, 255, 255), (0, 0, 0, 0))
        after_text = PixelText("After", "roman", (255, 255, 255, 255), (0, 0, 0, 0))
        text_height = before_text.font.max_height
    else:
        text_height = 0

    old_temp_x0 = old_temp.ox
    old_temp_x1 = old_temp.ox + old_temp.width
    old_temp_y0 = old_temp.oy
    old_temp_y1 = old_temp.oy + old_temp.height

    new_temp_x0 = new_temp.ox
    new_temp_x1 = new_temp.ox + new_temp.width
    new_temp_y0 = new_temp.oy
    new_temp_y1 = new_temp.oy + new_temp.height

    # origin coords
    min_y0 = min(old_temp_y0, new_temp_y0) - extra_padding - text_height
    min_x0 = min(old_temp_x0, new_temp_x0) - extra_padding
    # end coords
    max_y1 = max(old_temp_y1, new_temp_y1) + extra_padding
    max_x1 = max(old_temp_x1, new_temp_x1) + extra_padding
    # result images size
    max_height = max_y1 - min_y0
    max_width = max_x1 - min_x0

    # crop the current canvas to the result images size
    background_before = crop_array_to_shape(
        stats.board_array, max_height, max_width, min_y0, min_x0
    )
    background_before = stats.palettize_array(background_before)
    background_after = background_before.copy()

    # add padding to images so they can have the exact same size
    old_y0_offset = old_temp_y0 - min_y0
    old_x0_offset = old_temp_x0 - min_x0
    old_y1_offset = max_y1 - old_temp_y1
    old_x1_offset = max_x1 - old_temp_x1
    old_temp_padding = [
        (old_y0_offset, old_y1_offset),
        (old_x0_offset, old_x1_offset),
    ]
    array_before = np.pad(
        old_temp.palettized_array, old_temp_padding, constant_values=255
    )
    array_before = stats.palettize_array(array_before)

    new_y0_offset = new_temp_y0 - min_y0
    new_x0_offset = new_temp_x0 - min_x0
    new_y1_offset = max_y1 - new_temp_y1
    new_x1_offset = max_x1 - new_temp_x1
    new_temp_padding = [
        (new_y0_offset, new_y1_offset),
        (new_x0_offset, new_x1_offset),
    ]
    array_after = np.pad(new_temp.palettized_array, new_temp_padding, constant_values=255)
    array_after = stats.palettize_array(array_after)

    # paste the template images on the canvas and darken the canvas
    img_before = highlight_image(array_before, background_before, 0.3, (0, 0, 0, 255))
    img_after = highlight_image(array_after, background_after, 0.3, (0, 0, 0, 255))

    # add the text
    if with_text:
        before_text_image = before_text.get_image()
        after_text_image = after_text.get_image()
        img_before.paste(before_text_image, (2, 2), before_text_image)
        img_after.paste(after_text_image, (2, 2), after_text_image)

    # generate the GIF (can take long with a large image)
    frames = [img_before, img_after]
    diff_gif = BytesIO()
    save_transparent_gif(frames, 1200, diff_gif)
    diff_gif.seek(0)
    return diff_gif


@jit(nopython=True, cache=True)
def fast_max_chunk(chunked_mask):
    """find the index of the chunk with the most pixels to place in a chunk list"""
    max_index = -1
    chunk_pixels = 0
    for i, chunk in enumerate(chunked_mask):
        sum = np.sum(chunk)
        if sum > chunk_pixels:
            chunk_pixels = sum
            max_index = i
    return max_index
