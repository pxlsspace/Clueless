import disnake
import numpy as np
from io import BytesIO
from datetime import datetime, timezone
from disnake.ext import commands
from PIL import Image


from utils.image.image_utils import (
    get_color,
    hex_str_to_int,
    rgb_to_hex,
    is_dark,
)
from utils.discord_utils import (
    format_number,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.arguments_parser import MyParser
from utils.table_to_image import table_to_image


class Highlight(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="highlight")
    async def _highlight(
        self,
        inter: disnake.AppCmdInter,
        colors: str,
        image: str = None,
        bgcolor: str = None,
    ):
        """Highlight the selected colors in an image.

        Parameters
        ----------
        colors: List of pxls colors or hex colors separated by a comma.
        image: The URL of the image you want to highlight.
        bgcolor: To display behind the selected colors (can be a color name, hex color, 'none', 'light' or 'dark').
        """
        await inter.response.defer()
        args = (colors,)
        if image:
            args += (image,)
        if bgcolor:
            args += ("-bgcolor", bgcolor)
        await self.highlight(inter, *args)

    @commands.command(
        name="highlight",
        description="Highlight the selected colors in an image.",
        aliases=["hl"],
        usage="<colors> <image|url> [-bgcolor|-bg <color>]",
        help="""
            - `<colors>`: list of pxls or hex colors separated by a comma
            - `<image|url>`: an image URL or an attached file
            - `[-bgcolor|bg <color>]`: the color to display behind the higlighted colors, it can be:
                • a pxls name color (ex: "red")
                • a hex color (ex: "#ff000")
                • "none": to have a transparent background
                • "dark": to have the background darkened
                • "light": to have the background lightened""",
    )
    async def p_highlight(self, ctx, *args):
        async with ctx.typing():
            await self.highlight(ctx, *args)

    async def highlight(self, ctx, *args):
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("colors", type=str, nargs="+")
        parser.add_argument(
            "-bgcolor", "-bg", nargs="*", type=str, action="store", required=False
        )
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # check if there is an image URL in the arguments
        colors, urls = get_urls_from_list(parsed_args.colors)
        input_url = urls[0] if urls else None

        # get the input image
        image_bytes, url = await get_image_from_message(ctx, input_url)
        image = Image.open(BytesIO(image_bytes))
        image = image.convert("RGBA")
        image_array = np.array(image)

        await _highlight(ctx, image_array, colors, parsed_args.bgcolor)


async def _highlight(ctx, image_array: np.ndarray, colors, bg_color):
    """Highlight colors in an image."""

    # get color rgba
    colors = " ".join(colors)
    colors = colors.split(",")
    colors = [c.strip(" ").lower() for c in colors]
    colors = list(dict.fromkeys(colors))

    rgba_list = []
    for i, color in enumerate(colors):

        color_name, rgba = get_color(color)
        if rgba is None:
            return await ctx.send(f"❌ The color `{color}` is invalid.")
        colors[i] = color_name

        rgba_list.append(rgba)

    # get bg color rgba
    if bg_color:
        bg_color = " ".join(bg_color).lower()
        if bg_color == "none":
            bg_rgba = (0, 0, 0, 0)
        elif bg_color in ["dark", "light"]:
            bg_rgba = None
        else:
            bg_color_name, bg_rgba = get_color(bg_color)
            if bg_rgba is None:
                return await ctx.send(f"❌ The background color `{bg_color}` is invalid.")

    # find the number of pixels non-transparent
    alpha_values = image_array[:, :, 3]
    total_amount = np.sum(alpha_values == 255)

    # create a mask for each color and do a logical or between all the masks
    res_mask = np.zeros((image_array.shape[0], image_array.shape[1]))
    res_mask[:, :] = False
    color_amounts = []
    for rgba in rgba_list:
        mask = np.all(image_array == rgba, axis=2)
        res_mask = np.logical_or(res_mask, mask)
        color_amount = np.count_nonzero(mask != 0)
        color_amounts.append(color_amount)
    res_mask = ~res_mask

    # apply the mask to the canvas array
    color_selected_array = image_array.copy()
    color_selected_array[res_mask, :] = [0, 0, 0, 0]

    # put the background under the mask

    if not bg_color or bg_color in ["dark", "light"]:
        if bg_color == "light":
            highlight_bg_color = (255, 255, 255, 255)
        elif bg_color == "dark":
            highlight_bg_color = (0, 0, 0, 255)
        elif all([is_dark(rgba) for rgba in rgba_list]):
            highlight_bg_color = (255, 255, 255, 255)
        else:
            highlight_bg_color = (0, 0, 0, 255)
        hl_image = highlight_image(
            color_selected_array, image_array, background_color=highlight_bg_color
        )
    else:
        width = image_array.shape[1]
        height = image_array.shape[0]
        hl_image = Image.new("RGBA", (width, height), bg_rgba)
        color_selected_img = Image.fromarray(color_selected_array)
        hl_image.paste(color_selected_img, (0, 0), color_selected_img)

    data = []
    # make a table with the values
    for i in range(len(colors)):
        color_name = colors[i].strip(" ")
        if "#" not in color_name:
            color_name = color_name.title()
        amount = color_amounts[i]
        percentage = f"{round(amount/total_amount*100,2)}%"
        hex_color = rgb_to_hex(rgba_list[i][:-1])

        data.append((color_name, amount, percentage, hex_color))

    data.sort(key=lambda x: x[1], reverse=True)
    hex_colors = [d[-1] for d in data]
    data = [d[:-1] for d in data]
    data = [[format_number(c) for c in row] for row in data]
    table_img = table_to_image(data, ["Color", "Amount", "Percentage"], colors=hex_colors)

    # set embed color to the top 1 color in colors
    selected_color_int = hex_str_to_int(hex_colors[0])
    emb = disnake.Embed(
        title="Color highlight",
        color=selected_color_int,
        timestamp=datetime.now(timezone.utc),
    )
    table_file = image_to_file(table_img, "table.png", emb)
    hl_file = image_to_file(hl_image, "highlight.png")
    await ctx.send(embed=emb, files=[hl_file, table_file])


def highlight_image(
    top_array, background_array, opacity=0.2, background_color=(255, 255, 255, 255)
):
    msg = "top_array and background_array must have the same shape"
    assert top_array.shape == background_array.shape, msg
    assert top_array.shape[-1] in [3, 4], "top_array shapee must be [:,:,3|4]"
    assert background_array.shape[-1] in [
        3,
        4,
    ], "background_array shape must be [:,:,3|4]"
    # convert background to rgba
    if background_array.shape[-1] != 4:
        background_array = np.dstack(
            (background_array, np.zeros(background_array.shape[:-1]))
        )

    black_background = np.zeros_like(background_array)
    black_background[:, :] = background_color
    black_background[:, :, 3] = background_array[:, :, 3]

    background_array[:, :, -1] = opacity * background_array[:, :, -1]

    black_background_img = Image.fromarray(black_background)
    background_img = Image.fromarray(background_array)
    top_img = Image.fromarray(top_array)

    black_background_img = Image.alpha_composite(black_background_img, background_img)
    black_background_img.paste(top_img, (0, 0), top_img)

    return black_background_img


def setup(bot: commands.Bot):
    bot.add_cog(Highlight(bot))
