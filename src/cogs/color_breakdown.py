from PIL import Image, ImageColor
from discord.ext import commands
import discord
import requests
import plotly.graph_objects as go
from io import BytesIO
from utils.setup import stats
from utils.discord_utils import format_table

class ColorBreakdown(commands.Cog):
    def __init__(self,client):
        self.client = client

    @commands.command(description="Amount of pixels for each color in an image.",
        usage="<image|url>")
    async def colors(self,ctx,url=None):
        # if no url in the command, we check the attachments
        if url == None:
            if len(ctx.message.attachments) == 0:
                return await ctx.send("❌ You must give an image or url to add.")
            if "image" not in ctx.message.attachments[0].content_type:
                return await ctx.send("❌ Invalid file type. Only images are supported.")
            url = ctx.message.attachments[0].url

        # getting the image from url
        try:
            response = requests.get(url)
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema, requests.exceptions.ConnectionError):
            return await ctx.send("❌ The URL you have provided is invalid.")
        if response.status_code == 404:
            return await ctx.send( "❌ The URL you have provided leads to a 404.")

        input_image = Image.open(BytesIO(response.content))

        # get and format the color breakdown table
        tab = color_amount(input_image)
        tab_to_format = [tab[i][:2] for i in range(len(tab))]
        tab_formated = "```\n" + format_table(tab_to_format,["Color","Qty"],["^",">"]) + "```"

        # make the pie chart with the color table
        labels = [tab[i][0] for i in range(len(tab))]
        values = [tab[i][1] for i in range(len(tab))]
        colors = [tab[i][2] for i in range(len(tab))]
        piechart = get_piechart(labels,values,colors)
        piechart_img = fig2img(piechart)

        # create and send the embed with the color table, the pie chart and the image sent as thumbnail
        emb = discord.Embed(title="Color Breakdown",description=tab_formated)
        with BytesIO() as image_binary:
            piechart_img.save(image_binary, 'PNG')
            image_binary.seek(0)
            image = discord.File(image_binary, filename='piechart.png')
            emb.set_image(url=f'attachment://piechart.png')
            emb.set_thumbnail(url=url)
            await ctx.send(file=image,embed=emb)

def setup(client):
    client.add_cog(ColorBreakdown(client))

def color_amount(img):
    ''' Find the amount of pixels for each color in an image

    return a list of tuple of colors like [*(color_name,amount)] '''
    width,lenght = img.size
    colors = {}
    for x in range(width):
        for y in range(lenght):
            pixel_color = img.getpixel((x,y))
            if pixel_color[-1] == 255:
                pixel_color = pixel_color[:3]
                if pixel_color not in colors:
                    colors[pixel_color] = 1
                else:
                    colors[pixel_color] += 1
    colors_pxls = rgb_to_pxlscolor(colors)
    
    #colors_pxls_sorted = sorted(colors_pxls.items(), key=lambda x: x[1],reverse=True)
    colors_pxls.sort(key = lambda x:x[1],reverse=True)
    #)
    return colors_pxls

def rgb_to_pxlscolor(rgb_dict):
    ''' Convert a dictionary in the format {*(RGB:amount)} to {*(color_name:amount)}

    color_name is a pxls.space color name, if the RGB doesn't match,
    the color_name will be the hex code'''

    res_list = []
    for rgb in rgb_dict:

        for pxls_color in stats.get_palette():
            found = False
            if rgb == ImageColor.getcolor('#' + pxls_color["value"],'RGB'):
                res_list.append((pxls_color["name"],rgb_dict[rgb],rgb_to_hex(rgb)))
                found = True
                break
        if found == False:
            res_list.append((rgb_to_hex(rgb),rgb_dict[rgb],rgb_to_hex(rgb)))

    return res_list

def rgb_to_hex(rgb):
    ''' convert a RGB tuple to the matching hex code
    ((255,255,255) -> #ffffff)'''
    str = '#' + '%02x'*len(rgb)
    return str % rgb

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