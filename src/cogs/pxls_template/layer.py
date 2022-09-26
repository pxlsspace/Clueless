from __future__ import annotations

import time

import disnake
from disnake.ext import commands
from PIL import Image

from main import tracked_templates
from utils.arguments_parser import MyParser
from utils.discord_utils import CreateTemplateView, get_image_url, image_to_file
from utils.pxls.template_manager import Combo, layer
from utils.setup import stats


class Layer(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="layer")
    async def _layer(
        self,
        inter: disnake.AppCmdInter,
        templates: str,
    ):
        """Layer several templates.

        Parameters
        ----------
        templates: List of templates (URL or name) separated by a space (last goes above) (use ! to exclude one).
        """
        await inter.response.defer()
        # Remove unused entries, equal to None
        template_uris = templates.split(" ")
        await self.layer(inter, template_uris)

    @commands.command(
        name="layer",
        description="Layer several templates.",
        usage="<templates>",
        help="""
            - `<templates>`: List of templates (URL or name) separated by a space (last goes above) (use `!` in front of a template to exclude it).
            """,
    )
    async def p_layer(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("templates", nargs="+")

        try:
            parsed_args, _ = parser.parse_known_args(args)
            template_uris = parsed_args.templates
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        async with ctx.typing():
            await self.layer(ctx, template_uris)

    @staticmethod
    async def layer(ctx, template_uris):
        try:
            templates = await tracked_templates.get_templates(template_uris)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        start = time.time()
        ox, oy, palettized_array = layer(templates)
        if palettized_array.size == 0:
            return await ctx.send("❌ No placeable pixels in the layered template.")
        img = Image.fromarray(stats.palettize_array(palettized_array))
        end = time.time()

        embed = disnake.Embed(color=0x66C5CC, title="Layered")
        embed.set_footer(text=f"Layered in {round((end-start),3)}s")
        file = await image_to_file(img, "layered.png", embed)
        # Use the combo object here because it doesn't generate a placeable mask
        template = Combo(None, palettized_array, ox, oy, None, None, None)
        view = CreateTemplateView(ctx, template)
        m = await ctx.send(file=file, embed=embed, view=view)

        # save the URL of the image sent to use it to generate templates later
        if isinstance(ctx, disnake.AppCmdInter):
            m = await ctx.original_message()
        view.template_image_url = get_image_url(m.embeds[0].image)
        view.message = m


def setup(bot: commands.Bot):
    bot.add_cog(Layer(bot))
