import disnake
import inspect
import plotly.graph_objects as go
import functools
from PIL import Image
from disnake.ext import commands
from io import BytesIO

from utils.discord_utils import format_number, get_image_from_message, image_to_file
from utils.table_to_image import table_to_image
from utils.image.image_utils import h_concatenate, rgb_to_hex, rgb_to_pxls, hex_str_to_int
from utils.plot_utils import fig2img


class ColorBreakdown(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(name="colors")
    async def _colors(self, inter: disnake.AppCmdInter, image: str = None):
        """Get the amount of pixels for each color in an image.

        Parameters
        ----------
        image: The URL of the image you want to see the colors."""
        await inter.response.defer()
        await self.colors(inter, image)

    @commands.command(
        name="colors",
        description="Amount of pixels for each color in an image.",
        usage="<image|url>",
        aliases=["color", "colours", "colour"],
    )
    async def p_colors(self, ctx, url=None):
        async with ctx.typing():
            await self.colors(ctx, url)

    async def colors(self, ctx, url=None):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        input_image = Image.open(BytesIO(img_bytes))
        input_image = input_image.convert("RGBA")
        await _colors(self.client, ctx, input_image)


async def _colors(client, ctx, input_image, title="Color Breakdown"):

    nb_pixels = input_image.size[0] * input_image.size[1]

    # get the colors table
    image_colors = await client.loop.run_in_executor(
        None, input_image.getcolors, nb_pixels
    )
    if len(image_colors) > 5000:
        return await ctx.send(
            "❌ This image has too many colors ({})".format(len(image_colors))
        )
    if image_colors:
        pxls_colors = rgb_to_pxlscolor(image_colors)
        pxls_colors.sort(key=lambda x: x[1], reverse=True)
    else:
        return await ctx.send("❌ Unsupported format or image mode.")

    labels = [pxls_color[0] for pxls_color in pxls_colors]
    values = [pxls_color[1] for pxls_color in pxls_colors]
    colors = [pxls_color[2] for pxls_color in pxls_colors]

    data = []
    for i in range(len(labels)):
        color_name = labels[i]
        amount = values[i]
        percentage = round(amount / sum(values) * 100, 2)

        amount = format_number(amount)
        percentage = str(percentage) + " %"
        data.append([color_name, amount, percentage])

    # make the table image
    if len(data) > 40:
        # crop the table if it has too many values
        data_cropped = data[:40]
        colors_cropped = colors[:40]
        data_cropped.append(["...", "...", "..."])
        colors_cropped.append(None)
    else:
        data_cropped = data
        colors_cropped = colors
    func = functools.partial(
        table_to_image,
        data_cropped,
        ["Color", "Qty", "%"],
        ["center", "right", "right"],
        colors_cropped,
    )
    table_img = await client.loop.run_in_executor(None, func)

    # make the pie chart image
    piechart = get_piechart(labels, values, colors)
    piechart_img = await client.loop.run_in_executor(
        None, fig2img, piechart, 600, 600, 1.5
    )

    # create the message with a header
    header = f"""• Number of colors: `{len(colors)}`
                • Visible pixels: `{format_number(sum(values))}`
                • Image size: `{input_image.width} x {input_image.height}` (`{format_number(nb_pixels)}` pixels)"""
    header = inspect.cleandoc(header) + "\n"

    # concatenate the pie chart and table image
    res_img = await client.loop.run_in_executor(
        None, h_concatenate, table_img, piechart_img
    )

    # send an embed with the color table, the pie chart
    emb = disnake.Embed(title=title, description=header, color=hex_str_to_int(colors[0]))
    file = await client.loop.run_in_executor(
        None, image_to_file, res_img, "color_breakdown.png", emb
    )
    # set the input image as thumbnail
    f = image_to_file(input_image, "input.png")
    emb.set_thumbnail(url="attachment://input.png")
    await ctx.send(files=[file, f], embed=emb)


def rgb_to_pxlscolor(img_colors):
    """convert a list (amount,RGB) to a list of (color_name,amount,hex code)

    color_name is a pxls.space color name, if the RGB doesn't match,
    the color_name will be the hex code"""
    res_dict = {}
    for color in img_colors:
        amount = color[0]
        rgb = color[1]
        if len(rgb) != 4 or rgb[3] != 0:
            rgb = rgb[:3]
            color_name = rgb_to_pxls(rgb) or rgb_to_hex(rgb)
            if color_name in res_dict:
                res_dict[color_name]["amount"] += amount
            else:
                res_dict[color_name] = dict(amount=amount, hex=rgb_to_hex(rgb))
    res_list = [(k, res_dict[k]["amount"], res_dict[k]["hex"]) for k in res_dict.keys()]
    return res_list


def get_piechart(labels, values, colors):
    layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white"
    )
    fig = go.Figure(data=[go.Pie(labels=labels, values=values)], layout=layout)
    fig.update_traces(
        textinfo="percent",
        textfont_size=20,
        marker=dict(colors=colors, line=dict(color="#000000", width=1)),
    )
    fig.update_traces(textposition="inside")
    fig.update_layout(uniformtext_minsize=12, uniformtext_mode="hide")
    fig.update_layout(showlegend=False)
    return fig


def setup(client):
    client.add_cog(ColorBreakdown(client))
