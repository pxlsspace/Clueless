from __future__ import annotations
import disnake
import numpy as np
from disnake.ext import commands
from PIL import Image

from main import tracked_templates
from utils.pxls.template_manager import get_template_from_url, layer, parse_template
from utils.setup import stats
from utils.discord_utils import (
    autocomplete_templates,
    image_to_file,
    CreateTemplateView,
)


class TemplateCrop(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="crop-to-canvas")
    async def _croptocanvas(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Crop a template to the canvas boundaries.

        Parameters
        ----------
        template: A template name or URL.
        """
        await inter.response.defer()
        await self.crop(inter, template, type="tocanvas")

    @commands.command(
        name="croptocanvas",
        aliases=["canvascrop", "ctc"],
        description="Crop a template to the canvas boundaries.",
        usage="<template>",
        help="""
            - `<template>`: A template name or URL.
            """,
    )
    async def p_croptocanvas(self, ctx, template):

        async with ctx.typing():
            await self.crop(ctx, template, type="tocanvas")

    @commands.slash_command(name="crop-to-templates")
    async def _croptotemplates(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Crop out all overlaps with other tracked templates.

        Parameters
        ----------
        template: A template name or URL.
        """
        await inter.response.defer()
        await self.crop(inter, template, type="totemplates")

    @commands.command(
        name="croptotemplates",
        aliases=["croptocombo", "ctt"],
        description="Crop out all overlaps with other tracked templates.",
        usage="<template>",
        help="""
            - `<template>`: A template name or URL.
            """,
    )
    async def p_croptotemplates(self, ctx, template):

        async with ctx.typing():
            await self.crop(ctx, template, type="totemplates")

    @commands.slash_command(name="crop-wrong-pixels")
    async def _cropwrongpixels(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Crop out all the current incorrect pixels"

        Parameters
        ----------
        template: A template name or URL.
        """
        await inter.response.defer()
        await self.crop(inter, template, type="cropwrongpixels")

    @commands.command(
        name="cropwrongpixels",
        aliases=["cwp"],
        description="Crop out all the current incorrect pixels.",
        usage="<template>",
        help="""
            - `<template>`: A template name or URL.
            """,
    )
    async def p_cropwrongpixels(self, ctx, template):

        async with ctx.typing():
            await self.crop(ctx, template, type="cropwrongpixels")

    @commands.slash_command(name="replace-wrong-pixels")
    async def _replacewrongpixels(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Replace all the incorrect pixels with what is currently on the canvas."

        Parameters
        ----------
        template: A template name or URL.
        """
        await inter.response.defer()
        await self.crop(inter, template, type="replacewrongpixels")

    @commands.command(
        name="replacewrongpixels",
        aliases=["rwp"],
        description="Replace all the incorrect pixels with what is currently on the canvas.",
        usage="<template>",
        help="""
            - `<template>`: A template name or URL.
            """,
    )
    async def p_replacewrongpixels(self, ctx, template):

        async with ctx.typing():
            await self.crop(ctx, template, type="replacewrongpixels")

    @staticmethod
    async def crop(ctx, template_input, type="tocanvas"):
        if parse_template(template_input) is not None:
            try:
                template = await get_template_from_url(template_input)
            except ValueError as e:
                return await ctx.send(f":x: {e}")
        else:
            template = tracked_templates.get_template(template_input, None, False)
            if template is None:
                return await ctx.send(f":x: No template named `{template_input}` found.")

        if template.total_placeable == 0:
            return await ctx.send(
                ":x: The template seems to be outside the canvas, make sure it's correctly positioned."
            )

        res_array = template.palettized_array.copy()
        # crop to placemap
        res_array[~template.placeable_mask] = 255

        # crop to templates
        if type == "totemplates":
            template_list = tracked_templates.list.copy()
            if template in template_list:
                # exclude the template if it's already in the list
                template_list.remove(template)
            combo_mask = layer(template_list[::-1], crop_to_template=False)[2]
            cropped_combo_mask = template.crop_array_to_template(combo_mask)
            res_array[cropped_combo_mask != 255] = 255
        # crop out wrong pixels
        elif type == "cropwrongpixels":
            template.update_progress()
            wrong_pixels_mask = ~template.placed_mask
            res_array[wrong_pixels_mask == 1] = 255
        # replace wrong pixels with the current board
        elif type == "replacewrongpixels":
            template.update_progress()
            wrong_pixels_mask = np.logical_and(
                ~template.placed_mask, template.placeable_mask
            )
            cropped_board = template.crop_array_to_template(stats.board_array)
            res_array[wrong_pixels_mask == 1] = cropped_board[wrong_pixels_mask == 1]

        if np.all(res_array == 255):
            return await ctx.send("❌ No placeable pixels in the cropped template.")
        img = Image.fromarray(stats.palettize_array(res_array))

        embed = disnake.Embed(color=0x66C5CC, title="Cropped")
        file = await image_to_file(img, "cropped.png", embed)
        view = CreateTemplateView(ctx, template)
        m = await ctx.send(file=file, embed=embed, view=view)

        # save the URL of the image sent to use it to generate templates later
        if isinstance(ctx, disnake.AppCmdInter):
            m = await ctx.original_message()
        view.template_image_url = m.embeds[0].image.url
        view.message = m


def setup(bot: commands.Bot):
    bot.add_cog(TemplateCrop(bot))
