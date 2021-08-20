import discord
import numpy as np
import re
from io import BytesIO
from datetime import datetime, timezone
from discord.ext import commands
from PIL import Image,ImageColor

from utils.image_utils import get_pxls_color, hex_str_to_int,is_hex_color,\
         rgb_to_hex
from utils.discord_utils import get_image_from_message, image_to_file, IMAGE_URL_REGEX
from utils.arguments_parser import MyParser
from utils.table_to_image import table_to_image


class Highlight(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(
        description="Highlight the selected colors in an image.",
        aliases = ["hl"],
        usage="<colors> <image|url> [-bgcolor|-bg <color>]",
        help = """\t- `<colors>`: list of pxls colors separated by a comma
            \t- `<image|url>`: an image URL or an attached file
            \t- `[-bgcolor|bg <color>]`: the color to display behind the\
             selected colors (`none` = transparent)""")
    async def highlight(self,ctx,*args):

        # parse the arguemnts
        parser  = MyParser(add_help=False)
        parser.add_argument('colors', type=str, nargs='+')
        parser.add_argument('-bgcolor',"-bg",nargs="*", type=str,
            action='store', required=False)
        try:
            parsed_args= parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # check if there is an image URL in the arguments
        input_url = None
        possible_url = parsed_args.colors[-1]
        urls = re.findall(IMAGE_URL_REGEX,possible_url)
        if len(urls) > 0:
            input_url = urls[0]
            parsed_args.colors = parsed_args.colors[:-1]

        async with ctx.typing():
            # get the input image
            image_bytes, url = await get_image_from_message(ctx,input_url)
            image = Image.open(BytesIO(image_bytes))
            image = image.convert('RGBA')
            image_array = np.array(image)

            await _highlight(ctx,image_array,parsed_args)

async def _highlight(ctx,image_array:np.ndarray,parsed_args):
    """Highlight colors in an image."""

    # get color rgba
    colors = " ".join(parsed_args.colors)
    colors = colors.split(",")
    colors = [c.strip(" ").lower() for c in colors]
    colors = list(dict.fromkeys(colors))

    rgba_list =[]
    for color in colors:
        try:
            rgba = get_pxls_color(color)
        except ValueError:
            if is_hex_color(color):
                rgba = ImageColor.getcolor(color,"RGBA")
            else:
                return await ctx.send(f'❌ The color "{color}" is invalid.')
        rgba_list.append(rgba)

    # get bg color rgba
    bg_color = parsed_args.bgcolor
    if bg_color:
        bg_color = " ".join(bg_color)
        try:
            bg_rgba = get_pxls_color(bg_color)
        except ValueError:
            if bg_color == "none":
                bg_rgba = (0,0,0,0)
            elif is_hex_color(bg_color):
                bg_rgba = ImageColor.getcolor(bg_color,"RGBA")
            else:
                return await ctx.send(f'❌ The background color "{bg_color}" is invalid.')

    # find the number of pixels non-transparent
    alpha_values = image_array[:,:,3]
    total_amount = np.sum(alpha_values==255)

    # create a mask for each color and do a logical or between all the masks
    res_mask = np.zeros((image_array.shape[0],image_array.shape[1]))
    res_mask[:,:] = False
    color_amounts = []
    for rgba in rgba_list:
        mask = np.all(image_array == rgba, axis=2)
        res_mask = np.logical_or(res_mask,mask)
        color_amount = np.count_nonzero(mask!=0)
        color_amounts.append(color_amount)
    res_mask = ~res_mask

    # apply the mask to the canvas array
    color_selected_array = image_array.copy()
    color_selected_array[res_mask, :] = [0, 0, 0, 0]

    # put the background under the mask
    if not bg_color:
        hl_image = highlight_image(color_selected_array,image_array)
    else:
        width = image_array.shape[1]
        height = image_array.shape[0]
        hl_image = Image.new('RGBA',(width,height),bg_rgba)
        color_selected_img = Image.fromarray(color_selected_array)
        hl_image.paste(color_selected_img,(0,0),color_selected_img)

    data = []
    # make a table with the values
    for i in range(len(colors)):
        color_name = colors[i].strip(" ")
        if not '#' in color_name:
            color_name = color_name.title()
        amount = color_amounts[i]
        percentage = f"{round(amount/total_amount*100,2)}%"
        hex_color = rgb_to_hex(rgba_list[i][:-1])

        data.append((color_name,amount,percentage,hex_color))
    
    data.sort(key = lambda x:x[1],reverse=True)
    hex_colors = [d[-1] for d in data]
    data = [d[:-1] for d in data]
    table_img = table_to_image(data,["Color","Amount","Percentage"],colors=hex_colors)

    # set embed color to the top 1 color in colors
    selected_color_int = hex_str_to_int(hex_colors[0])
    emb = discord.Embed(
        title="Color highlight",
        color=selected_color_int,
        timestamp = datetime.now(timezone.utc))
    table_file = image_to_file(table_img,"table.png",emb)
    hl_file = image_to_file(hl_image,"highlight.png")
    await ctx.send(embed=emb,files=[hl_file,table_file])

def highlight_image(top_array,background_array,opacity=0.2):
    msg = "top_array and background_array must have the same shape"
    assert top_array.shape == background_array.shape,msg
    assert top_array.shape[-1] in [3,4],"top_array shapee must be [:,:,3|4]"
    assert background_array.shape[-1] in [3,4],"background_array shape must be [:,:,3|4]"
    # convert background to rgba
    if background_array.shape[-1] != 4:
        background_array = np.dstack((background_array, np.zeros(background_array.shape[:-1])))

    black_background = np.zeros_like(background_array)
    black_background[:,:] = (0,0,0,255)
    black_background[:,:,3] = background_array[:,:,3]

    background_array[:,:,-1] = opacity * background_array[:,:,-1]

    black_background_img = Image.fromarray(black_background)
    background_img = Image.fromarray(background_array)
    top_img = Image.fromarray(top_array)

    black_background_img = Image.alpha_composite(black_background_img,background_img)
    #black_background_img.paste(background_img,(0,0),black_background_img)
    black_background_img.paste(top_img,(0,0),top_img)

    return black_background_img

def setup(client):
    client.add_cog(Highlight(client))
