import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from utils.discord_utils import (
    autocomplete_palette,
    format_number,
    get_image_from_message,
    get_urls_from_list,
    image_to_file,
)
from utils.font.font_manager import PixelText
from utils.image.image_utils import get_color
from utils.utils import in_executor


class Grid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="grid")
    async def _grid(
        self,
        inter: disnake.AppCmdInter,
        image: str = None,
        x: int = 0,
        y: int = 0,
        color: str = commands.Param(autocomplete=autocomplete_palette, default=None),
    ):
        """Add a grid between pixels and upscale a pixel art.

        Parameters
        ----------
        image: The URL of the image.
        x: the x coordinate of the top left pixel
        y: the y coordinate of the top left pixel
        color: The color of the grid (default: black)
        """
        await inter.response.defer()
        await self.grid(inter, image, x, y, color)

    @commands.command(
        name="grid",
        description="Add a grid between pixels and upscale a pixel art.",
        usage="<url|image> <x> <y> [color]",
        help="""- `<url|image>`: an image URL or an attached image
                - `<x>`: the x coordinate of the top left pixel
                - `<y>`: the y coordinate of the top left pixel
                - `[color]`: color of the grid (default: black)""",
    )
    async def p_grid(self, ctx, *args):

        color = None
        coords, urls = get_urls_from_list(args)
        if len(coords) >= 3:
            x, y, color = coords[:3]
        elif len(coords) >= 2:
            x, y = coords[:2]
        elif len(coords) <= 0:
            raise commands.MissingRequiredArgument(commands.Param(name="x"))
        elif len(coords) <= 1:
            raise commands.MissingRequiredArgument(commands.Param(name="y"))

        try:
            x = int(x)
            y = int(y)
        except Exception:
            return await ctx.send(":x: Invalid integer in the coordinates.")
        url = None
        if urls:
            url = urls[0]

        async with ctx.typing():
            await self.grid(ctx, url, x, y, color)

    async def grid(self, ctx, url=None, x=0, y=0, color=None):
        """command to add an to an image"""

        # get the rgba from the color input
        if color:
            color_name, rgba = get_color(color)
            if rgba is None:
                return await ctx.send(f"❌ The color `{color}` is invalid.")
        else:
            rgba = [0, 0, 0, 255]

        # get the input image
        try:
            input_image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        image_scale = 7
        grid_width = 1
        input_width = input_image.width
        input_height = input_image.height
        res_size = input_height * input_width * (image_scale + grid_width) ** 2
        if res_size > 20000000:
            return await ctx.send(
                f":x: The resulting image would be too big ({format_number(res_size)} pixels)."
            )

        image_with_grid = await make_grid(
            input_image, rgba, grid_width, image_scale, x, y
        )
        file = await image_to_file(image_with_grid, "grid.png")

        await ctx.send(file=file)


def setup(bot: commands.Bot):
    bot.add_cog(Grid(bot))


@in_executor()
def make_grid(
    input_image: Image.Image,
    highlight_color=[0, 0, 0, 255],
    grid_width=1,
    image_scale=10,
    x: int = 0,
    y: int = 0,
):
    grid_color = [150, 150, 150, 255]
    input_width = input_image.width
    input_height = input_image.height

    input_image = input_image.resize(
        (input_image.width * image_scale, input_image.height * image_scale),
        resample=Image.NEAREST,
    )
    image_array = np.array(input_image, dtype=np.uint8)
    grid_color = np.array(grid_color, dtype=np.uint8)

    # add horizontal lines
    h_line = np.zeros((grid_width, image_array.shape[1], 4), np.uint8)
    h_line[:, :] = grid_color
    h_line_highlight = h_line.copy()
    h_line_highlight[:, :] = highlight_color
    for j in range(0, image_array.shape[0] + input_height + 1, image_scale + 1):
        true_j = j / (image_scale + 1) + y
        if true_j % 5 == 0 or (true_j - 1) % 5 == 0:
            image_array = np.insert(image_array, j, h_line_highlight, axis=0)
        else:
            image_array = np.insert(image_array, j, h_line, axis=0)

    # add vertical lines
    v_line = np.zeros((grid_width, image_array.shape[0], 4), np.uint8)
    v_line[:, :] = grid_color
    v_line_highlight = v_line.copy()
    v_line_highlight[:, :] = highlight_color
    for i in range(0, image_array.shape[1] + input_width + 1, image_scale + 1):
        true_i = i / (image_scale + 1) + x
        if true_i % 5 == 0 or (true_i - 1) % 5 == 0:
            image_array = np.insert(image_array, i, v_line_highlight, axis=1)
        else:
            image_array = np.insert(image_array, i, v_line, axis=1)

    # add text padding
    text = PixelText("0", "minecraft", (255, 255, 255, 255), (0, 0, 0, 0))
    text_height = text.font.max_height
    padding_left = np.zeros((20, image_array.shape[0], 4), np.uint8)
    image_array = np.insert(image_array, 0, padding_left, axis=1)
    padding_top = np.zeros((text_height + 1, image_array.shape[1], 4), np.uint8)
    image_array = np.insert(image_array, 0, padding_top, axis=0)

    # add coords (on the left)
    for j in range(0, image_array.shape[0] + 1, image_scale + 1):
        true_j = int(j / (image_scale + 1) + y) - 1
        if true_j % 5 == 0 and j != 0:
            text = PixelText(
                str(true_j), "minecraft", highlight_color, (0, 0, 0, 0)
            ).make_array()
            try:
                image_array[j + 2 : j + 2 + text.shape[0], 0 : text.shape[1]] = text
            except Exception:
                pass

    # add coords (at the top)
    for i in range(0, image_array.shape[1] + 1, image_scale + 1):
        true_i = int(i / (image_scale + 1) + x) - 1
        if true_i % 5 == 0 and i != 0:
            text = PixelText(
                str(true_i), "minecraft", highlight_color, (0, 0, 0, 0)
            ).make_array()
            offset = (text.shape[1] // 2) - 2
            try:
                image_array[
                    1 : text.shape[0] + 1, i + offset : i + offset + text.shape[1]
                ] = text
            except Exception:
                pass

    # make the background white
    image_array[image_array[:, :, -1] < 128] = [255, 255, 255, 255]
    return Image.fromarray(image_array)
