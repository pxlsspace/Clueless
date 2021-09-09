import functools
from PIL import Image, ImageColor
from discord.ext import commands
from io import BytesIO
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from utils.arguments_parser import parse_outline_args
from utils.discord_utils import get_image_from_message, image_to_file
from utils.image.image_utils import add_outline, remove_white_space,\
    get_pxls_color, is_hex_color
from utils.setup import GUILD_IDS

class Outline(commands.Cog):

    def __init__(self, client):
        self.client = client

    ### Commands ###
    @cog_ext.cog_slash(name="outline",
        description="Convert time formats.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="color",
            description="Color of the outline, can be the name of a pxlsColor or a hexcolor.",
            option_type=3,
            required=True
        ),
        create_option(
            name="image",
            description="The URL of the image you want to outline.",
            option_type=3,
            required=False
        ),
        create_option(
            name="sparse",
            description="To have a sparse outline (outline without the corners).",
            option_type=5,
            required=False
        ),
        create_option(
            name="width",
            description="The width of the outline in pixels.",
            option_type=4,
            required=False
        )]
    )
    async def _outline(self,ctx:SlashContext,color,image=None,sparse=False,width=None):
        await ctx.defer()
        args = (color,)
        if image:
            args += (image,)
        if sparse:
            args += ("-sparse",)
        if width:
            args += ("-width",str(width))
        await self.outline(ctx,*args)

    @commands.command(
        name = "outline",
        description = "Add an outline to an image.",
        usage="<color> <url|image> [-sparse] [-width <number>]",
        aliases = ["border"],
        help = """- `<color>`: color of the outline, can be the name of a pxlsColor or a hexcolor
                  - `<url|image>`: an image URL or an attached image
                  - `[-sparse]`: to have a sparse outline (outline without the corners)
                  - `[-width <number>]`: the width of the outline in pixels"""
        )
    async def p_outline(self,ctx,*args):
        async with ctx.typing():
            await self.outline(ctx,*args)
    
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
        if width > 32:
            return await ctx.send("❌ This outline width is too big (max: 32).")

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
        image_with_outline = await self.client.loop.run_in_executor(None,func)
        file = await self.client.loop.run_in_executor(None,image_to_file,image_with_outline,"outline.png")

        await ctx.send(file=file)

    @cog_ext.cog_slash(
        name="crop",
        description="Remove the 'white space' from a PNG image.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="image",
                description="The URL of the image.",
                option_type=3,
                required=False
            )
        ]
    )
    async def _crop(self,ctx:SlashContext,image=None):
        await ctx.defer()
        await self.crop(ctx,image)

    @commands.command(
        name="crop",
        usage = "<image|url>",
        description = "Remove the 'white space' from a PNG image.",
        help = """- `<url|image>`: an image URL or an attached image"""
        )
    async def p_crop(self,ctx,url=None):
        async with ctx.typing():
            await self.crop(ctx,url)

    async def crop(self,ctx,url=None):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        image_cropped = await self.client.loop.run_in_executor(None,remove_white_space,input_image)
        file = await self.client.loop.run_in_executor(None,image_to_file,image_cropped,"cropped.png")

        await ctx.send(file=file)

def setup(client):
    client.add_cog(Outline(client))
