from disnake.ext import commands
import disnake
import asyncio
import time
import numpy as np
from PIL import Image

from utils.discord_utils import (
    AuthorView,
    autocomplete_log_canvases,
    autocomplete_canvases,
    format_number,
    image_to_file,
)
from utils.setup import db_canvas, db_users, stats
from utils.pxls.archives import (
    check_key,
    get_canvas_image,
    get_user_placemap,
    check_canvas_code,
)
from utils.image.image_utils import highlight_image
from utils.log import get_logger

logger = get_logger(__name__)


class PlacemapView(AuthorView):
    message = disnake.Message

    def __init__(self, author: disnake.User, placemap_image, canvas_code):
        super().__init__(author)
        self.placemap_image = placemap_image
        self.canvas_code = canvas_code

    async def on_timeout(self) -> None:
        await self.message.edit(view=None)

    @disnake.ui.button(
        label="Layer over canvas (dark)", style=disnake.ButtonStyle.blurple
    )
    async def layer_dark(self, button: disnake.Button, inter: disnake.MessageInteraction):
        await self.layer(button, inter, dark=True)

    @disnake.ui.button(
        label="Layer over canvas (light)", style=disnake.ButtonStyle.blurple
    )
    async def layer_light(
        self, button: disnake.Button, inter: disnake.MessageInteraction
    ):
        await self.layer(button, inter, dark=False)

    async def layer(
        self, button: disnake.Button, inter: disnake.MessageInteraction, dark: bool
    ):
        await inter.response.defer()
        button.disabled = True

        canvas_image = get_canvas_image(self.canvas_code).convert("RGBA")
        highlighted_image = highlight_image(
            np.array(self.placemap_image),
            np.array(canvas_image),
            background_color=(0, 0, 0, 255) if dark else (255, 255, 255, 255),
        )

        embed = disnake.Embed(
            title=f"Layered Placemap ({'dark' if dark else 'light'})", color=0x66C5CC
        )
        file = await image_to_file(
            highlighted_image,
            f"placemap_c{self.canvas_code}_layered_{'dark' if dark else 'light'}.png",
            embed,
        )
        await inter.message.edit(view=self)
        await inter.send(embed=embed, file=file)


class Placemap(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.cd = commands.CooldownMapping.from_cooldown(1, 20, commands.BucketType.user)

    @commands.slash_command(name="placemap")
    async def _placemap(
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

    @commands.command(
        name="placemap",
        usage="<canvas code>",
        description="Get your placemap and personal stats for a given canvas.",
    )
    async def p_placemap(self, ctx, *, canvas_code):
        async with ctx.typing():
            await self.placemap(ctx, canvas_code)

    async def placemap(self, ctx, canvas_code_input):
        # check cooldown
        bucket = self.cd.get_bucket(ctx)
        retry_after = bucket.get_retry_after()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after, self.cd.type)

        canvas_code = check_canvas_code(canvas_code_input)
        if canvas_code is None:
            return await ctx.send(
                f":x: The given canvas code `{canvas_code_input}` is invalid."
            )

        canvas_codes = await db_canvas.get_logs_canvases()
        if canvas_code not in canvas_codes:
            return await ctx.send(
                ":x: This canvas code is invalid or doesn't have logs yet."
            )
        log_key = await db_users.get_key(ctx.author.id, canvas_code)
        if log_key is None:
            if isinstance(ctx, commands.Context):
                return await ctx.send(
                    f":x: You haven't added your log key for this canvas, use `>setkey` to add it.\n(You can also use the slash command `/placemap canvas-code:{canvas_code_input}` to input your log key directly)"
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
                title=f"Canvas {canvas_code} Placemap",
                description="<a:catload:957251966826860596> **Generating your placemap...**\n*(this can take a while)*",
                color=0x66C5CC,
            )
        )
        if isinstance(ctx, (disnake.AppCmdInter, disnake.ModalInteraction)):
            m = await ctx.original_message()

        self.cd.update_rate_limit(ctx)
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

        if nb_placed == 0:
            return await m.edit(
                embed=disnake.Embed(
                    title="Invalid key",
                    color=disnake.Color.red(),
                    description=f":x: No pixels found for this canvas ({canvas_code}).\nMake sure that you used the correct log key with the correct canvas.",
                )
            )
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

        view = PlacemapView(ctx.author, placemap_image, canvas_code)
        view.message = await m.edit(embed=embed, file=placemap_file, view=view)
        if view.message is None:
            view.message = await ctx.original_message()

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
        aliases=["c"],
    )
    async def p_canvas(self, ctx, *, canvas_code):
        async with ctx.typing():
            await self.canvas(ctx, canvas_code)

    async def canvas(self, ctx, canvas_code_input):

        canvas_code = check_canvas_code(canvas_code_input)
        if canvas_code is None:
            return await ctx.send(
                f":x: The given canvas code `{canvas_code_input}` is invalid."
            )

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
