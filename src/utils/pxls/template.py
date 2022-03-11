# code base by Nanineye#2417

import os
import numpy as np
from PIL import Image
from numba import jit
from numba.core import types
from numba.typed import Dict

from utils.setup import stats
from utils.image.image_utils import hex_to_rgb
from utils.image.ciede2000 import ciede2000, rgb2lab
from utils.log import get_logger

logger = get_logger(__name__)


class InvalidStyleException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def parse_style_image(style_image: Image.Image):
    try:
        img_array = np.array(style_image)
        mask = img_array[:, :, 3] != 0
        symbols_per_line = 16
        style_size = int(style_image.width / symbols_per_line)
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
        return res, style_size

    except Exception:
        return None, None


def get_style_from_name(style_name):
    try:
        basepath = os.path.dirname(__file__)
        styles_folder = os.path.abspath(
            os.path.join(basepath, "..", "..", "..", "resources", "styles")
        )
        filename = os.path.join(styles_folder, style_name + ".png")
        img = Image.open(filename)
    except FileNotFoundError:
        raise InvalidStyleException(f"Couldn't find '{filename}'")

    style_array, style_size = parse_style_image(img)
    if style_array is None:
        raise InvalidStyleException("Couldn't parse the style image.")

    style = {"name": style_name, "size": style_size, "array": style_array}
    return style


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
        STYLES.append(get_style_from_name(s))
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


@jit(
    nopython=True,
    cache=True,
    locals={"color_bit": types.uint64, "mapped_color_idx": types.uint8},
)
def _fast_reduce(array, palette, dist_func):
    cache = Dict.empty(key_type=types.uint64, value_type=types.uint8)
    res = np.empty(array.shape[:2], dtype=np.uint8)
    width = array.shape[1]
    for idx in range(array.shape[0] * array.shape[1]):
        i = idx // width
        j = idx % width
        alpha = array[i, j, 3]
        if alpha > 128:
            color = array[i, j, :3]
            color_bit = (color[0] << 16) + (color[1] << 8) + color[2]
            if color_bit in cache:
                mapped_color_idx = cache[color_bit]
            else:
                mapped_color_idx = dist_func(color, palette)
                cache[color_bit] = mapped_color_idx
        else:
            mapped_color_idx = 255
        res[i, j] = mapped_color_idx
    return res


def reduce(array: np.array, palette: np.array, matching="fast") -> np.array:
    """Convert an image array of RGBA colors to an array of palette index
    matching the nearest color in the given palette

    Parameters
    ----------
    array: a numpy array of RGBA colors (shape (h, w, 4))
    palette: a numpy array (shape (h, w, 1))
    matching: the algorithm to use to match the colors
    (fast = Euclidean distance, accurate = CIEDE2000)
    """
    matchings = ["fast", "accurate"]
    msg = f"Unkown matching '{matching}', choose from: {', '.join(matchings)}"
    assert matching in matchings, msg

    # convert to array just in case
    palette = np.asarray(palette, dtype=np.uint8)
    array = np.asarray(array, dtype=np.uint8)

    # Get rid of the alpha component
    palette = palette[:, :3]

    if matching == "fast":
        dist_func = nearest_color_idx_euclidean
    else:
        dist_func = nearest_color_idx_ciede2000
        palette = np.asarray([rgb2lab(color) for color in palette])

    res = _fast_reduce(array, palette, dist_func)
    return res


@jit(nopython=True, cache=True)
def nearest_color_idx_ciede2000(color, palette) -> int:
    """
    Find the nearest color to `color` in `palette` using CIEDE2000.

    Parameters
    ----------
    color: a rgb ndarray of uint8 of shape (3,)
    palette: a lab ndarray of shape (palette_size,3)
    """
    lab = rgb2lab(color)

    min_distance = np.inf
    nearest_color_idx = -1
    for i, palette_lab in enumerate(palette):
        distance = ciede2000(lab, palette_lab)
        if distance < min_distance:
            min_distance = distance
            nearest_color_idx = i
    return nearest_color_idx


@jit(nopython=True, cache=True)
def nearest_color_idx_euclidean(color, palette) -> int:
    """
    Find the nearest color to `color` in `palette` using the Euclidean distance

        Parameters
    ----------
    color: a rgb ndarray of uint8 of shape (3,)
    palette: a rgb ndarray of uint8 of shape (palette_size,3)

    """
    distances = np.sum((palette - color) ** 2, axis=1)
    return np.argmin(distances)


@jit(nopython=True, cache=True)
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
