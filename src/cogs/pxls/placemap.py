from disnake.ext import commands
import disnake
import asyncio
import time
from PIL import Image

from utils.discord_utils import (
    autocomplete_log_canvases,
    autocomplete_canvases,
    format_number,
    image_to_file,
)
from utils.setup import db_canvas, db_users, stats
from utils.pxls.archives import check_key, get_canvas_image, get_user_placemap
from utils.log import get_logger

logger = get_logger(__name__)


class Placemap(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.cooldown(1, 20, commands.BucketType.user)
    @commands.slash_command(name="placemap")
    async def _cooldown(
        self,
        inter: disnake.AppCmdInter,
        canvas_code: str = commands.Param(
            name="canvas-code", autocomplete=autocomplete_log_canvases
        ),
    ):
        """Get your placemap and personal stats for a given canvas.

        Parameters
        ----------
        canvas_code: The canvas code for which you want to see your stats.
        """
        await self.placemap(inter, canvas_code)

    @commands.cooldown(1, 20, commands.BucketType.user)
    @commands.command(
        name="placemap",
        usage="<canvas code>",
        description="Get your placemap and personal stats for a given canvas.",
    )
    async def p_placemap(self, ctx, canvas_code):
        async with ctx.typing():
            await self.placemap(ctx, canvas_code)

    async def placemap(self, ctx, canvas_code):
        canvas_codes = await db_canvas.get_logs_canvases()
        if canvas_code not in canvas_codes:
            return await ctx.send(
                ":x: This canvas code is invalid or doesn't have logs yet."
            )
        log_key = await db_users.get_key(ctx.author.id, canvas_code)
        if log_key is None:
            if isinstance(ctx, commands.Context):
                return await ctx.send(
                    ":x: You haven't added your log key for this canvas, use `>setkey` to add it (or use `/placemap <canvas code>` to input your log key directly)"
                )
            else:
                await ctx.response.send_modal(
                    title=f"C{canvas_code} Placemap",
                    custom_id="put_log_key",
                    components=[
                        disnake.ui.TextInput(
                            label=f"Log key for canvas {canvas_code}",
                            placeholder="Log Key (will stay 100% private)",
                            custom_id="log_key",
                            style=disnake.TextInputStyle.paragraph,
                        ),
                    ],
                )

                # Wait until the user submits the modal.
                try:
                    modal_inter: disnake.ModalInteraction = await self.bot.wait_for(
                        "modal_submit",
                        check=lambda i: i.custom_id == "put_log_key"
                        and i.author.id == ctx.author.id,
                        timeout=300,
                    )
                except asyncio.TimeoutError:
                    return

            log_key = modal_inter.text_values["log_key"]
            try:
                log_key = check_key(log_key)
            except ValueError as e:
                return await modal_inter.response.send_message(f":x: {e}")

            await modal_inter.response.defer()
            ctx = modal_inter
        elif isinstance(ctx, disnake.AppCmdInter):
            await ctx.response.defer()

        m = await ctx.send(
            embed=disnake.Embed(
                description="<a:catload:957251966826860596> **Generating your placemap...**\n*(this can take a while)*",
                color=0x66C5CC,
            )
        )
        if isinstance(ctx, (disnake.AppCmdInter, disnake.ModalInteraction)):
            m = await ctx.original_message()

        start = time.time()
        try:
            (
                placemap_image,
                nb_undo,
                nb_placed,
                nb_replaced_by_others,
                nb_replaced_by_you,
            ) = await get_user_placemap(canvas_code, log_key)
        except Exception:
            logger.exception(
                f"Error while generating c{canvas_code} placemap for {ctx.author}"
            )
            return await m.edit(
                embed=disnake.Embed(
                    color=disnake.Color.red(),
                    description=":x: An error occurred while generating the placemap.",
                )
            )
        end = time.time()

        canvas_pixels = nb_placed - nb_undo
        survived = canvas_pixels - nb_replaced_by_others - nb_replaced_by_you
        if canvas_pixels == 0:
            survived_percentage = "N/A"
        else:
            survived_percentage = (survived / canvas_pixels) * 100
        embed = disnake.Embed(title=f"Canvas {canvas_code} Placemap", color=0x66C5CC)
        stats = f"Canvas Pixels: `{format_number(canvas_pixels)}`\n"
        stats += f"Undos: `{format_number(nb_undo)}`\n"
        stats += f"Survived pixels: `{format_number(survived)}` (`{format_number(survived_percentage)}`%)\n"
        stats += f"Replaced by you: `{format_number(nb_replaced_by_you)}`\n"
        stats += f"Replaced by others: `{format_number(nb_replaced_by_others)}`\n"

        embed.add_field(name="Some Stats", value=stats, inline=False)
        embed.add_field(name="Your Placemap", value="\u200b", inline=False)
        embed.set_footer(text=f"Generated in {format_number(end-start)}s")
        placemap_file = await image_to_file(
            placemap_image, f"placemap_c{canvas_code}.png", embed
        )
        return await m.edit(embed=embed, file=placemap_file)

    @commands.slash_command(name="canvas")
    async def _canvas(
        self,
        inter: disnake.AppCmdInter,
        canvas_code: str = commands.Param(
            name="canvas-code", autocomplete=autocomplete_canvases
        ),
    ):
        """Get the final image for any canvas.

        Parameters
        ----------
        canvas_code: The code of the canvas want to see the image.
        """
        await inter.response.defer()
        await self.canvas(inter, canvas_code)

    @commands.command(
        name="canvas",
        usage="<canvas code>",
        description="Get the final image for any canvas.",
    )
    async def p_canvas(self, ctx, canvas_code):
        async with ctx.typing():
            await self.canvas(ctx, canvas_code)

    async def canvas(self, ctx, canvas_code):

        current_canvas = await stats.get_canvas_code()
        if canvas_code == current_canvas:
            canvas_array = stats.board_array
            canvas_array = stats.palettize_array(canvas_array)
            canvas_image = Image.fromarray(canvas_array)
            title = f"Canvas {canvas_code} (current)"
        else:
            canvas_image = get_canvas_image(canvas_code)
            if canvas_image is None:
                return await ctx.send(
                    ":x: This canvas code is invalid or doesn't have a final image."
                )
            title = f"Canvas {canvas_code} final"

        embed = disnake.Embed(title=title, color=0x66C5CC)
        canvas_file = await image_to_file(
            canvas_image, f"Pxls_Canvas_{canvas_code}.png", embed
        )
        return await ctx.send(embed=embed, file=canvas_file)


def setup(bot: commands.Bot):
    bot.add_cog(Placemap(bot))
