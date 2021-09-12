import discord
import numpy as np
from matplotlib.colors import hsv_to_rgb
from PIL import Image, ImageColor
from io import BytesIO
from discord.ext import commands
from blend_modes import hard_light
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

from utils.discord_utils import image_to_file, get_image_from_message
from utils.image.gif_saver import save_transparent_gif
from utils.image.image_utils import get_pxls_color, is_hex_color
from utils.image.img_to_gif import img_to_animated_gif
from utils.setup import GUILD_IDS
from utils.arguments_parser import MyParser

class Colorify(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @cog_ext.cog_slash(
        name="colorify",
        description="Turn an image to a different color.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="color",
            description="A pxlsColor name or hex color.",
            option_type=3,
            required=True
        ),
        create_option(
            name="image",
            description="Can be an image URL or a custom emoji.",
            option_type=3,
            required=False
        )]
    )
    async def _colorify(self,ctx:SlashContext, color, image=None):
        await ctx.defer()
        await self.colorify(ctx,color,image)

    @commands.command(
        name = "colorify",
        description="Turn an image to a different color.",
        usage="<color> <image|url|emoji>",
        aliases=["colorize"])
    async def p_colorify(self,ctx,color,url=None):
        async with ctx.typing():
            await self.colorify(ctx,color,url)

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
            res = colorify(img,rgb)
            file = image_to_file(res,"colorify.png")

        await ctx.send(file=file)

    @cog_ext.cog_slash(
        name="pinkify",
        description="Turn an image pink.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="image",
            description="Can be an image URL or a custom emoji.",
            option_type=3,
            required=False
        )]
    )
    async def _pinkify(self,ctx:SlashContext, image=None):
        await ctx.defer()
        await self.colorify(ctx,'pink',image)

    @commands.command(description="Turn an image pink.",usage="<image|url|emoji>")
    async def pinkify(self,ctx,url=None):
        async with ctx.typing():
            await self.colorify(ctx,'pink',url)

    @cog_ext.cog_slash(
        name="rainbowfy",
        description="Turn an image to a rainbow GIF.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="image",
            description="Can be an image URL or a custom emoji.",
            option_type=3,
            required=False
        ),
        create_option(
            name="saturation",
            description="The rainbow saturation value between 0 and 100 (default: 50).",
            option_type=4,
            required=False
        ),
        create_option(
            name="lightness",
            description="The rainbow lightness value between 0 and 100 (default: 60).",
            option_type=4,
            required=False
        )]
    )
    async def _rainbowfy(self,ctx:SlashContext, image=None,saturation=None,lightness=None):
        await ctx.defer()
        args = ()
        if image:
            args += (image,)
        if saturation:
            args += ("-saturation",str(saturation))
        if lightness:
            args += ("-lightness",str(lightness))

        await self.rainbowfy(ctx,*args)

    @commands.command(
        name="rainbowfy",
        usage = "<image|url|emoji> [-saturation value] [-lightness value]",
        description = "Turn an image to a rainbow GIF.",
        help = """
            - `<url|image|emoji>`: the image you want to rainbowfy
            - `[-saturation|-s value]`: the rainbow saturation value between 0 and 100 (default: 50)
            - `[-lightness|-l value]`: the rainbow lightness value between 0 and 100 (default: 60)""")
    async def p_rainbowfy(self,ctx,*args):
        async with ctx.typing():
            await self.rainbowfy(ctx,*args)

    async def rainbowfy(self,ctx,*args):

        parser = MyParser(add_help=False)
        parser.add_argument("url",action="store",nargs="*")
        parser.add_argument("-saturation",action="store",default=50)
        parser.add_argument("-lightness",action="store",default=60)
        try:
            parsed_args = parser.parse_args(args)
        except Exception as error:
            return await ctx.send(f"❌ {error}")

        # check on arguments
        url = parsed_args.url[0] if parsed_args.url else None
        try:
            saturation = int(parsed_args.saturation)
        except ValueError:
            return await ctx.send(f"❌ Invalid number '{parsed_args.saturation}'")
        try:
            lightness = int(parsed_args.lightness)
        except ValueError:
            return await ctx.send(f"❌ Invalid number '{parsed_args.lightness}'")

        if saturation > 100 or saturation < 0:
            return await ctx.send("❌ The saturation value must be between 0 and 100.")
        if lightness > 100 or lightness < 0:
            return await ctx.send("❌ The lightness value must be between 0 and 100.")

        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        img = Image.open(BytesIO(img))
        rainbow_img =  await self.client.loop.run_in_executor(None,rainbowfy,img,saturation,lightness)
        file=discord.File(fp=rainbow_img, filename="rainbowfy.gif")
        await ctx.send(file=file)

def rainbowfy(img:Image.Image,saturation=50,lightness=60) -> Image.Image:
    """ Turn an image to a rainbow GIF. """
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

    # change each frame to a different color
    palette =  get_rainbow_palette(nb_colors,saturation=saturation/100,lightness=lightness/100)
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
    save_transparent_gif(res_frames,durations,animated_img)
    animated_img.seek(0)

    return animated_img

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
