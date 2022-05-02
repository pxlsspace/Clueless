import disnake
import numpy as np
from os import path
from PIL import Image
from io import BytesIO
from disnake.ext import commands

from utils.discord_utils import (
    UserConverter,
    get_image_from_message,
    get_url,
)
from utils.image.gif_saver import save_transparent_gif
from utils.utils import in_executor


class Pet(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="pet")
    async def _pet(
        self,
        inter: disnake.AppCmdInter,
        target: disnake.User = None,
        image: str = None,
    ):
        """
        Pet someone or something.

        Parameters
        ----------
        target: The user to pet.
        image: The image or emote to pet.
        """
        url = None
        if image:
            url = image
        if target:
            url = target.display_avatar.url
        await inter.response.defer()
        await self.pet(inter, url)

    @commands.command(
        name="pet",
        aliases=["pat"],
        usage="<user|emoji|image|url|>",
        description="Pet someone or something.",
        help="""
            - `<user|emoji|image|url>`: the user/emoji/image to pet""",
    )
    async def p_pet(self, ctx, target=None):
        if target and get_url(target) is None:
            try:
                user = await UserConverter().convert(ctx, target)
            except commands.UserNotFound as e:
                return await ctx.send(f"❌ {e}")
            target = user.display_avatar.url
        async with ctx.typing():
            await self.pet(ctx, target)

    async def pet(self, ctx, target=None):
        try:
            img, url = await get_image_from_message(ctx, target, return_type="image")
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        pet_img = await pet(img)
        file = disnake.File(fp=pet_img, filename="pet.gif")
        await ctx.send(file=file)


resolution = (112, 112)
nb_frames = 10
delay = 25  # ms
petpet_folder = path.abspath(
    path.join(path.dirname(__file__), "..", "..", "resources", "pet")
)
petpet_images = []
for i in range(nb_frames):
    pet_img = Image.open(path.join(petpet_folder, f"pet{i}.gif"))
    pet_img = pet_img.convert("RGBA").resize(resolution)
    petpet_images.append(pet_img)


# from https://github.com/camprevail/pet-pet-gif/blob/main/petpetgif/petpet.py
@in_executor()
def pet(img: Image.Image) -> Image.Image:
    """Make a "petpet" gif from an image"""
    frames = []

    base = img.convert("RGBA").resize(resolution)

    # set semi transparent pixels fully transparent
    base_array = np.array(base)
    base_array[base_array[:, :, -1] < 128] = [0, 0, 0, 0]
    base = Image.fromarray(base_array)

    for i in range(nb_frames):
        squeeze = i if i < nb_frames / 2 else nb_frames - i
        width = 0.8 + squeeze * 0.02
        height = 0.8 - squeeze * 0.05
        offsetX = (1 - width) * 0.5 + 0.1
        offsetY = (1 - height) - 0.08

        canvas = Image.new("RGBA", size=resolution, color=(0, 0, 0, 0))
        canvas.paste(
            base.resize((round(width * resolution[0]), round(height * resolution[1]))),
            (round(offsetX * resolution[0]), round(offsetY * resolution[1])),
        )
        pet_img = petpet_images[i]
        canvas.paste(pet_img, mask=pet_img)
        frames.append(canvas)

    animated_img = BytesIO()
    save_transparent_gif(frames, durations=delay, save_file=animated_img)
    animated_img.seek(0)
    return animated_img


def setup(bot: commands.Bot):
    bot.add_cog(Pet(bot))
