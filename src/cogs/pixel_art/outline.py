import functools
import disnake
from PIL import Image, ImageColor
from disnake.ext import commands
from io import BytesIO

from utils.arguments_parser import parse_outline_args
from utils.discord_utils import autocomplete_palette, format_number, get_image_from_message, image_to_file
from utils.image.image_utils import (
    add_outline,
    remove_white_space,
    get_pxls_color,
    is_hex_color,
)


class Outline(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="outline")
    async def _outline(
            self,
            inter: disnake.AppCmdInter,
            color: str = commands.Param(autocomplete=autocomplete_palette),
            image: str = None,
            sparse: bool = False,
            width: int = commands.Param(default=None, gt=0, le=32),
    ):
        """Add an outline to an image.

        Parameters
        ----------
        color: Color of the outline, can be the name of a pxlsColor or a hexcolor.
        image: The URL of the image you want to outline.
        sparse: To have a sparse outline (outline without the corners) (default: False).
        width: The width of the outline in pixels. (default: 1)
        """
        await inter.response.defer()
        args = (color,)
        if image:
            args += (image,)
        if sparse:
            args += ("-sparse",)
        if width:
            args += ("-width", str(width))
        await self.outline(inter, *args)

    @commands.command(
        name="outline",
        description="Add an outline to an image.",
        usage="<color> <url|image> [-sparse] [-width <number>]",
        aliases=["border"],
        help="""- `<color>`: color of the outline, can be the name of a pxlsColor or a hexcolor
                  - `<url|image>`: an image URL or an attached image
                  - `[-sparse]`: to have a sparse outline (outline without the corners)
                  - `[-width <number>]`: the width of the outline in pixels""",
    )
    async def p_outline(self, ctx, *args):
        async with ctx.typing():
            await self.outline(ctx, *args)

    async def outline(self, ctx, *args):
        """command to add an to an image"""
        try:
            param = parse_outline_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        color = " ".join(param["color"])
        url = param["url"]
        sparse = param["sparse"]
        width = param["width"]
        if width > 32:
            return await ctx.send("❌ This outline width is too big (max: 32).")
        elif width < 1:
            return await ctx.send("❌ This outline width is too small (min: 1).")

        # get the rgba from the color input
        try:
            color, rgba = get_pxls_color(color)
        except ValueError:
            if is_hex_color(color):
                rgba = ImageColor.getcolor(color, "RGBA")
            else:
                return await ctx.send(f"❌ The color `{color}` is invalid.\n(use quotes if the color has 2 or more words)")

        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        input_image = Image.open(BytesIO(img_bytes))
        func = functools.partial(add_outline, input_image, rgba, not (sparse), width)
        image_with_outline = await self.bot.loop.run_in_executor(None, func)
        file = await self.bot.loop.run_in_executor(
            None, image_to_file, image_with_outline, "outline.png"
        )

        await ctx.send(file=file)

    @commands.slash_command(name="crop")
    async def _crop(self, inter: disnake.AppCmdInter, image: str = None):
        """Remove the 'white space' from a PNG image.

        Parameters
        ----------
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.crop(inter, image)

    @commands.command(
        name="crop",
        usage="<image|url>",
        description="Remove the empty space from a PNG image.",
        help="""- `<url|image>`: an image URL or an attached image""",
    )
    async def p_crop(self, ctx, url=None):
        async with ctx.typing():
            await self.crop(ctx, url)

    async def crop(self, ctx, url=None):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        input_image = Image.open(BytesIO(img_bytes))
        image_cropped = await self.bot.loop.run_in_executor(
            None, remove_white_space, input_image
        )
        ratio = (image_cropped.width * image_cropped.height) / (input_image.width * input_image.height)
        embed = disnake.Embed(title="Crop", color=0x66C5CC)
        if ratio == 1:
            embed.description = "There was nothing to crop here. <a:bruhkitty:880829401359589446>"
        else:
            embed.description = f"The cropped image is **{format_number((1-ratio)*100)}%** smaller.\n"
            embed.description += "`{0.width}x{0.height}` → `{1.width}x{1.height}`".format(
                input_image, image_cropped
            )
        file = await self.bot.loop.run_in_executor(
            None, image_to_file, image_cropped, "cropped.png", embed
        )

        await ctx.send(file=file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Outline(bot))
