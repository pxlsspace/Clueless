from PIL import Image, ImageColor
import numpy as np
import re
from utils.setup import stats

# from https://note.nkmk.me/en/python-pillow-concat-images/
def h_concatenate(im1, im2, resample=Image.BICUBIC, resize_im2=True,gap_width=0):
    ''' concatenate 2 images next to each other,
    the 2nd image gets resized unless resize_im2 is False,
    gap_width is the width of a gap that will be between the 2 images '''
    if im1.height == im2.height:
        _im1 = im1
        _im2 = im2
    elif resize_im2 == False:
        _im1 = im1.resize((int(im1.width * im2.height / im1.height), im2.height), resample=resample)
        _im2 = im2
    else:
        _im1 = im1
        _im2 = im2.resize((int(im2.width * im1.height / im2.height), im1.height), resample=resample)
    
    gap = Image.new('RGBA',(gap_width,_im1.height),color=(0,0,0,0))
    dst = Image.new('RGBA', (_im1.width + _im2.width + gap_width, _im1.height))
    
    dst.paste(_im1, (0, 0))
    dst.paste(gap, (_im1.width, 0))
    dst.paste(_im2, (_im1.width+gap_width, 0))
    return dst

# from https://note.nkmk.me/en/python-pillow-concat-images/
def v_concatenate(im1, im2, resample=Image.BICUBIC, resize_im2=True,gap_height=0):
    ''' concatenate 2 images on top of each other,
    the 2nd image gets resized unless resize_im2 is False,
    gap_height is the height of a gap that will be between the 2 images '''
    if im1.width == im2.width:
        _im1 = im1
        _im2 = im2
    elif resize_im2 == False:
        _im1 = im1.resize((im2.width, int(im1.height * im2.width / im1.width)), resample=resample)
        _im2 = im2
    else:
        _im1 = im1
        _im2 = im2.resize((im1.width, int(im2.height * im1.width / im2.width)), resample=resample)

    gap = Image.new('RGBA',(_im1.width,gap_height),color=(0,0,0,0))
    dst = Image.new('RGBA', (_im1.width, _im1.height + _im2.height + gap.height))
    
    dst.paste(_im1, (0, 0))
    dst.paste(gap, (0, _im1.height))
    dst.paste(_im2, (0, _im1.height+gap.height))
    return dst

def add_outline(original_image,color,full=True,outline_width=1,crop=True):
    ''' Add a border/outline around a transparent PNG '''

    # Convert to RGBA to manipulate the image easier
    original_image = original_image.convert('RGBA')
    background=Image.new("RGBA", (original_image.size[0]+outline_width*2, original_image.size[1]+outline_width*2), (0, 0, 0, 0))
    if len(color) == 3:
        color = list(color)
        color.append(255)
    #crate a mask of the outline color
    image_array = np.array(original_image)
    mask = image_array[:,:,3] == 255
    bg = np.zeros_like(image_array)
    bg[mask] = color

    # shift the mask around to create an outline
    outline = Image.fromarray(bg)
    if full:
        for x in range(0,outline_width*2+1):
            for y in range(0,outline_width*2+1):
                background.paste(outline,(x,y),outline)
    else:
        for x in range(0,outline_width*2+1):
            for y in range(abs(-abs(x)+outline_width),-abs(x-outline_width)+outline_width*2+1):
                background.paste(outline,(x,y),outline)

    # merge the outline with the image
    background.paste(original_image, (outline_width,outline_width), original_image)

    if crop:
        background = remove_white_space(background)

    return background

def remove_white_space(original_image):
    """ Remove the extra transparent pixels around a PNG image """
    image = original_image.convert('RGBA')
    image_array = np.array(image)
    mask = image_array[:,:,3] == 255
    r = mask.any(1)
    if r.any():
        m,n = mask.shape
        c = mask.any(0)
        out = image_array[r.argmax():m-r[::-1].argmax(), c.argmax():n-c[::-1].argmax()]
    else:
        out = np.empty((0,0),dtype=bool)

    return Image.fromarray(out)

def get_pxls_color(input):
    """ Get the RGBA value of a pxls color by its name. """
    color_name = input.lower().replace("gray","grey")
    for color in stats.get_palette():
        if color["name"].lower() == color_name.lower():
            rgb = ImageColor.getcolor(f'#{color["value"]}',"RGBA")
            return rgb
    raise ValueError("The color '{}' was not found in the pxls palette. ".format(input))

def is_hex_color(input_string):
    """ Check if a string has the format of a hex color (#fff or #ffffff)"""
    hex_color_regex = r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'
    regexp = re.compile(hex_color_regex)
    if regexp.search(input_string):
        return True
    else:
        return False

