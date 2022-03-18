import disnake
import numpy as np
import time
from PIL import Image
from disnake.ext import commands

from utils.arguments_parser import MyParser
from utils.discord_utils import (
    autocomplete_builtin_palettes,
    format_number,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.image.image_utils import (
    get_color,
    rgb_to_hex,
    get_builtin_palette,
)
from utils.pxls.template import reduce, get_rgba_palette
from utils.setup import stats


class Reduce(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="reduce")
    async def _reduce(
        self,
        inter: disnake.AppCmdInter,
        image: str = None,
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
        image: The URL of the image you want to templatize.
        palette: A list of colors (name of hex) seprated by a comma (!<color> = remove color). (default: pxls)
        matching: The color matching algorithm to use. (default: accurate)
        """
        await inter.response.defer()
        await self.reduce(inter, image, palette, matching)

    @commands.command(
        name="reduce",
        description="Reduce an image's colors to fit a specific palette.",
        usage="<image|url> [palette] [-fast]",
        help="""
            - `<image|url>`: an image URL or an attached file
            - `[palette]`: a list of color (name or hex) separated by a comma. (default: pxls (current))
            There are also built-in palettes: pxls, pxls_old, c1, grayscale, browns, yellows, greens, teals, blues, pinks, reds
            Note: Use `!` in front of a color to remove it.
            - `[-fast]`: to use the fast (but less accurate) color matching algorithm
        """,
    )
    async def p_reduce(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("palette", action="store", nargs="*")
        parser.add_argument("-fast", action="store_true", required=False, default=False)

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
        matching = "fast" if parsed_args.fast else "accurate"
        async with ctx.typing():
            await self.reduce(
                ctx,
                input_url,
                palette,
                matching,
            )

    async def reduce(self, ctx, image_url, palette, matching):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, image_url, accept_emojis=False)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        start = time.time()

        # check on the matching
        if matching is None:
            matching = "accurate"  # default = 'accurate'

        palette_names = []
        # check on the palette
        if not palette:
            palette_names.append("pxls (current)")
            rgba_palette = get_rgba_palette()
            hex_palette = None  # default pxls
        else:
            # format the colors
            palette = palette.lower()
            palette_input = palette.split(",")
            palette_input = [c.strip(" ") for c in palette_input]

            rgba_list = []
            banned_rgba = []
            # search for palette names
            for color in palette_input[:]:
                ban_color = False
                if color.startswith("!"):
                    ban_color = True
                    color = color[1:]
                found_palette = get_builtin_palette(color, as_rgba=True)
                if found_palette:
                    if ban_color:
                        palette_input.remove("!" + color)
                        banned_rgba += found_palette
                        palette_names.append(f"__No {color.title()}__")
                    else:
                        palette_input.remove(color)

                        rgba_list += found_palette
                        palette_names.append(f"__{color.title()}__")

            # search for colors names/hex
            for i, color in enumerate(palette_input):
                color = color.strip(" ")
                ban_color = False
                if color.startswith("!"):
                    ban_color = True
                    color = color[1:]
                color_name, rgba = get_color(color)
                if rgba is None:
                    return await ctx.send(f"❌ The color `{color}` is invalid.")
                if ban_color:
                    banned_rgba.append(rgba)
                    palette_names.append("No " + color_name)
                else:
                    palette_names.append(color_name)
                    rgba_list.append(rgba)

            # remove duplicates
            palette_names = list(dict.fromkeys(palette_names))
            rgba_list = list(dict.fromkeys(rgba_list))

            # remove banned colors
            if banned_rgba:
                palette_names.insert(0, "Pxls (current)")
                rgba_list += list([tuple(c) for c in get_rgba_palette()])
                rgba_list = [c for c in rgba_list if c not in banned_rgba]

            if len(rgba_list) == 0:
                return await ctx.send(":x: This palette is empty.")
            # format the data
            hex_palette = [rgb_to_hex(rgba[:3]) for rgba in rgba_list]
            rgba_palette = np.array(rgba_list)

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
