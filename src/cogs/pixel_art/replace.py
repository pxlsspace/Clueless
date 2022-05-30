import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from utils.discord_utils import (
    InterImage,
    autocomplete_palette_with_none,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.image.image_utils import get_color


class Replace(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="replace")
    async def _replace(
        self,
        inter: disnake.AppCmdInter,
        color1: str = commands.Param(autocomplete=autocomplete_palette_with_none),
        color2: str = commands.Param(autocomplete=autocomplete_palette_with_none),
        image: InterImage = None,
    ):
        """Replace a color by an other in an image.
        Parameters
        ----------
        color1: The name/hex/index of the color to replace (none = transparent).
        color2: The name/hex/index of the new color (none = transparent).
        """
        await inter.response.defer()
        await self.replace(inter, color1, color2, image.url)

    @commands.command(
        name="replace",
        usage="<color1> <color2> <image|url>",
        description="Replace a color by an other in an image.",
        help="""- `<color1>`: the name/hex/index of the color to replace (none = transparent)
        - `<color2>`: the name/hex/index of the new color (none = transparent)
        - `<url|image>`: an image URL or attached image""",
    )
    async def p_replace(self, ctx, *args):
        colors, urls = get_urls_from_list(list(args))
        # colors = " ".join(colors)
        # colors = colors.split(",")
        if len(colors) >= 2:
            color1 = colors[0]
            color2 = colors[1]
        elif len(colors) == 1:
            raise commands.MissingRequiredArgument(commands.Param(name="color2"))
        else:
            raise commands.MissingRequiredArgument(commands.Param(name="color1"))
        url = None
        if urls:
            url = urls[0]

        async with ctx.typing():
            await self.replace(ctx, color1, color2, url)

    async def replace(self, ctx, color1, color2, url=None):
        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        rgbas = []
        color_names = []
        for color in [color1, color2]:
            color = color.replace(",", "")
            if color.lower().strip() in ["none", "transparent"]:
                color_name = "Transparent"
                rgba = (0, 0, 0, 0)
            else:
                color_name, rgba = get_color(color)
                if rgba is None:
                    return await ctx.send(
                        f"❌ The color `{color}` is invalid.\n(use quotes if the color has 2 words)"
                    )
            rgbas.append(rgba)
            color_names.append(color_name)

        array = np.array(input_image)
        rgba1 = rgbas[0]
        rgba2 = rgbas[1]
        if rgba1 == (0, 0, 0, 0):
            mask = array[:, :, -1] <= 128
        else:
            mask = np.all(array == rgba1, axis=2)
        array[:, :, :4][mask] = rgba2

        res_image = Image.fromarray(array)

        embed = disnake.Embed(
            title="Replace",
            color=0x66C5CC,
            description=f"`{color_names[0]}` → `{color_names[1]}`",
        )

        file = await image_to_file(res_image, "replace.png", embed)
        await ctx.send(file=file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Replace(bot))
