# code base by Nanineye#2417

import os
import numpy as np
from PIL import Image
from utils.setup import stats
from utils.image.image_utils import hex_to_rgb
from numba import jit


class InvalidStyleException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def get_style_from_image(style_name):
    try:
        basepath = os.path.dirname(__file__)
        styles_folder = os.path.abspath(
            os.path.join(basepath, "..", "..", "..", "ressources", "styles")
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
        print(f"Warning: failed to load '{s}' style: {e}")


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


# from https://github.com/Seon82/pyCharity/blob/master/src/handlers/pxls/template.py#L91
def reduce(rendered_array, palette):
    best_match_idx = np.zeros(rendered_array.shape[:2], dtype=np.uint8)
    best_match_dist = np.full(rendered_array.shape[:2], 500)  # 500>sqrt(3*255^2)

    for idx, color in enumerate(palette):
        color_distance = np.linalg.norm(rendered_array - color, axis=-1)
        closer_mask = color_distance < best_match_dist
        best_match_dist[closer_mask] = color_distance[closer_mask]
        best_match_idx[closer_mask] = idx

    alpha_values = rendered_array[:, :, 3]
    best_match_idx[alpha_values < 128] = 255  # alpha index

    return best_match_idx


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
