import discord
import inspect
import plotly.graph_objects as go
import functools

from PIL import Image, ImageColor
from discord.ext import commands
from io import BytesIO

from utils.setup import stats
from utils.discord_utils import format_number, get_image_from_message, image_to_file
from utils.table_to_image import table_to_image
from utils.image_utils import h_concatenate
from utils.plot_utils import fig2img

class ColorBreakdown(commands.Cog):
    def __init__(self,client):
        self.client = client

    @commands.command(description="Amount of pixels for each color in an image.",
        usage="<image|url>")
    async def colors(self,ctx,url=None):
        async with ctx.typing():
            # get the input image
            try:
                img_bytes, url = await get_image_from_message(ctx,url)
            except ValueError as e:
                return await ctx.send(f'❌ {e}')

            input_image = Image.open(BytesIO(img_bytes))
            input_image = input_image.convert('RGBA')
            await self._colors(ctx,input_image)

    async def _colors(self,ctx,input_image,title="Color Breakdown"):

           
        nb_pixels = input_image.size[0]*input_image.size[1]

        # get the colors table
        image_colors = await self.client.loop.run_in_executor(None,input_image.getcolors,nb_pixels)

        if image_colors:
            pxls_colors = rgb_to_pxlscolor(image_colors)
            pxls_colors.sort(key = lambda x:x[1],reverse=True)
        else:
            return await ctx.send("❌ Unsupported format or image mode.")

        labels = [pxls_color[0] for pxls_color in pxls_colors]
        values = [pxls_color[1] for pxls_color in pxls_colors]
        colors = [pxls_color[2] for pxls_color in pxls_colors]

        data = []
        for i in range(len(labels)):
            color_name = labels[i]
            amount = values[i]
            percentage = round(amount/sum(values)*100,2)

            amount = format_number(amount)
            percentage = str(percentage) + " %"
            data.append([color_name,amount,percentage])

        # make the table image
        if len(data) > 40:
            # crop the table if it has too many values
            data_cropped = data[:40]
            colors_cropped = colors[:40]
            data_cropped.append(["...","...","..."])
            colors_cropped.append(None)
        else:
            data_cropped = data
            colors_cropped = colors
        func = functools.partial(table_to_image,data_cropped,['Color','Qty','%'],['center','right','right'],colors_cropped)
        table_img = await self.client.loop.run_in_executor(None,func)

        # make the pie chart image
        piechart = get_piechart(labels,values,colors)
        piechart_img = await self.client.loop.run_in_executor(None,fig2img,piechart,600,600,1.5)

        # create the message with a header
        header = f"""• Number of colors: `{len(colors)}`
                    • Number of pixels: `{format_number(nb_pixels)}`
                    • Number of visible pixels: `{format_number(sum(values))}`"""
        header = inspect.cleandoc(header) + "\n"

        # concatenate the pie chart and table image
        res_img = await self.client.loop.run_in_executor(None,h_concatenate,table_img,piechart_img)

        # send an embed with the color table, the pie chart
        emb = discord.Embed(title=title,description=header,color=hex_str_to_int(colors[0]))
        file = await self.client.loop.run_in_executor(None,image_to_file,res_img,"color_breakdown.png",emb)
        # set the input image as thumbnail
        f = image_to_file(input_image,"input.png")
        emb.set_thumbnail(url="attachment://input.png")
        await ctx.send(files=[file,f],embed=emb)

    @commands.command(description="Show the canvas colors.",aliases=["cc"],usage = "[-placed|-p]")
    async def canvascolors(self,ctx,*options):

        async with ctx.typing():
        # get the board with the placeable pixels only
            board_array = await stats.fetch_board()
            placemap_array = await stats.fetch_placemap()
            placeable_board = board_array.copy()
            placeable_board[placemap_array != 0] = 255
            placeable_board[placemap_array == 0] = board_array[placemap_array == 0]

            if "-placed" in options or "-p" in options:
            # use the virgin map as a mask to get the board with placed pixels
                virgin_array = await stats.fetch_virginmap()
                placed_board = placeable_board.copy()
                placed_board[virgin_array != 0] = 255
                placed_board[virgin_array == 0] = placeable_board[virgin_array == 0]
                img = Image.fromarray(stats.palettize_array(placed_board))
                title = "Canvas colors breakdown (non-virgin pixels only)"
            else:
                img = Image.fromarray(stats.palettize_array(placeable_board))
                title = "Canvas color breakdown"

            await self._colors(ctx,img,title)

def setup(client):
    client.add_cog(ColorBreakdown(client))

def rgb_to_pxlscolor(img_colors):
    '''convert a list (amount,RGB) to a list of (color_name,amount,hex code)

    color_name is a pxls.space color name, if the RGB doesn't match,
    the color_name will be the hex code'''
    res_list = []
    for color in img_colors:
        amount = color[0]
        rgb = color[1]
        if len(rgb) != 4 or rgb[3] != 0:
            rgb = rgb[:3]
            color_name = rgb_to_pxls(rgb)
            res_list.append(
                (color_name or (rgb_to_hex(rgb)),
                amount,
                rgb_to_hex(rgb)))
    return res_list

def rgb_to_hex(rgb):
    ''' convert a RGB tuple to the matching hex code as a string
    ((255,255,255) -> '#ffffff')'''
    str = '#' + '%02x'*len(rgb)
    return str % rgb

def rgb_to_pxls(rgb):
    ''' convert a RGB tuple to a pxlsColor.
    Return None if no color match.'''
    rgb = rgb [:3]
    for pxls_color in stats.get_palette():
        if rgb == hex_to_rgb(pxls_color["value"]):
            return pxls_color["name"]
    return None
def hex_to_rgb(hex:str,mode="RGB"):
    ''' convert a hex color string to a RGB tuple
    ('#ffffff' -> (255,255,255) or 'ffffff' -> (255,255,255)'''
    if "#" in hex:
        return ImageColor.getcolor(hex,mode)
    else:
        return ImageColor.getcolor('#' + hex, mode)

def hex_str_to_int(hex_str:str):
    """ '#ffffff' -> 0xffffff """
    if '#' in hex_str:
        return int(hex_str[1:],16)
    else:
        return int(hex_str,16)

def get_piechart(labels,values,colors):
    layout = go.Layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color="white"
    )
    fig = go.Figure(data=[go.Pie(labels=labels,
                                values=values)],layout=layout)
    fig.update_traces( textinfo='percent', textfont_size=20,
                    marker=dict(colors=colors, line=dict(color='#000000', width=1)))
    fig.update_traces(textposition='inside')
    fig.update_layout(uniformtext_minsize=12, uniformtext_mode='hide')
    fig.update_layout(showlegend=False)
    return fig
