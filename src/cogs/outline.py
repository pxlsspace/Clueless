import re
import discord

from PIL import Image, ImageColor
from discord.ext import commands
from io import BytesIO

from utils.setup import stats
from utils.arguments_parser import parse_outline_args
from utils.discord_utils import get_image_from_message, image_to_file

HEX_COLOR_REGEX = r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'


class Outline(commands.Cog):

    def __init__(self, client):
        self.stats = stats
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
            rgba = self.get_pxls_color(color)
        except ValueError:
            if self.is_hex_color(color):
                rgba = ImageColor.getcolor(color,"RGBA")
            else:
                return await ctx.send(f'❌ The color {color} is invalid.')

        # get the input image
        try:
            img_bytes, url = get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        image_with_outline = self.add_outline(input_image,rgba,not(sparse),width)

        file = image_to_file(image_with_outline,"outline.png")
        await ctx.send(file=file)

    @commands.command(usage = "<image or url>",
        description = "Remove the 'white space' from a PNG image.",
        help = """- `<url|image>`: an image URL or an attached image"""
        )
    async def crop(self,ctx,url=None):
        # get the input image
        try:
            img_bytes, url = get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        image_cropped = self.remove_white_space(input_image)

        file = image_to_file(image_cropped,"cropped.png")
        await ctx.send(file=file)

    ### Helper functions ###
    @staticmethod
    def add_outline(original_image,color,full=True,outline_width=1,crop=True):
        ''' add a border/outline around a transparent png '''
        # Convert to RGBA to manipulate the image easier
        original_image = original_image.convert('RGBA')
        background = original_image.copy()
        #crate a background transparent image to create the stroke in it
        background=Image.new("RGBA", (original_image.size[0]+outline_width*2, original_image.size[1]+outline_width*2), (0, 0, 0, 0))
        #background.paste(original_image, (0,0), original_image)

        width, height = original_image.size
        min_x = background.size[0]
        min_y = background.size[1]
        max_x = 0
        max_y = 0
        for r in range(width):
            for c in range(height):
                x = r + outline_width
                y = c + outline_width
                # non-transparent pixels
                if original_image.getpixel((r,c))[-1] != 0:

                    # trace the outline
                    if not full:
                        for k in range(-outline_width,outline_width+1):
                            for l in range(abs(k)-outline_width,-abs(k)+outline_width+1):
                                #if original_image.getpixel((x+k-outline_width,y+l-outline_width))[-1] == 0:
                                    background.putpixel((x+k,y+l),color)
                    if full:
                        for k in range(-outline_width,outline_width+1):
                            for l in range(-outline_width,outline_width+1):
                                #if original_image.getpixel((x+k-outline_width,y+l-outline_width))[-1] == 0:
                                    background.putpixel((x+k,y+l),color)

                    # find the non-transparent pixels coords
                    min_x = min(x-outline_width,min_x)
                    min_y = min(y-outline_width,min_y)
                    max_x = max(x+outline_width+1,max_x)
                    max_y = max(y+outline_width+1,max_y)

        # merge the outline with the image
        background.paste(original_image, (outline_width,outline_width), original_image) 
        # remove the white-space
        if crop:
            background = background.crop((min_x,min_y,max_x,max_y))
        return background

    @staticmethod
    def remove_white_space(original_image):
        ''' remove the empty space around a transparent png '''
        image = original_image.convert('RGBA')
        width, height = image.size
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        for x in range(width):
            for y in range(height):
                if image.getpixel((x,y))[-1] != 0:
                    min_x = min(x,min_x)
                    min_y = min(y,min_y)
                    max_x = max(x+1,max_x)
                    max_y = max(y+1,max_y)

        return image.crop((min_x,min_y,max_x,max_y))

    def get_pxls_color(self,input):
        """ Get the RGBA value of a pxls color by its name. """
        color_name = input.lower().replace("gray","grey")
        for color in self.stats.get_palette():
            if color["name"].lower() == color_name.lower():
                rgb = ImageColor.getcolor(f'#{color["value"]}',"RGBA")
                return rgb
        raise ValueError("The color '{}' was not found in the pxls palette. ".format(input))

    @staticmethod
    def is_hex_color(input_string):
        regexp = re.compile(HEX_COLOR_REGEX)
        if regexp.search(input_string):
            return True

def setup(client):
    client.add_cog(Outline(client))
