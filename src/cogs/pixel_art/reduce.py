import time

import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from utils.discord_utils import (
    autocomplete_builtin_palettes,
    format_number,
    get_image_from_message,
    image_to_file,
)
from utils.image.image_utils import get_colors_from_input
from utils.pxls.template import get_rgba_palette, reduce
from utils.setup import stats


class Reduce(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="reduce")
    async def _reduce(
        self,
        inter: disnake.AppCmdInter,
        image_link: str = commands.Param(name="image-link", default=None),
        image_file: disnake.Attachment = commands.Param(name="image-file", default=None),
        palette: str = commands.Param(
            default=None, autocomplete=autocomplete_builtin_palettes
        ),
        matching: str = commands.Param(
            default=None,
            choices={"Accurate (default)": "accurate", "Fast (faster)": "fast"},
        ),
    ):
        """Reduce an image's colors to fit a specific palette.

        Parameters
        ----------
        image_link: The URL of the image you want to templatize (can be a template link).
        image_file: An image file you want to templatize.
        palette: A list of colors (name or hex) seprated by a comma (!<color> = remove color). (default: pxls)
        matching: The color matching algorithm to use. (default: accurate)
        """
        if image_file:
            image_link = image_file.url
        await inter.response.defer()
        await self.reduce(inter, image_link, palette, matching)

    async def reduce(self, ctx, image_url, palette, matching):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, image_url, accept_emojis=False)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        start = time.time()

        # check on image size
        limit = int(15e6)
        if img.width * img.height > limit:
            msg = f"This image exceeds the limit of **{format_number(limit)}** pixels for this command.\n"
            return await ctx.send(
                embed=disnake.Embed(
                    title=":x: Size limit exceeded",
                    description=msg,
                    color=disnake.Color.red(),
                )
            )
        # check on the matching
        if matching is None:
            matching = "accurate"  # default = 'accurate'

        # get the palette
        if not palette:
            palette_names = ["pxls (current)"]
            rgba_palette = get_rgba_palette()
            hex_palette = None  # default pxls
        else:
            try:
                rgba_palette, hex_palette, palette_names = get_colors_from_input(
                    palette, accept_colors=True, accept_palettes=True
                )
            except ValueError as e:
                return await ctx.send(f":x: {e}")

        # reduce the image to the pxls palette
        img_array = np.array(img)
        reduced_array = await self.bot.loop.run_in_executor(
            None, reduce, img_array, rgba_palette, matching
        )

        total_amount = np.sum(reduced_array != 255)
        total_amount = format_number(int(total_amount))
        end = time.time()

        # create and send the image
        embed = disnake.Embed(title="**Reduce**", color=0x66C5CC)
        embed.description = f"**Matching**: `{matching}`\n"
        embed.description += f"**Palette**: {', '.join(palette_names)}\n"
        embed.description += f"**Size**: {total_amount} pixels ({img.width}x{img.height})"
        embed.set_footer(text=f"Reduced in {round((end-start),3)}s")

        reduced_image = Image.fromarray(stats.palettize_array(reduced_array, hex_palette))
        reduced_file = await image_to_file(reduced_image, "reduced.png", embed)

        await ctx.send(embed=embed, files=[reduced_file])


def setup(bot: commands.Bot):
    bot.add_cog(Reduce(bot))
