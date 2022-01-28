import numpy as np
from PIL import Image
from numba import jit
from urllib.parse import parse_qs, urlparse
from io import BytesIO

from utils.utils import get_content
from utils.setup import stats
from utils.pxls.template import get_rgba_palette, reduce


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
                    if alpha != 0:
                        result[y, x] = array[py, px]
                        result[y, x, 3] = 255
                        break
                # to break of the double loop
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


async def get_template(template_url: str):
    params = parse_template(template_url)

    if params is None:
        raise ValueError("The template URL is invalid.")

    image_url = params["template"]
    true_width = int(params["tw"])

    try:
        image_bytes = await get_content(image_url, "image")
    except Exception:
        raise ValueError("Couldn't download the template image.")

    template_image = Image.open(BytesIO(image_bytes))
    template_image = template_image.convert("RGBA")
    template_array = np.array(template_image)

    detemp_array = detemplatize(template_array, true_width)
    detemp_image = Image.fromarray(detemp_array)
    return (detemp_image, params)


def get_progress(template_array: np.ndarray, params, get_progress_image=True):
    """Return tuple(correct pixels, total pixels, progress image)"""
    x = int(params["ox"])
    y = int(params["oy"])
    width = template_array.shape[1]
    height = template_array.shape[0]
    palettized_array = reduce(template_array, get_rgba_palette())

    # deal with out of bounds coords:
    # to do that we copy the part of the board matching the template area
    # and we paste it on a new array with the template size at the correct coords
    y0 = max(0, y)
    y1 = min(stats.board_array.shape[0], y + height)
    x0 = max(0, x)
    x1 = min(stats.board_array.shape[1], x + width)
    _cropped_board = stats.board_array[y0:y1, x0:x1].copy()
    _cropped_placemap = stats.placemap_array[y0:y1, x0:x1].copy()
    cropped_board = np.full_like(palettized_array, 255)
    cropped_board[y0 - y : y1 - y, x0 - x : x1 - x] = _cropped_board
    cropped_placemap = np.full_like(palettized_array, 255)
    cropped_placemap[y0 - y : y1 - y, x0 - x : x1 - x] = _cropped_placemap

    # template size
    alpha_mask = (template_array[:, :, 3] == 255)  # create a mask with all the non-transparent pixels on the template image (True = non-transparent)
    alpha_mask[cropped_placemap == 255] = False  # exclude pixels outside of the placemap
    total_pixels = np.sum(alpha_mask)  # count the "True" pixels on the mask

    # correct pixels
    placed_mask = (palettized_array == cropped_board)  # create a mask with the pixels of the template matching the board
    placed_mask[cropped_placemap == 255] = False  # exclude the pixcels outside of the placemap
    correct_pixels = np.sum(placed_mask)  # count the "True" pixels on the mask

    if get_progress_image:
        progress_array = np.zeros((height, width, 4), dtype=np.uint8)
        opacity = 0.65
        progress_array[placed_mask] = [0, 255, 0, 255 * opacity]  # correct pixels = green
        progress_array[~placed_mask] = [255, 0, 0, 255 * opacity]  # incorrect pixels = red
        progress_array[cropped_placemap == 255] = [0, 0, 255, 255]  # not placeable = blue
        progress_array[palettized_array == 255] = [0, 0, 0, 0]  # outside of the template = transparent
        progress_image = Image.fromarray(progress_array)

        cropped_board[palettized_array == 255] = 255  # crop the board to the template visible pixels
        board_image = Image.fromarray(stats.palettize_array(cropped_board))
        res_image = Image.new("RGBA", board_image.size)
        res_image = Image.alpha_composite(res_image, board_image)
        res_image = Image.alpha_composite(res_image, progress_image)
    else:
        res_image = None

    return (correct_pixels, total_pixels, res_image)
