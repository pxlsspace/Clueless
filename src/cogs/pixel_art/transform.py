import disnake
from disnake.ext import commands
from io import BytesIO
from PIL import Image, ImageOps

from utils.discord_utils import get_image_from_message, image_to_file


class Transform(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="flip")
    async def _flip(self, inter: disnake.AppCmdInter, image: str = None):
        """Flip an image vertically.

        Parameters
        ----------
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.flip(inter, image)

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
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        image = Image.open(BytesIO(img_bytes))
        image = image.convert("RGBA")

        flipped = ImageOps.mirror(image)

        embed = disnake.Embed(title="Vertical Flip", color=0x66C5CC)
        file = image_to_file(flipped, "flipped.png", embed)
        await ctx.send(embed=embed, file=file)

    @commands.slash_command(name="hflip")
    async def _hflip(self, inter: disnake.AppCmdInter, image: str = None):
        """Flip an image horizontally.

        Parameters
        ----------
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.hflip(inter, image)

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
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        image = Image.open(BytesIO(img_bytes))
        image = image.convert("RGBA")

        flipped = ImageOps.flip(image)

        embed = disnake.Embed(title="Horizontal Flip", color=0x66C5CC)
        file = image_to_file(flipped, "flipped.png", embed)
        await ctx.send(embed=embed, file=file)


def setup(bot: commands.Bot):
    bot.add_cog(Transform(bot))
