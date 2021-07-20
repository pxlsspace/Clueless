import discord
import inspect
import plotly.graph_objects as go

from PIL import Image, ImageColor
from discord.ext import commands
from io import BytesIO

from utils.setup import stats
from utils.discord_utils import format_table, get_image_from_message

class ColorBreakdown(commands.Cog):
    def __init__(self,client):
        self.client = client

    @commands.command(description="Amount of pixels for each color in an image.",
        usage="<image|url>")
    async def colors(self,ctx,url=None):
        # get the input image
        try:
            img_bytes, url = get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        input_image = Image.open(BytesIO(img_bytes))
        input_image = input_image.convert('RGBA')
        nb_pixels = input_image.size[0]*input_image.size[1]

        # get the colors table
        async with ctx.typing():
            image_colors = input_image.getcolors(nb_pixels)

        if image_colors:
            pxls_colors = rgb_to_pxlscolor(image_colors)
            pxls_colors.sort(key = lambda x:x[1],reverse=True)
        else:
            return await ctx.send("❌ Unsupported format or image mode")

        labels = [pxls_color[0] for pxls_color in pxls_colors]
        values = [pxls_color[1] for pxls_color in pxls_colors]
        colors = [pxls_color[2] for pxls_color in pxls_colors]

        # create the message with a header and the table
        header = f"""• Number of colors: `{len(image_colors)}`
                     • Number of pixels: `{nb_pixels}`
                     • Number of visible pixels: `{sum(values)}`"""
        header = inspect.cleandoc(header) + "\n"
        tab_to_format = [pxls_colors[i][:2] for i in range(len(pxls_colors))]
        tab_formated = header + "```\n" + format_table(tab_to_format,["Color","Qty"],["^",">"]) + "```"
        if len(tab_formated) > 2000:
            tab_formated = header + f"*Too many colors to display the detailed breakdown.*"

        # make the pie chart
        piechart = get_piechart(labels,values,colors)
        piechart_img = fig2img(piechart)

        # send an embed with the color table, the pie chart and the input image as thumbnail
        emb = discord.Embed(title="Color Breakdown",description=tab_formated,color=hex_str_to_int(colors[0]))
        with BytesIO() as image_binary:
            piechart_img.save(image_binary, 'PNG')
            image_binary.seek(0)
            image = discord.File(image_binary, filename='piechart.png')
            emb.set_image(url=f'attachment://piechart.png')
            emb.set_thumbnail(url=url)
            await ctx.send(file=image,embed=emb)

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
    return fig

def fig2img(fig):
    buf = BytesIO()
    fig.write_image(buf,format="png",width=600,height=600,scale=1.5)
    img = Image.open(buf)
    return img