import disnake
from disnake.ext import commands
from PIL import ImageOps

from utils.discord_utils import InterImage, get_image_from_message, image_to_file


class Transform(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="flip")
    async def _flip(self, inter):
        """Flip images."""
        pass

    @_flip.sub_command(name="vertically")
    async def _vertically(self, inter: disnake.AppCmdInter, image: InterImage):
        """Flip an image vertically.

        Parameters
        ----------
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.flip(inter, image.url)

    @commands.command(
        name="flip",
        usage="<image|url>",
        description="Flip an image vertically.",
        help="""`<url|image>`: an image URL or an attached image""",
        aliases=["mirror", "vflip"],
    )
    async def p_flip(self, ctx, url=None):
        async with ctx.typing():
            await self.flip(ctx, url)

    async def flip(self, ctx, url=None):
        # get the input image
        try:
            image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        flipped = ImageOps.mirror(image)

        embed = disnake.Embed(title="Vertical Flip", color=0x66C5CC)
        file = await image_to_file(flipped, "flipped.png", embed)
        await ctx.send(embed=embed, file=file)

    @_flip.sub_command(name="horizontally")
    async def _horizontally(self, inter: disnake.AppCmdInter, image: InterImage):
        """Flip an image horizontally."""
        await inter.response.defer()
        await self.hflip(inter, image.url)

    @commands.command(
        name="hflip",
        usage="<image|url>",
        description="Flip an image horizontally.",
        help="""`<url|image>`: an image URL or an attached image""",
    )
    async def p_hflip(self, ctx, url=None):
        async with ctx.typing():
            await self.hflip(ctx, url)

    async def hflip(self, ctx, url=None):
        # get the input image
        try:
            image, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        flipped = ImageOps.flip(image)

        embed = disnake.Embed(title="Horizontal Flip", color=0x66C5CC)
        file = await image_to_file(flipped, "flipped.png", embed)
        await ctx.send(embed=embed, file=file)


def setup(bot: commands.Bot):
    bot.add_cog(Transform(bot))
