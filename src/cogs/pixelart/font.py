from PIL import ImageColor
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from utils.arguments_parser import parse_pixelfont_args
from utils.font.font_manager import get_all_fonts, PixelText
from utils.discord_utils import image_to_file
from utils.image.image_utils import get_pxls_color, is_hex_color
from utils.setup import GUILD_IDS


class Font(commands.Cog):
    def __init__(self, client):
        self.client = client

    fonts = get_all_fonts()
    fonts.insert(0, "all")

    @cog_ext.cog_slash(
        name="pixelfont",
        description="Convert a text to pixel art.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="text",
                description="The text to convert to pixel art.",
                option_type=3,
                required=True,
            ),
            create_option(
                name="font",
                description="The name of the font (default: all).",
                option_type=3,
                required=False,
                choices=[create_choice(name=f, value=f) for f in fonts],
            ),
            create_option(
                name="color",
                description="The color you want the text to be (default: black).",
                option_type=3,
                required=False,
            ),
            create_option(
                name="bgcolor",
                description="The color for the text background (none = transparent) (default: white).",
                option_type=3,
                required=False,
            ),
        ],
    )
    async def _pixelfont(self, ctx: SlashContext, text, font=None, color=None, bgcolor=None):
        await ctx.defer()
        args = (text,)
        if font:
            if font == "all":
                font = "*"
            args += ("-font", font)
        if color:
            args += ("-color", color)
        if bgcolor:
            args += ("-bgcolor", bgcolor)
        await self.pixelfont(ctx, *args)

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
            try:
                font_rgba = get_pxls_color(font_color)
            except ValueError:
                if font_color == "none":
                    font_rgba = (0, 0, 0, 0)
                elif is_hex_color(font_color):
                    font_rgba = ImageColor.getcolor(font_color, "RGBA")
                else:
                    return await ctx.send(f"❌ The font color `{font_color}` is invalid.")
        else:
            font_rgba = None

        background_color = arguments.bgcolor
        if background_color:
            # get the rgba from the color input
            background_color = " ".join(background_color).lower()
            try:
                bg_rgba = get_pxls_color(background_color)
            except ValueError:
                if background_color == "none":
                    bg_rgba = (0, 0, 0, 0)
                elif is_hex_color(background_color):
                    bg_rgba = ImageColor.getcolor(background_color, "RGBA")
                else:
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
                files.append(image_to_file(im, font_name + ".png"))

        # send the image(s)
        await ctx.send(files=files)

    @commands.command(description="Show the list of the fonts available.")
    async def fonts(self, ctx):
        fonts = get_all_fonts()
        if len(fonts) == 0:
            return await ctx.send("❌ I can't find any font :(")

        msg = "**Available fonts:**\n"
        for font in fonts:
            msg += "\t• `" + font + "`\n"
        return await ctx.send(msg)


def setup(client):
    client.add_cog(Font(client))
