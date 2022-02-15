from PIL import Image, ImageColor
import numpy as np

from utils.font.font_manager import FontManager, PixelText
from utils import image_utils
from utils.plot_utils import Theme

font_name = "minecraft"

BACKGROUND_COLOR = "#202225"
TEXT_COLOR = "#b9bbbe"
LINE_COLOR = "#2f3136"
OUTER_OUTLINE_COLOR = "#000000"
OUTER_OUTLINE_WIDTH = 3

BACKGROUND_COLOR = ImageColor.getcolor(BACKGROUND_COLOR, "RGBA")
TEXT_COLOR = ImageColor.getcolor(TEXT_COLOR, "RGBA")
LINE_COLOR = ImageColor.getcolor(LINE_COLOR, "RGBA")
OUTER_OUTLINE_COLOR = ImageColor.getcolor(OUTER_OUTLINE_COLOR, "RGBA")


def make_table_array(data, titles, alignments, colors=None, outline_dark=True):
    """Make a numpy array using the data provided"""
    line_width = 1
    vertical_margin = 2
    horizontal_margin = 4  # margin inside each cell
    title_gap_height = OUTER_OUTLINE_WIDTH  # space between the title and the content

    font = FontManager(font_name, TEXT_COLOR, BACKGROUND_COLOR)
    # insert title/headers values
    data.insert(0, titles)
    colors.insert(0, [None] * len(titles))

    # get the numpy arrays for all the text
    col_array = [[] for i in range(len(data[0]))]
    for i, lines in enumerate(data):
        for j, col in enumerate(lines):
            text = str(col)
            color = colors[i][j]
            if not color:
                color = TEXT_COLOR
            else:
                color = hex_to_rgba(color)
            pt = PixelText(text, font_name, color, (0, 0, 0, 0))
            text_array = pt.make_array()
            if outline_dark and image_utils.is_dark(color):
                outline_color = image_utils.lighten_color(color, 0.3)
                text_array = add_outline(text_array, outline_color)
                text_array = replace(text_array, (0, 0, 0, 0), BACKGROUND_COLOR)
            else:
                text_array = replace(text_array, (0, 0, 0, 0), BACKGROUND_COLOR)
                text_array = add_border(text_array, 1, BACKGROUND_COLOR)
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

            # align the element in the center for titles
            # and depending on the alignments list for the rest
            if i == 0:
                align = "center"
            else:
                align = alignments[j]
            if align == "right":
                padding = np.zeros((element.shape[0], diff_with_longest, 4), dtype=np.uint8)
                padding[:, :] = font.background_color
                element = np.append(padding, element, axis=1)
            if align == "left":
                padding = np.zeros((element.shape[0], diff_with_longest, 4), dtype=np.uint8)
                padding[:, :] = font.background_color
                element = np.append(element, padding, axis=1)
            if align == "center":
                half, rest = divmod(diff_with_longest, 2)
                padding_left = np.zeros((element.shape[0], half, 4), dtype=np.uint8)
                padding_left[:, :] = font.background_color
                padding_right = np.zeros((element.shape[0], half + rest, 4), dtype=np.uint8)
                padding_right[:, :] = font.background_color

                element = np.append(padding_left, element, axis=1)
                element = np.append(element, padding_right, axis=1)

            # add the margin inside the cells
            hmargin = np.zeros((element.shape[0], horizontal_margin, 4), dtype=np.uint8)
            hmargin[:, :] = font.background_color
            element = np.concatenate((hmargin, element, hmargin), axis=1)

            vmargin = np.zeros((vertical_margin, element.shape[1], 4), dtype=np.uint8)
            vmargin[:, :] = font.background_color
            element = np.concatenate((vmargin, element, vmargin), axis=0)

            # add the grid line around the element
            element = add_border(element, line_width, LINE_COLOR)

            # add a gap under the title
            if i == 0:
                title_gap = np.zeros((title_gap_height, element.shape[1], 4), dtype=np.uint8)
                title_gap[:, :] = OUTER_OUTLINE_COLOR
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
    for y in range(array.shape[0]):
        for x in range(array.shape[1]):
            if tuple(array[y, x]) == value_to_replace:
                array[y, x] = np.array(new_value)
    return array


def make_styled_corner(array, color):
    """make the styled gaps in each corner (this is just for aesthetic purposes)"""
    # top left
    width = OUTER_OUTLINE_WIDTH
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


def table_to_image(data, titles, alignments=None, colors=None, theme: Theme = None):
    """Create an image from a 2D array.

    Parameters
    ----------
    - data: list(list(Any)): a 2d list with the content of the table
    - titles: list(str): a list of titles for each column of the table
    - alignments list(str): a list of alignments for each column, either `center`, `left`, `right`
    - colors: list(str) or list(list(str)): a list of color for each line, the colors must be a string of hex code (e.g. #ffffff)
    - theme: Theme: a Theme object to set the table colors"""

    # check on params
    if len(data[0]) != len(titles):
        raise ValueError("The number of column in data and titles don't match.")
    if alignments and len(data[0]) != len(alignments):
        raise ValueError("The number of column in data and alignments don't match.")
    if colors:
        if not isinstance(colors[0], list) and len(colors) != len(data):
            raise ValueError("Incorrect shape for the colors list.")
        elif isinstance(colors[0], list) and (len(colors[0]) != len(data[0]) or len(colors) != len(data)):
            raise ValueError("Incorrect shape for the colors list.")
    # use the theme colors if a theme is given
    if theme is not None:
        global BACKGROUND_COLOR, TEXT_COLOR, LINE_COLOR, OUTER_OUTLINE_COLOR
        BACKGROUND_COLOR = theme.background_color
        TEXT_COLOR = theme.font_color
        LINE_COLOR = theme.grid_color
        OUTER_OUTLINE_COLOR = theme.table_outline_color
        outline_dark = theme.outline_dark

    else:
        BACKGROUND_COLOR = "#202225"
        TEXT_COLOR = "#b9bbbe"
        LINE_COLOR = "#2f3136"
        OUTER_OUTLINE_COLOR = "#000000"
        outline_dark = True
    BACKGROUND_COLOR = ImageColor.getcolor(BACKGROUND_COLOR, "RGBA")
    TEXT_COLOR = ImageColor.getcolor(TEXT_COLOR, "RGBA")
    LINE_COLOR = ImageColor.getcolor(LINE_COLOR, "RGBA")
    OUTER_OUTLINE_COLOR = ImageColor.getcolor(OUTER_OUTLINE_COLOR, "RGBA")

    # reshape the colors table
    if colors is None:
        colors = [[None] * len(data[0])] * len(data)
    elif not isinstance(colors[0], list):
        colors = [[c] * len(data[0]) for c in colors]

    if alignments is None:
        alignments = ["center"] * len(data[0])

    # copy the data to avoid changing the originals
    data = data.copy()
    titles = titles.copy()
    alignments = alignments.copy()
    colors = colors.copy()

    # get the table numpy array
    table_array = make_table_array(
        data, titles, alignments, colors, outline_dark=outline_dark
    )

    # add style
    table_array = add_border(table_array, OUTER_OUTLINE_WIDTH, OUTER_OUTLINE_COLOR)
    make_styled_corner(table_array, LINE_COLOR)
    table_array = add_border(table_array, 1, LINE_COLOR)

    # convert to image
    image = Image.fromarray(table_array)
    scale = 4
    new_width = image.size[0] * scale
    new_height = image.size[1] * scale
    image = image.resize((new_width, new_height), Image.NEAREST)
    return image
