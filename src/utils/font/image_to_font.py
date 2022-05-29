# https://github.com/akirbaes/Pixel-Font/blob/master/font_to_data.py

import io
import json
from os import path

import numpy as np
from PIL import Image

""" This file contains function to create font usable by font_manager.py
INPUT: filename of the characters list
there must exist a FILENAME.png image and a FILENAME.txt file containing the characters represented
(pad with spaces if a line doesn't go until the end)

OUTPUT: a FILENAME.json with the character positions """


def generate_data(fontimage_file):
    AUTOALIGN_LEFTMOST = True  # Otherwise, will align based on where you put the character in the rectangle
    if "aligned" in fontimage_file:
        AUTOALIGN_LEFTMOST = False
    fontimage = Image.open(fontimage_file).convert("RGB")
    image_width, image_height = fontimage.size

    # INPUT: the characters that appear in the font, in order
    filename = fontimage_file[:-4] + ".txt"
    with io.open(filename, "r", encoding="utf8") as f:
        allchars = f.read()
    # print(allchars)

    # allchars = "ABCDEFGHIJKLM\nNOPQRSTUVWXYZ"
    allchars = allchars.strip("\n")

    charlines = allchars.split("\n")
    chars_vertical_count = len(charlines)
    y_sep = image_height // chars_vertical_count

    # determine background color by majority
    def majority_color(image):
        image_width, image_height = image.size
        colors_counter = dict()
        for x in range(image_width):
            for y in range(image_height):
                pixel = image.getpixel((x, y))
                colors_counter[pixel] = colors_counter.get(pixel, -1) + 1
        maxcount = 0
        majority_color = (0, 0, 0)
        for color in colors_counter:
            if colors_counter[color] > maxcount:
                majority_color = color
                maxcount = colors_counter[majority_color]
        return majority_color

    #
    background_color = majority_color(fontimage)
    print(fontimage_file, background_color)
    # background_color = (0,0,0) #if doesn't work
    # print("background_color=",background_color)

    char_pos_size = dict()
    char_pos_size["background"] = background_color

    # Determine the boundaries of the character
    char_horizontal_count = 0
    for line in charlines:
        char_horizontal_count = max(char_horizontal_count, len(line))
    x_sep = image_width // char_horizontal_count
    print("Image of ", image_width, "x", image_height)
    print("Characters grid:", char_horizontal_count, "x", chars_vertical_count)
    print("Characters box:", x_sep, "x", y_sep)
    for j, line in enumerate(charlines):
        for i, character in enumerate(line):
            charx = i * x_sep
            chary = j * y_sep
            x0 = x_sep
            y0 = y_sep
            x1 = 0
            y1 = 0

            for dy in range(y_sep):
                for dx in range(x_sep):
                    pixel = fontimage.getpixel((charx + dx, chary + dy))
                    if pixel != background_color:
                        x0 = min(dx, x0)
                        y0 = min(dy, y0)
                        y1 = max(dy, y1)
                        if ("µ" in fontimage_file) and not (
                            pixel[1] == 0 and pixel[2] == 0 and pixel[0] > 1
                        ):
                            dx += 1  # If subpixels, pixels other than red are bigger on the right
                        x1 = max(dx, x1)

            # print(character,charx,chary,x1>x0 and y1>y0)
            if x1 >= x0 and y1 >= y0:
                char_pos_size[character] = [charx, chary, x0, y0, x1, y1]
                # Character fits into this box as [X+X0,Y+Y0,X+X1,Y+Y1]
                # charx, chary show the position compared to other characters

    font_width = 0
    font_height = 0
    origin_x = float("inf")  # top-left of the box regardless of char size
    origin_y = float("inf")
    # end_x = 0
    # end_y = 0 #Bottom right of the box regardless of char size
    for key in char_pos_size:
        if len(key) == 1:
            cx, cy, x0, y0, x1, y1 = char_pos_size[key]
            font_width = max(font_width, x1 - x0 + 1)
            font_height = max(font_height, y1 - y0 + 1)
            origin_x = min(origin_x, x0)
            origin_y = min(origin_y, y0)

    # shift everything by origin for neat cut
    # hence, x0 and y0 should be 0 most of the time
    # except for things like underscore
    # so we just include the shift in the size and drop x0,y0
    # Because we only really needed one height, and all the widths for our purposes
    for key in char_pos_size:
        if len(key) == 1:
            cx, cy, x0, y0, x1, y1 = char_pos_size[key]
            if "mono" in fontimage_file:
                # If mono, all characters must have the same width
                char_pos_size[key] = (
                    cx + origin_x,
                    cy + origin_y,
                    font_width,
                    y1 - origin_y + 1,
                )
            else:
                if AUTOALIGN_LEFTMOST:
                    char_pos_size[key] = (
                        cx + x0,
                        cy + origin_y,
                        x1 - x0 + 1,
                        y1 - origin_y + 1,
                    )
                else:
                    char_pos_size[key] = (
                        cx + origin_x,
                        cy + origin_y,
                        x1 - origin_x + 1,
                        y1 - origin_y + 1,
                    )

    for key in char_pos_size:
        if len(key) == 1:
            x0, y0, x1, y1 = char_pos_size[key]
            font_width = max(font_width, x1 - x0 + 1)
            font_height = max(font_height, y1 - y0 + 1)
    char_pos_size["width"] = font_width
    char_pos_size["height"] = font_height

    jsonform = json.dumps(char_pos_size, indent=4, separators=(",", ": "))
    # print(repr(jsonform))
    with io.open(fontimage_file[:-4] + ".json", "w", encoding="utf8") as f:
        f.write(jsonform)
    # with io.open(fontimage_file[:-4] + ".json", "r", encoding="utf8") as f:
    #     newdict = json.load(f)

    char_pos_size["background"] = (64, 64, 64)
    return char_pos_size


def create_font_template(char_height, char_width, nb_line, nb_col=1):
    """create a grid for a font in the dimensions given"""
    color1 = (36, 181, 254)
    color2 = (18, 92, 199)
    res_array = np.empty((0, char_height * (nb_line + 1), 3), dtype=np.uint8)
    for j in range(nb_col):
        row_array = np.zeros((char_width, char_height, 3), dtype=np.uint8)
        if j % 2 == 0:
            row_array[:, :] = color1
        else:
            row_array[:, :] = color2

        for i in range(nb_line):
            array_to_add = np.zeros((char_width, char_height, 3), dtype=np.uint8)
            if (j + i) % 2 == 0:
                array_to_add[:, :] = color2
            else:
                array_to_add[:, :] = color1
            row_array = np.concatenate((row_array, array_to_add), axis=1)
        res_array = np.concatenate((res_array, row_array), axis=0)
    return Image.fromarray(res_array)


if __name__ == "__main__":

    create_font_template(5, 7, 10, 10).save("temp.png")
    font_name = "typewriter"

    basepath = path.dirname(__file__)
    fonts_folder = path.abspath(
        path.join(basepath, "..", "..", "..", "resources", "fonts", font_name)
    )
    font_img_file = path.join(fonts_folder, font_name + ".png")
    print(font_img_file)
    generate_data(font_img_file)

    img = Image.open(font_img_file).convert("RGB")
    img.save(font_img_file)
    print("done!")
