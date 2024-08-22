import struct
from io import BytesIO

import disnake
from disnake.ext import commands
from PIL import Image, ImageDraw

from utils.arguments_parser import MyParser
from utils.discord_utils import (
    autocomplete_builtin_palettes,
    autocomplete_canvases,
    image_to_file,
)
from utils.image.image_utils import get_colors_from_input, hex_to_rgb
from utils.pxls.archives import check_canvas_code
from utils.setup import db_stats, stats


class PaletteView(disnake.ui.View):
    message: disnake.Message

    def __init__(self, color_hex: list, color_names: list, palette_name: str):
        super().__init__(timeout=500)
        self.color_hex = color_hex
        self.color_names = color_names
        self.palette_name = palette_name

    async def on_timeout(self) -> None:
        for c in self.children[:]:
            self.remove_item(c)
        await self.message.edit(view=self)

    @disnake.ui.button(label="Piskel/GIMP (.gpl)", style=disnake.ButtonStyle.blurple)
    async def gpl(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        file = make_gpl_palette(self.color_hex, self.color_names, self.palette_name)
        button.disabled = True
        button.style = disnake.ButtonStyle.gray
        await inter.send(file=file)
        await self.message.edit(view=self)

    @disnake.ui.button(label="Paint.NET (.txt)", style=disnake.ButtonStyle.blurple)
    async def paintnet(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        file = make_paintnet_palette(self.color_hex, self.color_names, self.palette_name)
        button.disabled = True
        button.style = disnake.ButtonStyle.gray
        await inter.send(file=file)
        await self.message.edit(view=self)

    @disnake.ui.button(label="Photoshop (.aco)", style=disnake.ButtonStyle.blurple)
    async def aco(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        file = make_aco_palette(self.color_hex, self.color_names, self.palette_name)
        button.disabled = True
        button.style = disnake.ButtonStyle.gray
        await inter.send(file=file)
        await self.message.edit(view=self)

    @disnake.ui.button(label="CSV", style=disnake.ButtonStyle.blurple)
    async def csv(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        file = make_csv_palette(self.color_hex, self.color_names, self.palette_name)
        button.disabled = True
        button.style = disnake.ButtonStyle.gray
        await inter.send(file=file)
        await self.message.edit(view=self)

    @disnake.ui.button(label="JSON", style=disnake.ButtonStyle.blurple)
    async def json(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        file = make_json_palette(self.color_hex, self.color_names, self.palette_name)
        button.disabled = True
        button.style = disnake.ButtonStyle.gray
        await inter.send(file=file)
        await self.message.edit(view=self)


class Palette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="palette")
    async def _palette(
        self,
        inter: disnake.AppCmdInter,
        canvas_code: str = commands.Param(
            default=None, name="canvas-code", autocomplete=autocomplete_canvases
        ),
        colors: str = commands.Param(
            default=None, autocomplete=autocomplete_builtin_palettes
        ),
    ):
        """Generate palette files and image.

        Parameters
        ----------
        canvas_code: The code of the canvas you want the palette from (default: current).
        colors: List of colors (seprated by a comma) to generate a palette from.
        """
        await self.palette(inter, canvas_code, colors)

    @commands.command(
        name="palette",
        usage="[canvas code] [-colors <list, of, colors>]",
        description="Generate palette files and image.",
    )
    async def p_palette(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("canvas_code", type=str, nargs="?", default=None)
        parser.add_argument("-colors", action="store", nargs="*")

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        colors = " ".join(parsed_args.colors) if parsed_args.colors else None
        async with ctx.typing():
            await self.palette(ctx, parsed_args.canvas_code, colors)

    async def palette(self, ctx, canvas_code_input, colors):

        embed = disnake.Embed(title="Palette", color=0x66C5CC, description="")
        # get the colors
        if colors:
            try:
                rgba_palette, hex_palette, palette_names = get_colors_from_input(
                    colors, accept_colors=True, accept_palettes=True
                )
            except ValueError as e:
                await ctx.send(f":x: {e}")
                return False
            embed.description += "**Palette:** " + ", ".join(palette_names) + "\n\n"
            canvas_code = None
            color_names = None

        else:
            if canvas_code_input:
                canvas_code = check_canvas_code(canvas_code_input)
                if canvas_code is None:
                    return await ctx.send(
                        f":x: The given canvas code `{canvas_code_input}` is invalid."
                    )
            else:
                canvas_code = await stats.get_canvas_code()
            palette = await db_stats.get_palette(canvas_code)
            if palette is None:
                return await ctx.send(f":x: Palette not found for c{canvas_code}.")
            hex_palette = [("#" + c["color_hex"]) for c in palette]
            color_names = [(c["color_name"]) for c in palette]
            embed.title = f"Palette for canvas {canvas_code}\n"

        embed.description += f"**Palette Hex:** {', '.join(hex_palette)}\n\n"

        if len(hex_palette) < 256:
            # create the palette image
            square_dim = 100
            color_per_row = 8
            lines = [
                hex_palette[i : i + color_per_row]
                for i in range(0, len(hex_palette), color_per_row)
            ]
            palette_image = Image.new(
                "RGBA",
                (square_dim * len(lines[0]), square_dim * len(lines)),
                color=(0, 0, 0, 0),
            )
            draw_image = ImageDraw.Draw(palette_image)

            col = 0
            for line in lines:
                row = 0
                for color in line:
                    square_x = row * square_dim
                    square_y = col * square_dim
                    square_shape = [
                        (square_x, square_y),
                        (square_x + square_dim - 1, square_y + square_dim - 1),
                    ]
                    row += 1
                    draw_image.rectangle(
                        square_shape,
                        fill=color,
                    )
                col += 1

            embed.description += f"**Number of colors:** {len(hex_palette)}\n\n"
            embed.description += "**Palette Image:**\n"
            filename = f"palette_c{canvas_code}.png" if canvas_code else "palette.png"
            file = await image_to_file(palette_image, filename, embed)
            files = [file]
        else:
            files = []

        palette_name = f"palette_c{canvas_code}" if canvas_code else "palette"

        view = PaletteView(hex_palette, color_names, palette_name)
        m = await ctx.send(embed=embed, files=files, view=view)
        if isinstance(ctx, (disnake.AppCmdInter, disnake.MessageInteraction)):
            m = await ctx.original_message()
        view.message = m


def setup(bot: commands.Bot):
    bot.add_cog(Palette(bot))


def make_gpl_palette(color_hex, color_names, palette_name) -> disnake.File:
    content = f"GIMP Palette\nName: {palette_name}\nColumns: {len(color_hex)}\n#\n"
    for i in range(len(color_hex)):
        hex = color_hex[i]
        name = color_names[i] if color_names else hex
        r, g, b = hex_to_rgb(hex)
        content += f"{r} {g} {b} {name}\n"

    buffer = BytesIO(content.encode("utf-8"))
    return disnake.File(buffer, filename=f"{palette_name}.gpl")


def make_paintnet_palette(color_hex, color_names, palette_name) -> disnake.File:
    content = f"; Paint.NET {palette_name}\n"
    for i in range(len(color_hex)):
        hex = color_hex[i]
        name = color_names[i] if color_names else hex
        content += f"FF{hex.replace('#', '').upper()} ; {name}\n"

    buffer = BytesIO(content.encode("utf-8"))
    return disnake.File(buffer, filename=f"{palette_name}.txt")


def make_aco_palette(color_hex, color_names, palette_name) -> disnake.File:
    buffer = BytesIO()
    for version in (1, 2):
        _write_aco_data(buffer, version, color_hex, color_names)
    buffer.seek(0)
    return disnake.File(buffer, filename=f"{palette_name}.aco")


def _write_aco_data(buffer, version, color_hex, color_names) -> None:
    buffer.write(struct.pack(">2H", version, len(color_hex)))
    color_space = 0  # RGB
    for i, hex in enumerate(color_hex):
        name = color_names[i] if color_names else hex
        r, g, b = hex_to_rgb(hex)
        color_data = struct.pack(">5H", color_space, r * 257, g * 257, b * 257, 0)
        buffer.write(color_data)
        if version == 2:
            buffer.write(struct.pack(">L", len(name) + 1))
            for c in name:
                buffer.write(struct.pack(">H", ord(c)))
            buffer.write(b"00")  # NULL word


def make_csv_palette(color_hex, color_names, palette_name) -> disnake.File:
    content = "Name,#hexadecimal,R,G,B\n"
    for i in range(len(color_hex)):
        hex = color_hex[i]
        r, g, b = hex_to_rgb(hex)
        name = color_names[i] if color_names else hex
        content += f"{name},{hex},{r},{g},{b}\n"

    buffer = BytesIO(content.encode("utf-8"))
    return disnake.File(buffer, filename=f"{palette_name}.csv")


def make_json_palette(color_hex, color_names, palette_name) -> disnake.File:
    content = "{\n"
    for i in range(len(color_hex)):
        hex = color_hex[i]
        name = color_names[i] if color_names else hex
        content += f'\t"{name}": "{hex}"'
        if i < len(color_hex) - 1:
            content += ","
        content += "\n"
    content += "}"

    buffer = BytesIO(content.encode("utf-8"))
    return disnake.File(buffer, filename=f"{palette_name}.json")
