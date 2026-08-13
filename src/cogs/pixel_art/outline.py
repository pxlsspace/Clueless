import functools

import disnake
from disnake.ext import commands

from utils.discord_utils import (
    InterImage,
    autocomplete_palette,
    format_number,
    get_image_from_message,
    image_to_file,
)
from utils.image.image_utils import add_outline, get_color, remove_white_space


class Outline(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="outline")
    async def _outline(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage,
        color: str = commands.Param(autocomplete=autocomplete_palette),
        sparse: bool = False,
        width: int = commands.Param(default=1, gt=0, le=32),
    ):
        """Add an outline to an image.

        Parameters
        ----------
        color: Color of the outline, can be the name of a pxlsColor or a hexcolor.
        sparse: To have a sparse outline (outline without the corners) (default: False).
        width: The width of the outline in pixels. (default: 1)
        """
        await inter.response.defer()
        await self.outline(inter, color, image.url, sparse, width)

    async def outline(self, ctx, color, url=None, sparse=False, width=1):
        """command to add an to an image"""

        if width > 32:
            return await ctx.send("❌ This outline width is too big (max: 32).")
        elif width < 1:
            return await ctx.send("❌ This outline width is too small (min: 1).")

        # get the rgba from the color input
        color_name, rgba = get_color(color)
        if rgba is None:
            return await ctx.send(f"❌ The color `{color}` is invalid.")

        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        func = functools.partial(add_outline, input_image, rgba, not (sparse), width)
        image_with_outline = await self.bot.loop.run_in_executor(None, func)
        file = await image_to_file(image_with_outline, "outline.png")

        await ctx.send(file=file)

    @commands.slash_command(name="crop")
    async def _crop(
        self,
        inter: disnake.AppCmdInter,
        image: InterImage,
    ):
        """Remove the 'white space' from a PNG image."""
        await inter.response.defer()
        await self.crop(inter, image.url)

    async def crop(self, ctx, url=None):
        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        image_cropped = await self.bot.loop.run_in_executor(
            None, remove_white_space, input_image
        )
        ratio = (image_cropped.width * image_cropped.height) / (
            input_image.width * input_image.height
        )
        embed = disnake.Embed(title="Crop", color=0x66C5CC)
        if ratio == 1:
            embed.description = (
                "There was nothing to crop here. <:bruhkitty:943594789532737586>"
            )
        else:
            embed.description = (
                f"The cropped image is **{format_number((1-ratio)*100)}%** smaller.\n"
            )
            embed.description += "`{0.width}x{0.height}` → `{1.width}x{1.height}`".format(
                input_image, image_cropped
            )
        file = await image_to_file(image_cropped, "cropped.png", embed)

        await ctx.send(file=file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Outline(bot))
