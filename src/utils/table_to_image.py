from PIL import Image, ImageColor
import numpy as np
from copy import deepcopy

from utils.font.font_manager import PixelText
from utils import image_utils
from utils.plot_utils import Theme, get_theme
from utils.utils import in_executor

DEFAULT_FONT = "minecraft"
OUTER_OUTLINE_WIDTH = 3


def make_table_array(data, alignments, colors, bg_colors, theme: Theme):
    """Make a numpy array using the data provided"""
    # config
    line_width = 1  # grid width
    vertical_margin = 2
    horizontal_margin = 4  # margin inside each cell
    # space between the title and the content
    title_gap_height = theme.table_outline_width

    # colors
    outer_outline_color = hex_to_rgba(theme.table_outline_color)
    line_color = hex_to_rgba(theme.grid_color)

    # get the numpy arrays for all the text
    col_array = [[] for i in range(len(data[0]))]
    for i, lines in enumerate(data):
        for j, col in enumerate(lines):
            text = str(col)
            # convert colors to RGBA
            color = colors[i][j]
            if not color:
                color = hex_to_rgba(theme.font_color)
            else:
                color = hex_to_rgba(color)
            bg_color = bg_colors[i][j]
            if not bg_color:
                bg_color = hex_to_rgba(theme.background_color)
            else:
                bg_color = hex_to_rgba(bg_color)
            bg_colors[i][j] = bg_color
            # make the text images
            pt = PixelText(text, DEFAULT_FONT, color, (0, 0, 0, 0))
            text_array = pt.make_array(accept_empty=True)
            if theme.outline_dark and image_utils.is_dark(color):
                outline_color = image_utils.lighten_color(color, 0.3)
                text_array = add_outline(text_array, outline_color)
                text_array = replace(text_array, (0, 0, 0, 0), bg_color)
            else:
                text_array = replace(text_array, (0, 0, 0, 0), bg_color)
                text_array = add_border(text_array, 1, bg_color)
            col_array[j].append(text_array)

    # create a numpy array for the whole table
    # table height: (text height + 2 * the height of lines + 2 * vertical margins) * the number of columns + the gap for the title
    table_array = np.zeros(
        (
            (col_array[0][0].shape[0] + line_width + 2 * vertical_margin)
            * len(col_array[0])
            + line_width * 2
            + title_gap_height,
            0,
            4,
        ),
        dtype=np.uint8,
    )

    for j, col in enumerate(col_array):

        longest_element = max([array.shape[1] for array in col])
        # column width: lenght of the longest elmnt + 2 * the lenght of lines + 2 * horizontal margins
        column_array = np.empty(
            (0, longest_element + 2 * line_width + 2 * horizontal_margin, 4),
            dtype=np.uint8,
        )

        for i, element in enumerate(col):
            diff_with_longest = longest_element - element.shape[1]
            bg_color = bg_colors[i][j]
            # align the element in the center for titles
            # and depending on the alignments list for the rest
            if i == 0:
                align = "center"
            else:
                align = alignments[j]
            if align == "right":
                padding = np.zeros(
                    (element.shape[0], diff_with_longest, 4), dtype=np.uint8
                )
                padding[:, :] = bg_color
                element = np.append(padding, element, axis=1)
            if align == "left":
                padding = np.zeros(
                    (element.shape[0], diff_with_longest, 4), dtype=np.uint8
                )
                padding[:, :] = bg_color
                element = np.append(element, padding, axis=1)
            if align == "center":
                half, rest = divmod(diff_with_longest, 2)
                padding_left = np.zeros((element.shape[0], half, 4), dtype=np.uint8)
                padding_left[:, :] = bg_color
                padding_right = np.zeros(
                    (element.shape[0], half + rest, 4), dtype=np.uint8
                )
                padding_right[:, :] = bg_color

                element = np.append(padding_left, element, axis=1)
                element = np.append(element, padding_right, axis=1)

            # add the margin inside the cells
            hmargin = np.zeros((element.shape[0], horizontal_margin, 4), dtype=np.uint8)
            hmargin[:, :] = bg_color
            element = np.concatenate((hmargin, element, hmargin), axis=1)

            vmargin = np.zeros((vertical_margin, element.shape[1], 4), dtype=np.uint8)
            vmargin[:, :] = bg_color
            element = np.concatenate((vmargin, element, vmargin), axis=0)

            # add the grid line around the element
            element = add_border(element, line_width, line_color)

            # add a gap under the title
            if i == 0:
                title_gap = np.zeros(
                    (title_gap_height, element.shape[1], 4), dtype=np.uint8
                )
                title_gap[:, :] = outer_outline_color
                element = np.concatenate((element, title_gap), axis=0)

            # remove the outline at the top to avoid double lines
            if i > 1:
                element = np.delete(element, slice(0, line_width), axis=0)

            column_array = np.concatenate((column_array, element), axis=0)

        # remove the outline at the left to avoid double lines
        if j != 0:
            column_array = np.delete(column_array, slice(0, line_width), axis=1)

        table_array = np.concatenate((table_array, column_array), axis=1)

    return table_array


def hex_to_rgba(hex):
    return ImageColor.getcolor(hex, "RGBA")


def add_border(array, width: int, color: tuple):
    """add a square outline around a numpy array"""

    channel_r = array[:, :, 0]
    channel_g = array[:, :, 1]
    channel_b = array[:, :, 2]
    channel_a = array[:, :, 3]

    r_cons, g_cons, b_cons, a_cons = color

    channel_r = np.pad(channel_r, width, "constant", constant_values=r_cons)
    channel_g = np.pad(channel_g, width, "constant", constant_values=g_cons)
    channel_b = np.pad(channel_b, width, "constant", constant_values=b_cons)
    channel_a = np.pad(channel_a, width, "constant", constant_values=a_cons)

    return np.dstack(tup=(channel_r, channel_g, channel_b, channel_a))


def add_outline(array, color):
    """add an outline around a text"""
    img = Image.fromarray(array)
    img = image_utils.add_outline(img, color, crop=False)
    outline_array = np.array(img)
    return outline_array


def replace(array, value_to_replace, new_value):
    """replace a value by an other in a numpy array"""
    value_to_replace = np.array(value_to_replace)
    new_value = np.array(new_value)
    return np.where(array == value_to_replace, new_value, array).astype(np.uint8)


def make_styled_corner(array, color, width):
    """make the styled gaps in each corner (this is just for aesthetic purposes)"""
    # top left
    array[:width, width * 2] = color
    array[width * 2, 0:width] = color
    # top right
    array[0:width, -(width * 2) - 1] = color
    array[width * 2, -width:] = color
    # bottom left
    array[-(width * 2) - 1, :width] = color
    array[-width:, (width * 2)] = color
    # bottom right
    array[-(width * 2) - 1, -width:] = color
    array[-width:, -(width * 2) - 1] = color


@in_executor()
def table_to_image(
    data,
    titles,
    alignments=None,
    colors=None,
    theme: Theme = None,
    bg_colors=None,
    alternate_bg=False,
    scale=4,
):
    """
    Create an image from a 2D array.

    Parameters
    ----------
    - data: list(list(Any)): a 2d list with the content of the table
    - titles: list(str): a list of titles for each column of the table
    - alignments list(str): a list of alignments for each column, either `center`, `left`, `right`
    - colors: list(str) or list(list(str)): a list of color for each line, the colors must be a string of hex code (e.g. #ffffff)
    - theme: Theme: a Theme object to set the table colors
    - bg_colors: list(str) or list(list(str)): a list of color for each cell background
    - alternate_bg: Bool: Alternate the background color on even rows if set to True
    - scale: int: the scale for the final image (default: x4)
    """

    # check on params
    if len(data[0]) != len(titles):
        raise ValueError("The number of column in data and titles don't match.")
    if alignments and len(data[0]) != len(alignments):
        raise ValueError("The number of column in data and alignments don't match.")
    if colors:
        if not isinstance(colors[0], list) and len(colors) != len(data):
            raise ValueError("Incorrect shape for the colors list.")
        elif isinstance(colors[0], list) and (
            len(colors[0]) != len(data[0]) or len(colors) != len(data)
        ):
            raise ValueError("Incorrect shape for the colors list.")
    if bg_colors:
        if not isinstance(bg_colors[0], list) and len(bg_colors) != len(data):
            raise ValueError("Incorrect shape for the bg_colors list.")
        elif isinstance(bg_colors[0], list) and (
            len(bg_colors[0]) != len(data[0]) or len(bg_colors) != len(data)
        ):
            raise ValueError("Incorrect shape for the bg_colors list.")

    # use the theme default theme if None is given
    if theme is None:
        theme = get_theme("default")

    # reshape the colors table
    if colors is None:
        colors = [[None for _ in range(len(data[0]))] for _ in range(len(data))]
    elif not isinstance(colors[0], list):
        colors = [[c] * len(data[0]) for c in colors]

    # reshape the bg_colors table
    if bg_colors is None:
        bg_colors = [[None for _ in range(len(data[0]))] for _ in range(len(data))]
    elif not isinstance(bg_colors[0], list):
        bg_colors = [[c] * len(data[0]) for c in bg_colors]

    if alignments is None:
        alignments = ["center"] * len(data[0])

    # copy the data to avoid changing the originals
    # (using deepcopy() to also copy nested lists)
    data = deepcopy(data)
    titles = deepcopy(titles)
    alignments = deepcopy(alignments)
    colors = deepcopy(colors)
    bg_colors = deepcopy(bg_colors)

    # insert title/headers values
    data.insert(0, titles)
    colors.insert(0, [None] * len(titles))
    bg_colors.insert(0, [theme.headers_background_color] * len(titles))

    if alternate_bg:
        for i, row in enumerate(bg_colors):
            for j, col in enumerate(row):
                if bg_colors[i][j] is None:
                    if i % 2 == 0:
                        bg_color = theme.odd_row_color
                    else:
                        bg_color = None
                    bg_colors[i][j] = bg_color

    # get the table numpy array
    table_array = make_table_array(data, alignments, colors, bg_colors, theme)

    # add style
    table_array = add_border(
        table_array, theme.table_outline_width, hex_to_rgba(theme.table_outline_color)
    )
    make_styled_corner(
        table_array, hex_to_rgba(theme.grid_color), theme.table_outline_width
    )
    table_array = add_border(table_array, 1, hex_to_rgba(theme.grid_color))

    # convert to image
    image = Image.fromarray(table_array)
    new_width = image.size[0] * scale
    new_height = image.size[1] * scale
    image = image.resize((new_width, new_height), Image.NEAREST)
    return image
