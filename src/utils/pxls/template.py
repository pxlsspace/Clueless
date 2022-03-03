# code base by Nanineye#2417

import os
import numpy as np
from PIL import Image
from numba import jit

from utils.setup import stats
from utils.image.image_utils import hex_to_rgb
from utils.log import get_logger

logger = get_logger(__name__)


class InvalidStyleException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def get_style_from_image(style_name):
    try:
        basepath = os.path.dirname(__file__)
        styles_folder = os.path.abspath(
            os.path.join(basepath, "..", "..", "..", "resources", "styles")
        )
        filename = os.path.join(styles_folder, style_name + ".png")
        img = Image.open(filename)
    except FileNotFoundError:
        raise InvalidStyleException(f"Can't find {filename}")

    try:
        img_array = np.array(img)
        mask = img_array[:, :, 3] != 0
        symbols_per_line = 16
        style_size = int(img.width / symbols_per_line)
        res = np.zeros((symbols_per_line * symbols_per_line, style_size, style_size))
        color_idx = 0
        for i in range(symbols_per_line):
            for j in range(symbols_per_line):
                x0 = i * style_size
                y0 = j * style_size
                x1 = x0 + style_size
                y1 = y0 + style_size
                symbol = mask[x0:x1, y0:y1]
                res[color_idx] = symbol
                color_idx += 1
        style = {"name": style_name, "size": style_size, "array": res}
        return style

    except Exception as e:
        raise InvalidStyleException(f"Unexpected error: {e}")


none = {"name": "none", "size": 1, "array": np.array([[[1]]] * 255)}

dotted = {
    "name": "dotted",
    "size": 3,
    "array": np.array([[[0, 0, 0], [0, 1, 0], [0, 0, 0]]] * 255),
}

plus = {
    "name": "plus",
    "size": 3,
    "array": np.array([[[0, 1, 0], [1, 1, 1], [0, 1, 0]]] * 255),
}

bigdotted = {
    "name": "bigdotted",
    "size": 5,
    "array": np.array(
        [
            [
                [0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0],
                [0, 1, 1, 1, 0],
                [0, 1, 1, 1, 0],
                [0, 0, 0, 0, 0],
            ]
        ]
        * 255
    ),
}

STYLES = [none, dotted, plus, bigdotted]
custom_styles = ["custom", "pgcustom", "numbers"]

for s in custom_styles:
    try:
        STYLES.append(get_style_from_image(s))
    except InvalidStyleException as e:
        logger.warning(f"failed to load '{s}' style: {e}")


def get_style(style_name: str):
    for style in STYLES:
        if style["name"] == style_name:
            return style
    return None


def get_rgba_palette():
    palette = stats.get_palette()
    palette = np.array([c["value"] for c in palette])
    res = []
    for i in palette:
        c = hex_to_rgb(i, "RGBA")
        res.append(c)
    return np.array(res)


def stylize(style, stylesize, palette, glow_opacity=0):
    res = np.zeros((len(palette), stylesize, stylesize, 4))
    for i in range(len(palette)):
        cstyle = np.zeros((stylesize, stylesize, 4))
        glow_value = np.copy(palette[i])
        glow_value[3] = glow_opacity * 255
        cstyle[:, :] = glow_value
        for j in range(stylesize):
            for k in range(stylesize):
                if style[i, j, k]:
                    cstyle[j, k] = palette[i] * style[i, j, k]
        res[i] = cstyle
    return res


def reduce(array: np.array, palette: np.array) -> np.array:
    """Convert an image array of RGBA colors to an array of palette index
    matching the nearest color in the given palette

    Parameters
    ----------
    array: a numpy array of RGBA colors (shape (h, w, 4))
    palette: a numpy array (shape (h, w, 1))
    """
    # convert to array just in case
    palette = np.array(palette)
    array = np.array(array)

    # convert the colors to integers so it's easier to manipulate
    # e.g. rgba(32, 64, 128, 255) -> 32*2^16 + 64*2^8 + 128*2^0 + 255*0 = 2113664
    # note: we ignore the alpha values because we will apply a filter to them later
    array_int = array.dot(np.array([65536, 256, 1, 0], dtype=np.int32))
    # remove duplicates to have a list of all the unique colors
    array_colors = np.unique(array_int)

    # we want to make a color map for each unique color
    # where the key is the color integer and the value is the palette index
    # first: we populate the color map with the palette colors
    palette_int = palette.dot(np.array([65536, 256, 1, 0], dtype=np.int32))
    color_map = np.full(shape=(256 * 256 * 256), fill_value=255, dtype=np.int32)
    for i, color in enumerate(palette_int):
        color_map[color] = i

    # if some colors do not match: we complete the color map finding the nearest color
    if not np.all(np.isin(array_colors, palette_int)):
        # using the Euclidean distance
        color_map = get_color_map(array_colors, palette, color_map)

    # we apply the color map to the image array so we get an array of palette indexes
    res_array = color_map[array_int]

    # filter out all the pixels with an alpha value inferior to 128
    res_array[array[:, :, 3] < 128] = 255  # 255 is the index for transparent pixels
    return res_array


@jit(nopython=True)
def nearest_color(color: int , palette):
    """Find the nearest color to `color` in `palette` using the Euclidean distance"""
    red = (color >> 16) & 255
    green = (color >> 8) & 255
    blue = color & 255
    rgb = np.array([red, green, blue], dtype=np.uint8)

    distances = np.sqrt(np.sum((palette[:, :3] - rgb)**2, axis=1))
    return np.argmin(distances)


@jit(nopython=True)
def get_color_map(array_colors, palette, color_map):
    """Get a color map with the index of the nearest color in the palette"""
    for color in array_colors:
        if color_map[color] == 255:
            color_map[color] = nearest_color(color, palette)
    return color_map


@jit(nopython=True)
def fast_templatize(n, m, st, red, style_size):
    res = np.zeros((style_size * n, style_size * m, 4), dtype=np.uint8)
    for i in range(n):
        for j in range(m):
            if red[i, j] != 255:  # non-alpha values
                res[
                    style_size * i : style_size * i + style_size,
                    style_size * j : style_size * j + style_size,
                ] = st[red[i][j]]
    return res


def templatize(style: dict, image: Image.Image, glow_opacity=0) -> np.ndarray:
    style_array = style["array"]
    style_size = style["size"]
    image_array = np.array(image)

    n = image_array.shape[0]
    m = image_array.shape[1]

    palette = get_rgba_palette()
    st = stylize(style_array, style_size, palette, glow_opacity)
    res = fast_templatize(n, m, st, image_array, style_size)
    return res
