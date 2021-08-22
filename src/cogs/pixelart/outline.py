import functools

from PIL import Image, ImageColor
from discord.ext import commands
from io import BytesIO

from utils.arguments_parser import parse_outline_args
from utils.discord_utils import get_image_from_message, image_to_file
from utils.image.image_utils import add_outline, remove_white_space,\
    get_pxls_color, is_hex_color


class Outline(commands.Cog):

    def __init__(self, client):
        self.client = client

    ### Commands ###
    @commands.command(
        description = "Add an outline to an image.",
        usage="<color> <url|image> [-sparse] [-width <number>]",
        aliases = ["border"],
        help = """- `<color>`: color of the outline, can be the name of a pxlsColor or a hexcolor
                  - `<url|image>`: an image URL or an attached image
                  - `[-sparse]`: to have a sparse outline (outline without the corners)
                  - `[-width <number>]`: the width of the outline in pixels"""
        )
    async def outline(self,ctx,*args):
        ''' command to add an to an image '''
        try:
            param = parse_outline_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        color = " ".join(param["color"])
        url = param["url"]
        sparse = param["sparse"]
        width = param["width"]

        # get the rgba from the color input
        try:
            rgba = get_pxls_color(color)
        except ValueError:
            if is_hex_color(color):
                rgba = ImageColor.getcolor(color,"RGBA")
            else:
                return await ctx.send(f'❌ The color {color} is invalid.')

        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        func = functools.partial(add_outline,input_image,rgba,not(sparse),width)
        async with ctx.typing():
            image_with_outline = await self.client.loop.run_in_executor(None,func)
            file = await self.client.loop.run_in_executor(None,image_to_file,image_with_outline,"outline.png")

        await ctx.send(file=file)

    @commands.command(usage = "<image or url>",
        description = "Remove the 'white space' from a PNG image.",
        help = """- `<url|image>`: an image URL or an attached image"""
        )
    async def crop(self,ctx,url=None):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        async with ctx.typing():
            image_cropped = await self.client.loop.run_in_executor(None,remove_white_space,input_image)
            file = await self.client.loop.run_in_executor(None,image_to_file,image_cropped,"cropped.png")

        await ctx.send(file=file)

def setup(client):
    client.add_cog(Outline(client))
