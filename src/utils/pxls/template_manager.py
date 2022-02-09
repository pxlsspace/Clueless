import numpy as np
import asyncio
from PIL import Image
from numba import jit
from urllib.parse import parse_qs, urlparse
from io import BytesIO

from utils.utils import get_content
from utils.setup import stats
from utils.pxls.template import get_rgba_palette, reduce


class Template():
    def __init__(self, url: str, stylized_url: str, title: str, image_array: np.ndarray, ox: int, oy: int, canvas_code) -> None:
        # template meta data
        self.url = url
        self.stylized_url = stylized_url
        self.title = title
        self.ox = ox
        self.oy = oy
        self.canvas_code = canvas_code

        # template image and array
        self.image_array = image_array  # array of RGBA
        self.palettized_array: np.ndarray = reduce(image_array, get_rgba_palette())  # array of palette indexes
        self.image = Image.fromarray(image_array)

        # template size and dimensions
        self.width = self.image_array.shape[1]
        self.height = self.image_array.shape[0]
        self.total_size = np.sum(self.image_array[:, :, 3] == 255)
        self.placeable_mask = self.make_placeable_mask()
        self.total_placeable = np.sum(self.placeable_mask)

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
        self.current_progress = np.sum(self.placed_mask)
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
