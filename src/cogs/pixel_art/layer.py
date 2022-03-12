from __future__ import annotations
import time

import disnake
from disnake.ext import commands
from PIL import Image

from main import tracked_templates
from cogs.pxls_template.progress import autocomplete_templates
from utils.arguments_parser import MyParser
from utils.pxls.template_manager import get_template_from_url, parse_template, layer
from utils.setup import stats
from utils.discord_utils import image_to_file


class Layer(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="layer")
    async def _reduce(
        self,
        inter: disnake.AppCmdInter,
        first_template: str = commands.Param(autocomplete=autocomplete_templates),
        second_template: str = commands.Param(autocomplete=autocomplete_templates),
        third_template: str = commands.Param(
            default=None, autocomplete=autocomplete_templates
        ),
        fourth_template: str = commands.Param(
            default=None, autocomplete=autocomplete_templates
        ),
        fifth_template: str = commands.Param(
            default=None, autocomplete=autocomplete_templates
        ),
    ):
        """Layer several images.

        Parameters
        ----------
        first_template: A template link or name in the tracker.
        second_template: A template link or name in the tracker.
        ...etc
        """
        await inter.response.defer()
        # Remove unused entries, equal to None
        template_uris = [
            temp
            for temp in [
                first_template,
                second_template,
                third_template,
                fourth_template,
                fifth_template,
            ]
            if temp
        ]
        templates = await self._clean(inter, template_uris)
        await self._layer(inter, templates)

    @commands.command(
        name="layer",
        description="Layer templates.",
        usage="<first template name|link> <second template name|link> ...",
        help="""
            - `<template name|link>`: a template link or name in the tracker
            """,
    )
    async def p_layer(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("templates", nargs="+")

        try:
            parsed_args, _ = parser.parse_known_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        async with ctx.typing():
            templates = await self._clean(ctx, parsed_args.templates)
            await self._layer(ctx, templates)

    @staticmethod
    async def _clean(ctx, templates_uris: list[str]):
        templates = []
        for template_name in templates_uris:
            if parse_template(template_name) is not None:
                try:
                    template = await get_template_from_url(template_name)
                except ValueError as e:
                    return await ctx.send(f":x: Error while parsing {template_name}: {e}")
            else:
                template = tracked_templates.get_template(template_name, None, False)
                if template is None:
                    return await ctx.send(f":x: No template named `{template_name}` found.")
            templates.append(template)
        return templates

    @staticmethod
    async def _layer(ctx, templates):
        start = time.time()
        palettized_array = layer(templates)
        img = Image.fromarray(stats.palettize_array(palettized_array))
        end = time.time()
        embed = disnake.Embed(color=0x00BB00, title="Layered")
        embed.set_footer(text=f"Layered in {round((end-start),3)}s")
        file = image_to_file(img, "layered.png", embed)
        await ctx.send(file=file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Layer(bot))
