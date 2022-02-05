from PIL import Image, ImageColor
import numpy as np
import re
import matplotlib.colors as mc
import colorsys
from numba import jit

from utils.setup import stats


# from https://note.nkmk.me/en/python-pillow-concat-images/
def h_concatenate(im1, im2, resample=Image.BICUBIC, resize_im2=True, gap_width=0):
    """concatenate 2 images next to each other,
    the 2nd image gets resized unless resize_im2 is False,
    gap_width is the width of a gap that will be between the 2 images"""
    if im1.height == im2.height:
        _im1 = im1
        _im2 = im2
    elif not resize_im2:
        _im1 = im1.resize(
            (int(im1.width * im2.height / im1.height), im2.height), resample=resample
        )
        _im2 = im2
    else:
        _im1 = im1
        _im2 = im2.resize(
            (int(im2.width * im1.height / im2.height), im1.height), resample=resample
        )

    gap = Image.new("RGBA", (gap_width, _im1.height), color=(0, 0, 0, 0))
    dst = Image.new("RGBA", (_im1.width + _im2.width + gap_width, _im1.height))

    dst.paste(_im1, (0, 0))
    dst.paste(gap, (_im1.width, 0))
    dst.paste(_im2, (_im1.width + gap_width, 0))
    return dst


# from https://note.nkmk.me/en/python-pillow-concat-images/
def v_concatenate(im1, im2, resample=Image.BICUBIC, resize_im2=True, gap_height=0):
    """concatenate 2 images on top of each other,
    the 2nd image gets resized unless resize_im2 is False,
    gap_height is the height of a gap that will be between the 2 images"""
    if im1.width == im2.width:
        _im1 = im1
        _im2 = im2
    elif not resize_im2:
        _im1 = im1.resize(
            (im2.width, int(im1.height * im2.width / im1.width)), resample=resample
        )
        _im2 = im2
    else:
        _im1 = im1
        _im2 = im2.resize(
            (im1.width, int(im2.height * im1.width / im2.width)), resample=resample
        )

    gap = Image.new("RGBA", (_im1.width, gap_height), color=(0, 0, 0, 0))
    dst = Image.new("RGBA", (_im1.width, _im1.height + _im2.height + gap.height))

    dst.paste(_im1, (0, 0))
    dst.paste(gap, (0, _im1.height))
    dst.paste(_im2, (0, _im1.height + gap.height))
    return dst


def add_outline(original_image, color, full=True, outline_width=1, crop=True):
    """Add a border/outline around a transparent PNG"""

    # Convert to RGBA to manipulate the image easier
    original_image = original_image.convert("RGBA")
    background = Image.new(
        "RGBA",
        (original_image.size[0] + outline_width * 2, original_image.size[1] + outline_width * 2),
        (0, 0, 0, 0),
    )
    if len(color) == 3:
        color = list(color)
        color.append(255)
    # create a mask of the outline color
    image_array = np.array(original_image)
    mask = image_array[:, :, 3] > 128
    image_array[~mask] = [0, 0, 0, 0]
    bg = np.zeros_like(image_array)
    bg[mask] = color

    # shift the mask around to create an outline
    outline = Image.fromarray(bg)
    if full:
        for x in range(0, outline_width * 2 + 1):
            for y in range(0, outline_width * 2 + 1):
                background.paste(outline, (x, y), outline)
    else:
        for x in range(0, outline_width * 2 + 1):
            for y in range(
                abs(-abs(x) + outline_width),
                -abs(x - outline_width) + outline_width * 2 + 1,
            ):
                background.paste(outline, (x, y), outline)

    # exclude the original image pixels from the background created
    image = Image.fromarray(image_array)
    outline_mask = np.full((background.height, background.width), False)
    outline_mask[
        outline_width:outline_width + image_array.shape[0],
        outline_width:outline_width + image_array.shape[1]
    ] = mask
    bg_array = np.array(background)
    bg_array[outline_mask] = [0, 0, 0, 0]
    # merge the outline with the image
    background = Image.fromarray(bg_array)
    background.paste(image, (outline_width, outline_width), image)

    if crop:
        background = remove_white_space(background)

    return background


def remove_white_space(original_image):
    """Remove the extra transparent pixels around a PNG image"""
    image = original_image.convert("RGBA")
    image_array = np.array(image)
    mask = image_array[:, :, 3] > 128
    r = mask.any(1)
    if r.any():
        m, n = mask.shape
        c = mask.any(0)
        out = image_array[r.argmax() : m - r[::-1].argmax(), c.argmax() : n - c[::-1].argmax()]
    else:
        out = np.empty((0, 0), dtype=bool)

    return Image.fromarray(out)


def get_pxls_color(input):
    """Get the RGBA value of a pxls color by its name. Return `(color_name, rgba)`"""
    color_name = input.lower().replace("gray", "grey")
    color_name = color_name.replace('"', '')
    color_name = color_name.replace("_", " ")
    for color in stats.get_palette():
        if color["name"].lower().replace(" ", "") == color_name.lower().replace(" ", ""):
            rgb = ImageColor.getcolor(f'#{color["value"]}', "RGBA")
            return color["name"], rgb
    raise ValueError("The color `{}` was not found in the pxls palette. ".format(input))


def is_hex_color(input_string):
    """Check if a string has the format of a hex color (#fff or #ffffff)"""
    hex_color_regex = r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$"
    regexp = re.compile(hex_color_regex)
    if regexp.search(input_string):
        return True
    else:
        return False


def rgb_to_hex(rgb):
    """convert a RGB/RGBA tuple to the matching hex code as a string
    ((255,255,255) -> '#ffffff')"""
    str = "#" + "%02x" * len(rgb)
    return str % rgb


def rgb_to_pxls(rgb):
    """convert a RGB tuple to a pxlsColor.
    Return None if no color match."""
    rgb = rgb[:3]
    for pxls_color in stats.get_palette():
        if rgb == hex_to_rgb(pxls_color["value"]):
            return pxls_color["name"]
    return None


def hex_to_rgb(hex: str, mode="RGB"):
    """convert a hex color string to a RGB tuple
    ('#ffffff' -> (255,255,255) or 'ffffff' -> (255,255,255)"""
    if "#" in hex:
        return ImageColor.getcolor(hex, mode)
    else:
        return ImageColor.getcolor("#" + hex, mode)


def hex_str_to_int(hex_str: str):
    """'#ffffff' -> 0xffffff"""
    if "#" in hex_str:
        return int(hex_str[1:], 16)
    else:
        return int(hex_str, 16)


def is_dark(color: tuple, theshhold=80):
    """check if a color luminance is above a threshold"""

    if len(color) == 4:
        r, g, b, a = color
    if len(color) == 3:
        r, g, b = color

    luminance_b = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance_b > theshhold:
        return False
    else:
        return True


# https://stackoverflow.com/a/49601444
def lighten_color(color, amount=0.5):
    """
    Lightens the given color by multiplying (1-luminosity) by the given amount.
    Input must be a RGB tuple.

    Examples:
    >> lighten_color((255,255,255), 0.3)
    >> lighten_color('#F034A3', 0.6)
    >> lighten_color('blue', 0.5)
    """

    try:
        c = mc.cnames[color]
    except Exception:
        color = [v / 255 for v in color]
        c = color
    c = colorsys.rgb_to_hls(*mc.to_rgb(c))
    res_color = colorsys.hls_to_rgb(c[0], 1 - amount * (1 - c[1]), c[2])
    res_color = tuple([int(v * 255) for v in res_color])
    return res_color


# this is mostly copied from PxlsFiddle code
@jit(nopython=True)
def get_image_scale(image_array: np.ndarray) -> int:
    """return the scale for an upscaled image or None if not found"""
    min_pixel_width = 99999999
    min_pixel_height = 99999999
    prev_x = 0
    prev_y = 0
    height = image_array.shape[0]
    width = image_array.shape[1]
    previous_color = image_array[0, 0]
    for y in range(height):
        for x in range(width):
            color = image_array[y, x]
            if x == 0:
                previous_color = color.copy()
            # find the next pixel with a different color
            elif (color != previous_color).any() and not (
                color[-1] == 0 and previous_color[-1] == 0  # to exclude transparent pixels
            ):
                # check if the diff is smaller than the min
                if (x - prev_x) < min_pixel_width:
                    # print(f"x: {x} y: {y}, prev_x: {prev_x} run: {x - prev_x} vs {min_pixel_width}")
                    # print(previous_color, color)
                    min_pixel_width = x - prev_x
                previous_color = color.copy()
                prev_x = x
        prev_x = 0

    for x in range(width):
        for y in range(height):
            color = image_array[y, x]
            if y == 0:
                previous_color = color.copy()
            elif (color != previous_color).any() and not (
                color[-1] == 0 and previous_color[-1] == 0
            ):
                if (y - prev_y) < min_pixel_height:
                    # print(f"x: {x} y: {y}, prev_y: {prev_y} run: {y - prev_y} vs {min_pixel_height}")
                    # print(previous_color, color)
                    min_pixel_height = y - prev_y
                previous_color = color.copy()
                prev_y = y
        prev_y = 0

    # use the largest value, it's easier to tweak down than to tweak up.
    pixel_size = max(min_pixel_width, min_pixel_height)

    if pixel_size != 1e6:
        return pixel_size
    else:
        return None
