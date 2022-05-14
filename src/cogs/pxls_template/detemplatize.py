import disnake
from PIL import Image
from disnake.ext import commands

from utils.discord_utils import format_number, image_to_file
from utils.pxls.template_manager import get_template_from_url


class Detemplatize(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="detemplatize")
    async def _detemplatize(self, inter: disnake.AppCmdInter, url: str):
        """Get the image from a template URL.

        Parameters
        ----------
        url: The URL of the template you want to detemplatize."""
        await inter.response.defer()
        await self.detemplatize(inter, url)

    @commands.command(
        name="detemplatize",
        description="Get the image from a template URL.",
        usage="<url>",
        aliases=["detemp"],
    )
    async def p_detemplatize(self, ctx, url: str):

        async with ctx.typing():
            await self.detemplatize(ctx, url)

    async def detemplatize(self, ctx, template_url):
        try:
            template = await get_template_from_url(template_url)
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        # get template info
        title = template.title or "`N/A`"
        total_pixels = template.total_size
        total_placeable = template.total_placeable
        correct_pixels = template.update_progress()
        if total_placeable == 0:
            correct_percentage = "NaN"
        else:
            correct_percentage = round((correct_pixels / total_placeable) * 100, 2)

        total_placeable = format_number(int(total_placeable))
        correct_pixels = format_number(int(correct_pixels))
        total_pixels = format_number(int(total_pixels))

        embed = disnake.Embed(title="**Detemplatize**", color=0x66C5CC)
        embed.description = f"**Title**: {title}\n"
        embed.description += (
            f"**Size**: {total_pixels} pixels ({template.width}x{template.height})\n"
        )
        embed.description += f"**Coordinates**: ({template.ox}, {template.oy})\n"
        if not (template.stylized_url).startswith("data:image"):
            embed.description += (
                f"**Templatized Image**: [[click to open]]({template.stylized_url})\n"
            )
        embed.description += f"**Progress**: {correct_percentage}% done ({correct_pixels}/{total_placeable})\n"
        embed.description += f"[Template link]({template.url})"

        detemp_file = await image_to_file(
            Image.fromarray(template.get_array()), "detemplatize.png", embed
        )
        await ctx.send(file=detemp_file, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Detemplatize(bot))
