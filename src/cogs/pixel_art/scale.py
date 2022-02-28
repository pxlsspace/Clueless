import disnake
import numpy as np
import time
from disnake.ext import commands
from io import BytesIO
from PIL import Image

from utils.image.image_utils import remove_white_space, get_image_scale
from utils.pxls.template_manager import detemplatize
from utils.discord_utils import get_image_from_message, image_to_file


class Scale(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="downscale")
    async def _downscale(self, inter: disnake.AppCmdInter, image: str = None):
        """Downscale an upscaled pixel art.

        Parameters
        ----------
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.downscale(inter, image)

    @commands.command(
        name="downscale",
        usage="<image|url>",
        description="Downscale an upscaled pixel art.",
        help="""- `<url|image>`: an image URL or an attached image""",
    )
    async def p_downscale(self, ctx, url=None):
        async with ctx.typing():
            await self.downscale(ctx, url)

    async def downscale(self, ctx, url=None):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        input_image = Image.open(BytesIO(img_bytes))
        input_image = input_image.convert("RGBA")  # Convert to RGBA
        input_image = remove_white_space(input_image)  # Remove extra space
        input_image_array = np.array(input_image)
        start = time.time()
        scale = await self.bot.loop.run_in_executor(
            None, get_image_scale, input_image_array
        )
        if not scale or scale == 1:
            msg = "Make sure that:\n"
            msg += "- The image doesn't have artificats (it needs to be a good quality image)\n"
            msg += "- The image isn't already at its smallest possible scale"
            error_embed = disnake.Embed(
                title=":x: **Couldn't downscale that image**",
                description=msg,
                color=0xFF3621,
            )
            return await ctx.send(embed=error_embed)

        true_width = input_image.width // scale
        downscaled_array = await self.bot.loop.run_in_executor(
            None, detemplatize, input_image_array, true_width
        )
        end = time.time()
        downscaled_image = Image.fromarray(downscaled_array)

        embed = disnake.Embed(title="Downscale", color=0x66C5CC)
        embed.description = "Original pixel size: **{0}x{0}**\n".format(scale)
        embed.description += (
            "`{0.shape[1]}x{0.shape[0]}` → `{1.shape[1]}x{1.shape[0]}`".format(
                input_image_array, downscaled_array
            )
        )
        embed.set_footer(text=f"Downscaled in {round((end - start), 3)}s")
        downscaled_file = image_to_file(downscaled_image, "downscaled.png", embed=embed)
        await ctx.send(embed=embed, file=downscaled_file)

    @commands.slash_command(name="upscale")
    async def _upscale(self, inter: disnake.AppCmdInter, scale: int, image: str = None):
        """Upscale an image to the desired scale.

        Parameters
        ----------
        scale: The new scale for the image (ex: 2 means the image will be 2x bigger).
        image: The URL of the image.
        """
        await inter.response.defer()
        await self.upscale(inter, scale, image)

    @commands.command(
        name="upscale",
        usage="<scale> <image|url>",
        description="Upscale an image to the desired scale.",
        help="""- `scale`: the new scale for the image (ex: 2 means the image will be 2x bigger)
                - `<url|image>`: an image URL or an attached image""",
    )
    async def p_upscale(self, ctx, scale, url=None):
        async with ctx.typing():
            await self.upscale(ctx, scale, url)

    async def upscale(self, ctx, scale, url=None):
        # check on the scale
        err_msg = "The scale value must be an integer."
        try:
            scale = int(scale)
        except ValueError:
            return await ctx.send(f"❌ {err_msg}")
        if scale < 1:
            return await ctx.send(f"❌ {err_msg}")

        # get the input image
        try:
            img_bytes, url = await get_image_from_message(ctx, url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        input_image = Image.open(BytesIO(img_bytes))
        input_image = input_image.convert("RGBA")

        # check that the image won't be too big
        final_width = scale * input_image.width
        final_height = scale * input_image.height
        limit = 6000
        if final_width > limit or final_height > limit:
            err_msg = (
                "The resulting image would be too big with this scale ({}x{}).".format(
                    final_width, final_height
                )
            )
            return await ctx.send(f"❌ {err_msg}")

        res_image = input_image.resize((final_width, final_height), Image.NEAREST)

        embed = disnake.Embed(title="Upscale", color=0x66C5CC)
        embed.description = "Final pixel size: **{0}x{0}**\n".format(scale)
        embed.description += "`{0.width}x{0.height}` → `{1.width}x{1.height}`".format(
            input_image, res_image
        )
        res_file = image_to_file(res_image, "upscaled.png", embed=embed)
        await ctx.send(embed=embed, file=res_file)


def setup(bot: commands.Bot):
    bot.add_cog(Scale(bot))
