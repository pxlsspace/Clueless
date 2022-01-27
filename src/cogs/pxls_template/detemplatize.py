import discord
import numpy as np

from PIL import Image
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

from utils.discord_utils import format_number, image_to_file
from utils.pxls.detemplatize import get_progress, get_template
from utils.setup import GUILD_IDS
from utils.utils import make_progress_bar

class Detemplatize(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @cog_ext.cog_slash(
        name="detemplatize",
        description="Get the image from a template URL.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="url",
                description="The URL of the template you want to detemplatize.",
                option_type=3,
                required=True
            )]
    )
    async def _detemplatize(self,ctx:SlashContext, url):
        await ctx.defer()
        await self.detemplatize(ctx,url)

    @commands.command(
        name="detemplatize",
        description="Get the image from a template URL.",
        usage = "<url>",
        aliases=["detemp"])
    async def p_detemplatize(self, ctx, url:str):

        async with ctx.typing():
            await self.detemplatize(ctx, url)

    async def detemplatize(self, ctx, template_url):
        try:
            (detemp_image,params) = await get_template(template_url)
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        # get template info
        if "title" in params.keys():
            title = params["title"]
        else:
            title = "`N/A`"

        detemp_array = np.array(detemp_image)
        total_pixels = np.sum(detemp_array[:,:,3] == 255)
        (correct_pixels, total_placeable, progress_image) = await self.client.loop.run_in_executor(None, get_progress, detemp_array, params, False)
        correct_percentage = round((correct_pixels/total_placeable)*100,2)

        total_placeable = format_number(int(total_placeable))
        correct_pixels = format_number(int(correct_pixels))
        total_pixels = format_number(int(total_pixels))

        embed = discord.Embed(title="**Detemplatize**", color=0x66c5cc)
        embed.description = f"**Title**: {title}\n"
        embed.description += f"**Size**: {total_pixels} pixels ({detemp_image.width}x{detemp_image.height})\n"
        embed.description += f"**Coordinates**: ({params['ox']}, {params['oy']})\n"
        embed.description += f"**Templatized Image**: [[click to open]]({params['template']})\n"
        embed.description += f"**Progress**: {correct_percentage}% done ({correct_pixels}/{total_placeable})\n"
        embed.description += f"[Template link]({template_url})"

        detemp_file = image_to_file(detemp_image,"detemplatize.png",embed)
        await ctx.send(file=detemp_file,embed=embed)


    @cog_ext.cog_slash(
        name="progress",
        description="Check the progress of a template.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="url",
                description="The URL of the template you want to check.",
                option_type=3,
                required=True
            )]
    )
    async def _progress(self,ctx:SlashContext, url):
        await ctx.defer()
        await self.progress(ctx,url)

    @commands.command(
        name="progress",
        description="Check the progress of a template.",
        usage = "<url>")
    async def p_progress(self, ctx, url:str):

        async with ctx.typing():
            await self.progress(ctx, url)

    async def progress(self, ctx, template_url):
        try:
            (detemp_image,params) = await get_template(template_url)
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        if "title" in params.keys():
            title = params["title"]
        else:
            title = "`N/A`"

        # get the progress stats
        detemp_array = np.array(detemp_image)
        (correct_pixels, total_amount, progress_image) = await self.client.loop.run_in_executor(None, get_progress, detemp_array, params)
        if total_amount == 0:
            return await ctx.send(":x: The template seems to be outside the canvas, make sure it's correctly positioned.")
        correct_percentage = round((correct_pixels/total_amount)*100,2)
        togo_pixels = total_amount - correct_pixels

        # make the progress bar
        bar = make_progress_bar(correct_percentage)

        # format the progress stats
        total_amount = format_number(int(total_amount))
        correct_pixels = format_number(int(correct_pixels))
        togo_pixels = format_number(int(togo_pixels))

        embed = discord.Embed(title="**Progress**", color=0x66c5cc)
        embed.description = f"**Title**: {title}\n"
        embed.description += f"**Correct pixels**: {correct_pixels}/{total_amount}\n"
        embed.description += f"**Pixels to go**: {togo_pixels}\n"
        embed.description += f"**Progress**:\n|`{bar}`| {correct_percentage}%\n"
        embed.description += f"[Template link]({template_url})"
        embed.set_footer(text="Green = correct, Red = wrong, Blue = not placeable")

        detemp_file = image_to_file(progress_image,"progress.png",embed)
        await ctx.send(file=detemp_file,embed=embed)

def setup(client):
    client.add_cog(Detemplatize(client))
    