from datetime import datetime, timezone
import discord
from discord.ext import commands
import numpy as np
from PIL import Image,ImageColor
from utils.image_utils import get_pxls_color, hex_str_to_int,is_hex_color,\
         rgb_to_hex, v_concatenate
from utils.setup import stats
from utils.discord_utils import format_number, image_to_file
from utils.arguments_parser import MyParser
from utils.table_to_image import table_to_image


class Highlight(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(
        description="Highlight the selected colors on the canvas.",
        aliases = ["hl"],
        usage="<colors> [-bgcolor|-bg <color>]",
        help = """\t- `<colors>`: list of pxls colors separated by a comma
            \t- `[-bgcolor|bg <color>]`: the color to display behind the\
             selected colors (`none` = transparent)""")
    async def highlight(self,ctx,*args):
        """Highlight colors on the canvas."""


        # parse the arguemnts
        parser  = MyParser(add_help=False)
        parser.add_argument('colors', type=str, nargs='+')
        parser.add_argument('-bgcolor',"-bg",nargs="*", type=str,
            action='store', required=False)
        try:
            parsed_args= parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # get color rgba
        colors = " ".join(parsed_args.colors)
        colors = colors.split(",")

        rgba_list =[]
        for color in colors:
            color = color.strip(" ").lower()
            try:
                rgba = get_pxls_color(color)
            except ValueError:
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

        async with ctx.typing():
            # get the board with the placeable pixels only
            canvas_array_idx = await stats.get_placable_board()
            total_amount = np.sum(canvas_array_idx!=255)
            canvas_array = stats.palettize_array(canvas_array_idx)

            # create a mask for each color and do a logical or between all the masks
            res_mask = np.zeros((canvas_array.shape[0],canvas_array.shape[1]))
            res_mask[:,:] = False
            color_amounts = []
            for rgba in rgba_list:
                mask = np.all(canvas_array == rgba, axis=2)
                res_mask = np.logical_or(res_mask,mask)
                color_amount = np.count_nonzero(mask!=0)
                color_amounts.append(color_amount)
            res_mask = ~res_mask

            # apply the mask to the canvas array
            color_selected_array = canvas_array.copy()
            color_selected_array[res_mask, :] = [0, 0, 0, 0]

            # put the background under the mask
            if not bg_color:
                hl_image = highlight_image(color_selected_array,canvas_array)
            else:
                width = canvas_array.shape[1]
                height = canvas_array.shape[0]
                hl_image = Image.new('RGBA',(width,height),bg_rgba)
                color_selected_img = Image.fromarray(color_selected_array)
                hl_image.paste(color_selected_img,(0,0),color_selected_img)

            data = []
            # make a table with the values
            for i in range(len(colors)):
                color_name = colors[i].strip(" ").title()
                amount = color_amounts[i]
                percentage = f"{round(amount/total_amount*100,2)}%"
                hex_color = rgb_to_hex(rgba_list[i][:-1])

                data.append((color_name,amount,percentage,hex_color))
            
            data.sort(key = lambda x:x[1],reverse=True)
            hex_colors = [d[-1] for d in data]
            data = [d[:-1] for d in data]
            table_img = table_to_image(data,["Color","Amount","Percentage"],colors=hex_colors)
            res_img = v_concatenate(table_img,hl_image,resize_im2=False,gap_height=50)

            # set embed color to the top 1 color in colors
            selected_color_int = hex_str_to_int(hex_colors[0])
            emb = discord.Embed(
                title="Color highlight",
                color=selected_color_int,
                timestamp = datetime.now(timezone.utc))
            res_file =image_to_file(res_img,"highlight.png",emb)

            await ctx.send(embed=emb,file=res_file)

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

    background_array[:,:,-1] = opacity * 255

    black_background_img = Image.fromarray(black_background)
    background_img = Image.fromarray(background_array)
    top_img = Image.fromarray(top_array)

    black_background_img = Image.alpha_composite(black_background_img,background_img)
    #black_background_img.paste(background_img,(0,0),black_background_img)
    black_background_img.paste(top_img,(0,0),top_img)

    return black_background_img

def setup(client):
    client.add_cog(Highlight(client))
