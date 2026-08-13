import asyncio
from io import BytesIO

import disnake
from disnake.ext import commands
from PIL import Image

from utils.discord_utils import format_emoji, get_image_from_message, number_emoji
from utils.image.img_to_gif import img_to_animated_gif


class Emote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(
        name="emote",
        default_member_permissions=disnake.Permissions(manage_emojis=True),
    )
    async def _emote(self, inter: disnake.AppCmdInter):
        """Manage the server custom emotes."""
        pass  # group root is a no-op

    @_emote.sub_command(name="add")
    @commands.has_permissions(manage_emojis=True)
    async def _emote_add(
        self,
        inter: disnake.AppCmdInter,
        name: str,
        image: disnake.Attachment = None,
        url: str = None,
    ):
        """Add an image as a custom emoji.

        Parameters
        ----------
        name: Name of the emoji to add.
        image: An attached image to use.
        url: An image URL to use (if no attachment)."""
        await inter.response.defer()
        await self.add(inter, name, url=url, image=image)

    @_emote.sub_command(name="remove")
    @commands.has_permissions(manage_emojis=True)
    async def _emote_remove(self, inter: disnake.AppCmdInter, name: str):
        """Remove a custom emoji from the server.

        Parameters
        ----------
        name: Name of the emoji to remove."""
        await self.remove(inter, name)

    @_emote.sub_command(name="list")
    async def _emote_list(self, inter: disnake.AppCmdInter):
        """Show all of the server custom emojis and their names."""
        await inter.response.defer()
        await self.list(inter)

    @_emote.sub_command(name="number")
    async def _emote_number(self, inter: disnake.AppCmdInter):
        """Give the number of emojis and animated emojis on the server."""
        await inter.response.defer()
        await self.number(inter)

    async def add(self, ctx, name, url=None, image=None):

        # get the input image
        if image is not None:
            # slash attachment path
            img_bytes = await image.read()
        else:
            # prefix / URL path (unchanged)
            try:
                img_bytes, url = await get_image_from_message(
                    ctx, url, return_type="bytes"
                )
            except ValueError as e:
                return await ctx.send(f"❌ {e}")

        # check if there is enough emote space
        nb_emoji, nb_animated = await number_emoji(ctx)
        if nb_emoji + nb_animated >= 2 * ctx.guild.emoji_limit:
            return await ctx.send("❌ The server is full")

        # convert the emoji to gif if the server is full
        if nb_emoji >= ctx.guild.emoji_limit:
            stream = BytesIO(img_bytes)
            img = Image.open(stream)
            if not (hasattr(img, "is_animated") and img.is_animated):
                img_bytes = img_to_animated_gif(img)

        # adding the emote to the server
        try:
            emoji = await asyncio.wait_for(
                ctx.guild.create_custom_emoji(name=name, image=img_bytes), timeout=10.0
            )
        except disnake.InvalidArgument:
            return await ctx.send(
                "❌ Invalid image type. Only PNG, JPEG and GIF are supported."
            )
        except disnake.HTTPException as e:
            if e.code == 30008:
                return await ctx.send(
                    f"❌ Maximum number of emojis reached ({ctx.guild.emoji_limit})"
                )
            else:
                return await ctx.send(f"❌ {e.text}")
        except asyncio.TimeoutError:
            return await ctx.send(
                "❌ You're getting ratelimited by discord, retry again in 20/30 min"
            )

        await ctx.send("✅ Successfully added the emoji {}".format(format_emoji(emoji)))

    async def remove(self, ctx, name):
        emotes = [x for x in ctx.guild.emojis if x.name == name]
        if len(emotes) == 0:
            return await ctx.send("❌ There is no emote with that name on this server.")
        nb_emote = len(emotes)
        deleted_emojis = ""
        for emote in emotes:
            deleted_emojis += f" {format_emoji(emote)}"

        await ctx.send(
            f"✅ {nb_emote} emote(s) with the name `:{name}:` have been deleted:"
            + deleted_emojis
        )
        for emote in emotes:
            await emote.delete()

    async def list(self, ctx):
        emotes = ctx.guild.emojis
        if len(emotes) == 0:
            return await ctx.send("❌ There are no emotes in this server")
        res = [""]
        i = 0
        for emote in emotes:
            emote_text = f"{format_emoji(emote)} `:{emote.name}:`\n"
            if len(res[i]) + len(emote_text) > 2000:
                i += 1
                res.append("")
            res[i] += emote_text

        # print(len(res))
        for msg in res:
            await ctx.send(msg)

    async def number(self, ctx):
        nb_static, nb_anim = await number_emoji(ctx)
        await ctx.send(
            f"There are {nb_anim+nb_static} emojis in this server:\n\t- {nb_static} emojis\n\t- {nb_anim} animated emojis"
        )


def setup(bot: commands.Bot):
    bot.add_cog(Emote(bot))
