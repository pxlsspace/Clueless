from PIL import ImageColor
import discord
from discord.ext import commands
from io import BytesIO

from utils.arguments_parser import parse_pixelfont_args
from utils.font.font_manager import *
from utils.discord_utils import image_to_file
from utils.image_utils import get_pxls_color, is_hex_color

class Font(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(
        description = "Convert a text to pixel art.",
        aliases = ["pf","pixeltext"],
        usage = "<text> <-font <name|*>> [-color <color|none>] [-bgcolor <color|none>]",
        help = """- `<text>` a text to convert to pixel art
                  - `[-font <name|*>]`: the name of the font (`*` will use all the fonts available)
                  - `[-fontcolor]`: the color you want the text to be
                  - `[-bgcolor]`: the color for the background around the text
                  (the colors can be a pxls color name, a hex color, or `none` if you want transparent)"""
    )
    async def pixelfont(self,ctx,*args):
        try:
            arguments = parse_pixelfont_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}\nUsage: `{ctx.prefix}{ctx.command.name} {ctx.command.usage}`')

        fonts = get_all_fonts()
        if len(fonts) == 0:
            return await ctx.send("❌ I can't find any fonts :(")


        font = arguments.font
        if not(font in fonts) and font != "*":
            msg = "❌ Can't find this font.\n"
            msg += "**Available fonts:**\n"
            for font in fonts:
                msg += "\t• `" + font + "`\n"
            return await ctx.send(msg)

        font_color = arguments.color
        if font_color == "none":
            font_rgba = (0,0,0,0)

        elif font_color != None:
            # get the rgba from the color input
            try:
                font_rgba = get_pxls_color(font_color)
            except ValueError:
                if is_hex_color(font_color):
                    font_rgba = ImageColor.getcolor(font_color,"RGBA")
                else:
                    return await ctx.send(f'❌ The font color {font_color} is invalid.')
        else:
            font_rgba = None

        background_color = arguments.bgcolor
        if background_color == "none":
            bg_rgba = (0,0,0,0)

        elif background_color != None:
            # get the rgba from the color input
            try:
                bg_rgba = get_pxls_color(background_color)
            except ValueError:
                if is_hex_color(background_color):
                    bg_rgba = ImageColor.getcolor(background_color,"RGBA")
                else:
                    return await ctx.send(f'❌ The background color {background_color} is invalid.')
        else:
            bg_rgba = None

        text = " ".join(arguments.text)
        images = []
        if font == "*":
            for font_name in fonts:
                try:
                    images.append([font_name,PixelText(text,font_name,font_rgba,bg_rgba).get_image()])
                except ValueError as e:
                    return await ctx.send(f'❌ {e}')
        else:
            images.append([font,PixelText(text,font,font_rgba,bg_rgba).get_image()])

        # create a list of discord File to send
        files = []
        for image in images:
            font_name = image[0]
            im = image[1]
            if im != None:
                files.append(image_to_file(im,font_name+".png"))

        # send the image(s)
        await ctx.send(files=files)
                    
    @commands.command(description = "Show the list of the fonts available.")
    async def fonts(self,ctx):
        fonts = get_all_fonts()
        if len(fonts) == 0:
            return await ctx.send("❌ I can't find any font :(")

        msg = "**Available fonts:**\n"
        for font in fonts:
            msg += "\t• `" + font + "`\n"
        return await ctx.send(msg)

def setup(client):
    client.add_cog(Font(client))