from __future__ import annotations
import time

import disnake
from disnake.ext import commands
from PIL import Image

from main import tracked_templates
from utils.arguments_parser import MyParser
from utils.pxls.template_manager import (
    get_template_from_url,
    parse_template,
    layer,
)
from utils.setup import stats
from utils.discord_utils import image_to_file


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
        templates: List of templates (URL or name) separated by a space (first goes above).
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
            - `<templates>`: List of templates (URL or name) separated by a space (first goes above).
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
    async def _clean(templates_uris: list[str]):
        templates = []
        for i, template_name in enumerate(templates_uris):
            if parse_template(template_name) is not None:
                try:
                    template = await get_template_from_url(template_name)
                except ValueError:
                    raise ValueError(
                        f"Please use a valid template link for template {i}."
                    )
            else:
                template = tracked_templates.get_template(template_name, None, False)
                if template is None:
                    raise ValueError(f"No template named `{template_name}` found.")
            templates.append(template)
        return templates

    @staticmethod
    async def layer(ctx, template_uris):
        try:
            templates = await Layer._clean(template_uris)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        start = time.time()
        _, _, palettized_array = layer(templates)
        if palettized_array.size == 0:
            return await ctx.send("❌ No placeable pixels in the layered template.")
        img = Image.fromarray(stats.palettize_array(palettized_array))
        end = time.time()
        embed = disnake.Embed(color=0x66C5CC, title="Layered")
        embed.set_footer(text=f"Layered in {round((end-start),3)}s")
        file = image_to_file(img, "layered.png", embed)
        return await ctx.send(file=file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Layer(bot))
