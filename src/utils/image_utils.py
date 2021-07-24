from PIL import Image


# https://note.nkmk.me/en/python-pillow-concat-images/
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
