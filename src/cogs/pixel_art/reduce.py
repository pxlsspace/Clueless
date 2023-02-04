import time

import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from utils.arguments_parser import MyParser
from utils.discord_utils import (
    autocomplete_builtin_palettes,
    format_number,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.image.image_utils import get_colors_from_input
from utils.pxls.template import ColorDist, get_rgba_palette, reduce
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
        dither: float = commands.Param(default=0, le=1, ge=0),
    ):
        """Reduce an image's colors to fit a specific palette.

        Parameters
        ----------
        image_link: The URL of the image you want to templatize (can be a template link).
        image_file: An image file you want to templatize.
        palette: A list of colors (name or hex) seprated by a comma (!<color> = remove color). (default: pxls)
        matching: The color matching algorithm to use. (default: accurate)
        dither: The strength of the dithering, between 0-1. (default: 0)
        """
        if image_file:
            image_link = image_file.url
        await inter.response.defer()
        matching = ColorDist.EUCLIDEAN if matching == "fast" else ColorDist.CIEDE2000
        await self.reduce(inter, image_link, palette, matching, dither)

    @commands.command(
        name="reduce",
        description="Reduce an image's colors to fit a specific palette.",
        usage="<image|url> [palette] [-fast] [-dither]",
        help="""
            - `<image|url>`: an image URL or an attached file
            - `[palette]`: a list of color (name or hex) separated by a comma. (default: pxls (current))
            There are also built-in palettes: pxls, pxls_old, c1, grayscale, browns, yellows, greens, teals, blues, pinks, reds
            Note: Use `!` in front of a color to remove it.
            - `[-fast]`: to use the fast (but less accurate) color matching algorithm
            - `[-dither]`: strength of the dithering, between 0 and 1. 0 means no dithering.
        """,
    )
    async def p_reduce(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("palette", action="store", nargs="*")
        parser.add_argument("-fast", action="store_true", required=False, default=False)
        parser.add_argument("-dither", action="store", default=0, type=float)

        try:
            parsed_args, unknown = parser.parse_known_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        palette, urls = get_urls_from_list(parsed_args.palette)
        input_url = urls[0] if urls else None

        if palette:
            palette = " ".join(palette)
        else:
            palette = None
        matching = ColorDist.EUCLIDEAN if parsed_args.fast else ColorDist.CIEDE2000
        dither = min(1, max(0, parsed_args.dither))
        async with ctx.typing():
            await self.reduce(ctx, input_url, palette, matching, dither)

    async def reduce(self, ctx, image_url, palette, matching, dither):
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
        rgb_palette = rgba_palette[:, :3]
        reduced_array = await self.bot.loop.run_in_executor(
            None, reduce, img_array, rgb_palette, matching, dither
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
