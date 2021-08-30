import discord
import numpy as np
from matplotlib.colors import hsv_to_rgb
from PIL import Image, ImageColor
from io import BytesIO
from discord.ext import commands
from blend_modes import hard_light

from utils.discord_utils import image_to_file, get_image_from_message
from utils.image.gif_saver import save_transparent_gif
from utils.image.image_utils import get_pxls_color, is_hex_color
from utils.image.img_to_gif import img_to_animated_gif

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


        try:
            is_animated = img.is_animated
            img.info["duration"]
        except:
            is_animated = False

        # animated image with a duration(gif)
        if is_animated:
            async with ctx.typing():
                # convert each frame to the color
                res_frames = []
                durations = []
                for i in range(0,img.n_frames):
                    img.seek(i)
                    res_frame = img.copy()
                    frame = colorify(res_frame,rgb)
                    res_frames.append(frame)
                    durations.append(img.info["duration"])

                # combine the frames back to a gif
                animated_img = BytesIO()
                await self.client.loop.run_in_executor(None,save_transparent_gif,res_frames,durations,animated_img)
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

        await self.colorify(ctx,'pink',url)

    @commands.command(usage = "<image|url|emoji>)",description = "Turn an image to a rainbow GIF.")
    async def rainbowfy(self,ctx,url=None):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        img = Image.open(BytesIO(img))

        # check if the image is animated
        try:
            is_animated = img.is_animated
            img.info["duration"]
            # loop through the gif it has less than 8 frames
            if img.n_frames < 8:
                nb_colors = img.n_frames * (8//img.n_frames +1)
            else:
                nb_colors = img.n_frames
        except:
            is_animated = False
            nb_colors = 16
            bytes = img_to_animated_gif(img)
            img = Image.open(BytesIO(bytes))

        async with ctx.typing():
            # change each frame to a different color
            palette =  get_rainbow_palette(nb_colors,saturation=0.5,lightness=0.6)
            res_frames = []
            durations = []
            for i,color in enumerate(palette):
                if is_animated:
                    img.seek(i%img.n_frames) # to loop in the gif if we exceed the number of frames
                    _img = img.copy()
                    durations.append(img.info["duration"])
                else:
                    _img = img
                    durations.append(0.01)
                res_frames.append(colorify(_img,color))

            # combine the frames back to a gif
            animated_img = BytesIO()
            await self.client.loop.run_in_executor(None,save_transparent_gif,
                res_frames,durations,animated_img)
            animated_img.seek(0)
            file=discord.File(fp=animated_img,filename="rainbowfy.gif")
            await ctx.send(file=file)

def get_rainbow_palette(nb_colors:int,saturation:float=1,lightness:float=1) -> list:
    """ Get a list of rgb colors with a linear hue (saturation and lightness 
    values should be between 0 and 1)"""
    palette = []
    for i in range(nb_colors):
        hue = i/nb_colors
        rgb_float = hsv_to_rgb((hue,saturation,lightness))
        rgb = [round(c*255) for c in rgb_float]
        palette.append(tuple(rgb))
    return palette

def colorify(img:Image.Image,color:tuple) -> Image.Image:
    ''' Blend the image with a solid color image with the given color image.
    The blend mode used is 'hard light' '''

    # background image
    img = img.convert('RGBA')
    img_array = np.array(img)

    # save the alpha channel
    alpha_channel = None
    if img_array.shape[-1] == 4:
        alpha_channel = img.split()[-1]
    elif img_array.shape[-1] != 3:
        raise ValueError(f"Incorrect number of channels in the image\
            (received: {img_array.shape[-1]},\ must be 3 or 4)")

    # convert to grayscale
    gray_img = img.convert('L').convert("RGBA")
    gray_array = np.array(gray_img)
    gray_array = gray_array.astype(float)

    # make the filter image: a solid image with the color input
    filter = Image.new('RGBA',img.size,color)
    filter_array = np.array(filter)
    filter_array = filter_array.astype(float)

    # Blend the images
    blended_img_array = hard_light(gray_array,filter_array,1)
    blended_img_array = np.uint8(blended_img_array)
    blended_img = Image.fromarray(blended_img_array)

    # put the alpha values back
    if alpha_channel:
        blended_img.putalpha(alpha_channel)
    return blended_img

def setup(client):
    client.add_cog(Colorify(client))
