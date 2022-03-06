import disnake
import inspect
import plotly.graph_objects as go
import functools
from PIL import Image
from disnake.ext import commands
from io import BytesIO

from utils.discord_utils import format_number, get_image_from_message, image_to_file
from utils.table_to_image import table_to_image
from utils.image.image_utils import (
    h_concatenate,
    hex_to_rgb,
    rgb_to_hex,
    hex_str_to_int,
)
from utils.plot_utils import fig2img
from utils.setup import stats


class ColorBreakdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

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
        await _colors(self.bot, ctx, input_image)


async def _colors(bot: commands.Bot, ctx, input_image, title="Color Breakdown"):

    pie_chart_limit = 256
    table_limit = 40
    nb_pixels = input_image.size[0] * input_image.size[1]

    # get the colors table
    image_colors = await bot.loop.run_in_executor(
        None, input_image.getcolors, nb_pixels
    )
    if image_colors is None:
        return await ctx.send("❌ Unsupported format or image mode.")

    # remove transparent pixels (alpha < 128)
    image_colors = [c for c in image_colors if (len(c[1]) != 4 or c[1][3] >= 128)]
    nb_colors = len(image_colors)
    if nb_colors > 1e6:
        return await ctx.send(
            embed=disnake.Embed(
                title="❌ Too many colors.",
                description=f"This image has way too many colors! (**{format_number(nb_colors)}**)",
                color=disnake.Color.red(),
            )
        )
    # group by rgb color and get the colors names
    pxls_colors = rgb_to_pxlscolor(image_colors)
    # sort by amount
    pxls_colors.sort(key=lambda x: x[1], reverse=True)

    labels = [pxls_color[0] for pxls_color in pxls_colors]
    values = [pxls_color[1] for pxls_color in pxls_colors]
    total_amount = sum(values)
    colors = [pxls_color[2] for pxls_color in pxls_colors]
    percentages = [
        format_number((pxls_color[1] / total_amount) * 100) + " %"
        for pxls_color in pxls_colors
    ]

    data = [[labels[i], values[i], percentages[i]] for i in range(len(pxls_colors))]

    def crop_data(nb_line):
        """keep the `nb_line` first values of data/colors
        and add "other" at the end with the right values"""
        data_cropped = data[: nb_line - 1]
        colors_cropped = colors[: nb_line - 1]

        rest = data[nb_line - 1 :]
        rest_amount = sum([c[1] for c in rest])
        rest_percentage = format_number((rest_amount / total_amount) * 100) + " %"

        data_cropped.append(["Other", rest_amount, rest_percentage])
        colors_cropped.append(None)

        return data_cropped, colors_cropped

    # make the table image
    if len(data) > table_limit:
        # crop the table if it has too many values
        data_cropped, colors_cropped = crop_data(table_limit)
    else:
        data_cropped = data
        colors_cropped = colors

    data_cropped = [[format_number(c) for c in row] for row in data_cropped]
    func = functools.partial(
        table_to_image,
        data_cropped,
        ["Color", "Qty", "%"],
        ["center", "right", "right"],
        colors_cropped,
        None,
        None,
        False,
        3,
    )
    table_img = await bot.loop.run_in_executor(None, func)

    # make the pie chart image
    if len(data) > pie_chart_limit:
        # crop the data if it has too many values
        data_chart, colors_chart = crop_data(pie_chart_limit)
        # remove the "other" value
        data_chart.pop(-1)
        colors_chart.pop(-1)
    else:
        data_chart = data
        colors_chart = colors
    labels_chart = [d[2] for d in data_chart]  # show the correct percentages as labels
    values_chart = [d[1] for d in data_chart]
    piechart = get_piechart(labels_chart, values_chart, colors_chart)
    piechart_img = await bot.loop.run_in_executor(
        None, fig2img, piechart, 600, 600, 1.5
    )

    # create the message with a header
    header = f"""• Number of colors: `{format_number(nb_colors)}`
                • Visible pixels: `{format_number(total_amount)}`
                • Image size: `{input_image.width} x {input_image.height}` (`{format_number(nb_pixels)}` pixels)"""
    header = inspect.cleandoc(header) + "\n"

    # concatenate the pie chart and table image
    res_img = await bot.loop.run_in_executor(
        None, h_concatenate, table_img, piechart_img
    )

    # send an embed with the color table, the pie chart
    emb = disnake.Embed(
        title=title, description=header, color=hex_str_to_int(colors[0])
    )
    if len(data) > pie_chart_limit:
        emb.set_footer(
            text=f"Too many colors - Showing the top {pie_chart_limit} colors in the chart."
        )
    file = await bot.loop.run_in_executor(
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

    # make a dictionary of the palette where the key is the rgb value and value is the name
    pxls_palette = stats.get_palette()
    palette_names = [c["name"] for c in pxls_palette]
    palette_rgbs = [hex_to_rgb(hex) for hex in [c["value"] for c in pxls_palette]]
    palette_dict = {palette_rgbs[i]: palette_names[i] for i in range(len(palette_rgbs))}

    res_dict = {}
    for color in img_colors:
        amount = color[0]
        rgb = tuple(color[1][:3])
        color_name = palette_dict.get(rgb) or rgb_to_hex(rgb)

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
    fig = go.Figure(
        data=[go.Pie(text=labels, values=values, sort=False)], layout=layout
    )
    fig.update_traces(
        textinfo="text",
        textfont_size=20,
        marker=dict(colors=colors, line=dict(color="#000000", width=1)),
    )
    fig.update_traces(textposition="inside")
    fig.update_layout(uniformtext_minsize=12, uniformtext_mode="hide")
    fig.update_layout(showlegend=False)
    return fig


def setup(bot: commands.Bot):
    bot.add_cog(ColorBreakdown(bot))
