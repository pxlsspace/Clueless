from io import BytesIO

import disnake
import numpy as np
from blend_modes import hard_light
from disnake.ext import commands
from matplotlib.colors import hsv_to_rgb
from PIL import Image

from utils.arguments_parser import MyParser
from utils.discord_utils import (
    InterImage,
    autocomplete_palette,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.image.gif_saver import save_transparent_gif
from utils.image.image_utils import get_color
from utils.image.img_to_gif import img_to_animated_gif
from utils.utils import in_executor


class Colorify(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="colorify")
    async def _colorify(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage,
        color: str = commands.Param(autocomplete=autocomplete_palette),
    ):
        """Turn an image to a different color.

        Parameters
        ----------
        color: A pxlsColor name or hex color.
        """
        await inter.response.defer()
        await self.colorify(inter, color, image.url)

    @commands.command(
        name="colorify",
        description="Turn an image to a different color.",
        usage="<color> <image|url|emoji>",
        aliases=["colorize", "colourify"],
    )
    async def p_colorify(self, ctx, *args):
        colors, urls = get_urls_from_list(list(args))
        if colors:
            color = " ".join(colors)
        else:
            raise commands.MissingRequiredArgument(commands.Param(name="color"))
        url = None
        if urls:
            url = urls[0]

        async with ctx.typing():
            await self.colorify(ctx, color, url)

    async def colorify(self, ctx, color, url=None):
        # get the rgba from the color input

        color_name, rgb = get_color(color, mode="RGB")
        if rgb is None:
            return await ctx.send(f"❌ The color `{color}` is invalid.")
        color = color_name

        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, url, return_type="image")
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        try:
            is_animated = img.is_animated
            img.info["duration"]
        except Exception:
            is_animated = False

        # animated image with a duration(gif)
        if is_animated:
            # convert each frame to the color
            res_frames = []
            durations = []
            for i in range(0, img.n_frames):
                img.seek(i)
                res_frame = img.copy()
                frame = colorify(res_frame, rgb)
                res_frames.append(frame)
                durations.append(img.info["duration"])

            # combine the frames back to a gif
            animated_img = BytesIO()
            await self.bot.loop.run_in_executor(
                None, save_transparent_gif, res_frames, durations, animated_img
            )
            animated_img.seek(0)
            file = disnake.File(fp=animated_img, filename="colorify.gif")

        # still image (png, jpeg, ..)
        else:
            res = colorify(img, rgb)
            file = await image_to_file(res, "colorify.png")

        await ctx.send(file=file)

    @commands.slash_command(name="pinkify")
    async def _pinkify(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage = None,
    ):
        """Turn an image pink."""
        await inter.response.defer()
        await self.colorify(inter, "pink", image.url)

    @commands.command(description="Turn an image pink.", usage="<image|url|emoji>")
    async def pinkify(self, ctx, url=None):
        async with ctx.typing():
            await self.colorify(ctx, "#FFA9D9", url)

    @commands.slash_command(name="rainbowfy")
    async def _rainbowfy(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage = None,
        saturation: int = None,
        lightness: int = None,
    ):
        """
        Turn an image to a rainbow GIF.

        Parameters
        ----------
        saturation: he rainbow saturation value between 0 and 100 (default: 50).
        lightness: The rainbow lightness value between 0 and 100 (default: 60).
        """
        args = ()
        if image.url:
            args += (image.url,)
        if saturation:
            args += ("-saturation", str(saturation))
        if lightness:
            args += ("-lightness", str(lightness))

        await inter.response.defer()
        await self.rainbowfy(inter, *args)

    @commands.command(
        name="rainbowfy",
        usage="<image|url|emoji> [-saturation value] [-lightness value]",
        description="Turn an image to a rainbow GIF.",
        help="""
            - `<url|image|emoji>`: the image you want to rainbowfy
            - `[-saturation|-s value]`: the rainbow saturation value between 0 and 100 (default: 50)
            - `[-lightness|-l value]`: the rainbow lightness value between 0 and 100 (default: 60)""",
    )
    async def p_rainbowfy(self, ctx, *args):
        async with ctx.typing():
            await self.rainbowfy(ctx, *args)

    async def rainbowfy(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("url", action="store", nargs="*")
        parser.add_argument("-saturation", action="store", default=50)
        parser.add_argument("-lightness", action="store", default=60)
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
            img, url = await get_image_from_message(ctx, url, return_type="image")
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        rainbow_img = await rainbowfy(img, saturation, lightness)
        file = disnake.File(fp=rainbow_img, filename="rainbowfy.gif")
        await ctx.send(file=file)


@in_executor()
def rainbowfy(img: Image.Image, saturation=50, lightness=60) -> Image.Image:
    """Turn an image to a rainbow GIF."""
    # check if the image is animated
    try:
        is_animated = img.is_animated
        img.info["duration"]
        # loop through the gif it has less than 8 frames
        if img.n_frames < 8:
            nb_colors = img.n_frames * (8 // img.n_frames + 1)
        else:
            nb_colors = img.n_frames
    except Exception:
        is_animated = False
        nb_colors = 16
        bytes = img_to_animated_gif(img)
        img = Image.open(BytesIO(bytes))

    # change each frame to a different color
    palette = get_rainbow_palette(
        nb_colors, saturation=saturation / 100, lightness=lightness / 100
    )
    res_frames = []
    durations = []
    for i, color in enumerate(palette):
        if is_animated:
            # loop in the gif if we exceed the number of frames
            img.seek(i % img.n_frames)
            _img = img.copy()
            durations.append(img.info["duration"])
        else:
            _img = img
            durations.append(0.01)
        res_frames.append(colorify(_img, color))

    # combine the frames back to a gif
    animated_img = BytesIO()
    save_transparent_gif(res_frames, durations, animated_img)
    animated_img.seek(0)

    return animated_img


def get_rainbow_palette(
    nb_colors: int, saturation: float = 1, lightness: float = 1
) -> list:
    """Get a list of rgb colors with a linear hue (saturation and lightness
    values should be between 0 and 1)"""
    palette = []
    for i in range(nb_colors):
        hue = i / nb_colors
        rgb_float = hsv_to_rgb((hue, saturation, lightness))
        rgb = [round(c * 255) for c in rgb_float]
        palette.append(tuple(rgb))
    return palette


def colorify(img: Image.Image, color: tuple) -> Image.Image:
    """Blend the image with a solid color image with the given color image.
    The blend mode used is 'hard light'"""

    # background image
    img = img.convert("RGBA")
    img_array = np.array(img)

    # save the alpha channel
    alpha_channel = None
    if img_array.shape[-1] == 4:
        alpha_channel = img.split()[-1]
    elif img_array.shape[-1] != 3:
        raise ValueError(
            f"Incorrect number of channels in the image\
            (received: {img_array.shape[-1]}, must be 3 or 4)"
        )

    # convert to grayscale
    gray_img = img.convert("L").convert("RGBA")
    gray_array = np.array(gray_img)
    gray_array = gray_array.astype(float)

    # make the filter image: a solid image with the color input
    filter = Image.new("RGBA", img.size, color)
    filter_array = np.array(filter)
    filter_array = filter_array.astype(float)

    # Blend the images
    blended_img_array = hard_light(gray_array, filter_array, 1)
    blended_img_array = np.uint8(blended_img_array)
    blended_img = Image.fromarray(blended_img_array)

    # put the alpha values back
    if alpha_channel:
        blended_img.putalpha(alpha_channel)
    return blended_img


def setup(bot: commands.Bot):
    bot.add_cog(Colorify(bot))
