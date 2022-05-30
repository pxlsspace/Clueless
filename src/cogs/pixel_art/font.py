import disnake
from disnake.ext import commands

from utils.arguments_parser import parse_pixelfont_args
from utils.discord_utils import autocomplete_palette_with_none, image_to_file
from utils.font.font_manager import PixelText, get_all_fonts, get_allowed_fonts
from utils.image.image_utils import get_color


class Font(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    fonts = get_all_fonts()
    fonts.insert(0, "all")

    @commands.slash_command(name="pixelfont")
    async def _pixelfont(
        self,
        inter: disnake.AppCmdInter,
        text: str,
        font: str = commands.Param(choices=fonts, default=None),
        color: str = commands.Param(
            autocomplete=autocomplete_palette_with_none, default=None
        ),
        bgcolor: str = commands.Param(
            autocomplete=autocomplete_palette_with_none, default=None
        ),
    ):
        """Convert a text to pixel art.

        Parameters
        ----------
        text: The text to convert to pixel art.
        font: The name of the font (default: all).
        color: The color you want the text to be (default: black).
        bgcolor: The color for the text background (none = transparent) (default: white).
        """
        await inter.response.defer()
        args = (text,)
        if font:
            if font == "all":
                font = "*"
            args += ("-font", font)
        if color:
            args += ("-color", color)
        if bgcolor:
            args += ("-bgcolor", bgcolor)
        await self.pixelfont(inter, *args)

    @commands.command(
        name="pixelfont",
        description="Convert a text to pixel art.",
        aliases=["pf", "pixeltext"],
        usage="<text> [-font <name|*>] [-color <color|none>] [-bgcolor <color|none>]",
        help="""- `<text>` a text to convert to pixel art
                  - `[-font name|*]`: the name of the font (`*` will use all the fonts available)
                  - `[-color]`: the color you want the text to be
                  - `[-bgcolor]`: the color for the background around the text
                  (the colors can be a pxls color name, a hex color, or `none` if you want transparent)""",
    )
    async def p_pixelfont(self, ctx, *, args):
        args = args.split(" ")
        async with ctx.typing():
            await self.pixelfont(ctx, *args)

    async def pixelfont(self, ctx, *args):
        try:
            arguments = parse_pixelfont_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        fonts = get_all_fonts()
        if len(fonts) == 0:
            return await ctx.send("❌ I can't find any fonts :(")

        font = arguments.font
        if not (font in fonts) and font != "*":
            msg = "❌ Can't find this font.\n"
            msg += "**Available fonts:**\n"
            for font in fonts:
                msg += "\t• `" + font + "`\n"
            return await ctx.send(msg)

        font_color = arguments.color
        if font_color:
            # get the rgba from the color input
            font_color = " ".join(font_color).lower()
            if font_color == "none":
                font_rgba = (0, 0, 0, 0)
            else:
                font_color_name, font_rgba = get_color(font_color)
                if font_rgba is None:
                    return await ctx.send(f"❌ The font color `{font_color}` is invalid.")
        else:
            font_rgba = None

        background_color = arguments.bgcolor
        if background_color:
            # get the rgba from the color input
            background_color = " ".join(background_color).lower()
            if background_color == "none":
                bg_rgba = (0, 0, 0, 0)
            else:
                background_color_name, bg_rgba = get_color(background_color)
                if bg_rgba is None:
                    return await ctx.send(
                        f"❌ The background color `{background_color}` is invalid."
                    )
        else:
            bg_rgba = None

        text = " ".join(arguments.text)
        images = []
        if font == "*":
            for font_name in fonts:
                try:
                    images.append(
                        [
                            font_name,
                            PixelText(text, font_name, font_rgba, bg_rgba).get_image(),
                        ]
                    )
                except ValueError as e:
                    return await ctx.send(f"❌ {e}")
            # check that we have at least one image in the image list
            if all([im[1] is None for im in images]):
                return await ctx.send("❌ These characters weren't found in any font.")
        else:
            images.append([font, PixelText(text, font, font_rgba, bg_rgba).get_image()])
            # check that we have at least one image in the image list
            if all([im[1] is None for im in images]):
                return await ctx.send("❌ These characters weren't found in the font.")

        # create a list of discord File to send
        files = []
        for image in images:
            font_name = image[0]
            im = image[1]
            if im is not None:
                file = await image_to_file(im, font_name + ".png")
                files.append(file)

        # send the image(s)
        await ctx.send(files=files)

    @commands.command(description="Show the list of the fonts available.")
    async def fonts(self, ctx):
        fonts = get_all_fonts()
        allowed_fonts = get_allowed_fonts()
        if len(fonts) == 0:
            return await ctx.send("❌ I can't find any font :(")
        msg = ""
        for font in fonts:
            if font in allowed_fonts:
                msg += f"\t• **`{font}`** *\n"

            else:
                msg += f"\t• `{font}`\n"
        embed = disnake.Embed(title="Available Fonts", color=0x66C5CC, description=msg)
        embed.set_footer(text=f"* = available for {ctx.prefix}setfont\n")
        return await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Font(bot))
