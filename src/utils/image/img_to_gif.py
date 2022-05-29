import random
from io import BytesIO

from PIL import Image

"""Functions to turn a static image to an animated gif"""


def unique_color(image):
    """find a color that doesn't exist in the image"""
    colors = image.getdata()
    while True:
        # Generate a random color
        if image.mode == "LA":
            color = (random.randint(0, 255),)
        else:
            color = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )

        if color not in colors:
            return color


def fill_transparent(image, color, threshold=0):
    """Fill transparent image parts with the specified color"""

    def quantize_and_invert(alpha):
        if alpha <= threshold:
            return 255
        return 0

    # Get the alpha band from the image
    if image.mode == "RGBA":
        red, green, blue, alpha = image.split()
    elif image.mode == "LA":
        gray, alpha = image.split()
    # Set all pixel values below the given threshold to 255,
    # and the rest to 0
    alpha = Image.eval(alpha, quantize_and_invert)
    # Paste the color into the image using alpha as a mask
    image.paste(color, alpha)


def color_index(image, color):
    """Find the color index"""
    palette = image.getpalette()
    palette_colors = list(zip(palette[::3], palette[1::3], palette[2::3]))
    index = palette_colors.index(color)
    return index


def change_one_pixel(image):
    """Change one pixel in an image to a value un-noticeable"""
    width, height = image.size
    if image.mode == "RGBA":
        for x in range(height):
            for y in range(width):
                if image.getpixel((x, y))[-1] == 255:
                    new_color = list(image.getpixel((x, y)))
                    if new_color[0] != 255:
                        new_color[0] += 1
                    else:
                        new_color[0] -= 1
                    image.putpixel((x, y), tuple(new_color))
                    return image
    elif image.mode == "P":
        middle_value = image.getpixel((int(width / 2), int(height / 2)))
        if middle_value == 255:
            image.putpixel((int(width / 2), int(height / 2)), middle_value - 1)
        else:
            image.putpixel((int(width / 2), int(height / 2)), middle_value + 1)
        return image
    elif image.mode == "RGB":
        middle_value = list(image.getpixel((int(width / 2), int(height / 2))))
        if middle_value[0] != 255:
            middle_value[0] += 1
        else:
            middle_value[0] -= 1
        image.putpixel((int(width / 2), int(height / 2)), tuple(middle_value))
        return image

    else:
        raise ValueError("Unsupported PNG file" + "(" + image.mode + ")")


def img_to_animated_gif(image_orignal):
    """Turn a static image to an animated gif with 2 frames"""
    image = image_orignal.copy()
    frame1 = BytesIO()

    if image.mode not in ["RGBA", "RGB"]:
        image = image.convert("RGBA")

    if has_transparency(image):
        threshold = 128
        colour = unique_color(image)

        fill_transparent(image, colour, threshold)
        image = image.convert("RGB").convert("P", palette=Image.ADAPTIVE)
        image.save(frame1, format="GIF", transparency=color_index(image, colour))

        frames = [Image.open(frame1), change_one_pixel(Image.open(frame1).copy())]
        animated_gif = BytesIO()
        frames[0].save(
            animated_gif,
            format="GIF",
            optimize=False,
            save_all=True,
            append_images=frames,
            delay=0.8,
            loop=0,
            transparency=color_index(image, colour),
        )

        return animated_gif.getvalue()

    else:
        bytes = BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(bytes, format="GIF")

        frame1 = Image.open(bytes)
        frame2 = change_one_pixel(frame1.copy())
        frames = [frame1, frame2]

        animated_gif = BytesIO()
        frames[0].save(
            animated_gif,
            format="GIF",
            save_all=True,
            append_images=frames,
            delay=0.8,
            loop=0,
        )
        return animated_gif.getvalue()


# https://stackoverflow.com/a/58567453
def has_transparency(img):
    """Check if an image has fully transparent pixels (alpha=0)"""
    if img.mode == "P":
        transparent = img.info.get("transparency", -1)
        for _, index in img.getcolors():
            if index == transparent:
                return True

    elif img.mode == "RGBA":
        extrema = img.getextrema()
        if extrema[3][0] == 0:
            return True

    return False
