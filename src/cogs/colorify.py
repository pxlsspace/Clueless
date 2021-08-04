import discord
import cv2
import colorsys
import numpy as np
from PIL import Image, ImageColor
from io import BytesIO
from discord.ext import commands

from utils.discord_utils import image_to_file, get_image_from_message
from utils.gif_saver import save_transparent_gif
from utils.image_utils import get_pxls_color, is_hex_color

class Colorify(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @commands.command(
        description="Turn an image to a different color.",
        usage="<color> <image|url|emoji>",
        aliases=["colorize"])
    async def colorify(self,ctx,color,url=None):
        # get the rgba from the color input
        try:
            rgba = get_pxls_color(color)
        except ValueError:
            if is_hex_color(color):
                rgba = ImageColor.getcolor(color,"RGBA")
            else:
                return await ctx.send(f'❌ The color {color} is invalid.')
        rgb = rgba[:-1]

        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        img = Image.open(BytesIO(img))

        # animated image (gif)
        try:
            is_animated = img.is_animated
        except:
            is_animated = False
        if is_animated:
            async with ctx.typing():
                # convert each frame to the color
                res_frames = []
                for i in range(0,img.n_frames):

                    img.seek(i)
                    res_frame = img.copy()
                    frame = colorify(res_frame,rgb)
                    res_frames.append(frame)
                # combine the frames back to a gif
                animated_img = BytesIO()
                await self.client.loop.run_in_executor(None,save_transparent_gif,res_frames,img.info["duration"],animated_img)
                animated_img.seek(0)
                file=discord.File(fp=animated_img,filename="colorify.gif")

        # still image (png, jpeg, ..)
        else:
            async with ctx.typing():
                res = colorify(img,rgb)
                file = image_to_file(res,"colorify.png")

        await ctx.send(file=file)
    
    @commands.command(description="Turn an image pink.",usage="<image|url|emoji>")
    async def pinkify(self,ctx,url=None):
        pink = (255,169,217)

        await self.colorify(ctx,'pink',url)

def rgb_to_hsv(rgb):
    # convert a RGB tuple to a HSV tuple
    r,g,b = (r/255 for r in rgb) # values between 0 and 1
    _hsv = colorsys.rgb_to_hsv(r,g,b)
    hsv = (h*255 for h in _hsv)
    return hsv

def colorify(img:Image.Image,color:tuple):
    ''' colorize an image with colors close to the given color '''
    # save the alpha channel
    img = img.convert('RGBA')
    image_array = np.array(img)
    alpha_channel = None
    try:
        r,g,b,alpha_channel = cv2.split(image_array)
    except ValueError:
        try:
            r,g,b = cv2.split(image_array)
        except ValueError:
            raise ValueError(f"Incorrect number of channel in the image ({len(cv2.split(img))})")

    # convert to grayscale
    gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
    gray_values = cv2.split(gray)[0]

    # convert to HSV
    gray_brg = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    gray_hsv = cv2.cvtColor(gray_brg, cv2.COLOR_BGR2HSV)
    h,s,v = cv2.split(gray_hsv)

    # get the HSV values of the input color
    c_h,c_s,c_v = rgb_to_hsv(color)
    
    # apply the self-made color filter
    # the hue is the same as the color
    h[:,:] = (c_h/255)*180 
    # the value/brightness is the same as the color
    v[:,:] = c_v
    # the saturation is: (255 - grayscale value) * (the color saturation*2)/255
    s_ = (255 - gray_values)*((c_s)*2)/255 +s*0
    s_[s_>255] = 255
    s = s_.astype(np.uint8)

    # merge the converted values to make the result image
    final_hsv = cv2.merge((h, s, v))
    final_rgb = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2RGB)
    if alpha_channel is None:
        return Image.fromarray(final_rgb)
    else:
        r,g,b = cv2.split(final_rgb)
        final_rgba = cv2.merge((r,g,b,alpha_channel))
        return Image.fromarray(final_rgba)

def setup(client):
    client.add_cog(Colorify(client))
