import asyncio
from io import BytesIO

import disnake
from disnake.ext import commands
from PIL import Image

from utils.discord_utils import (
    InterImage,
    format_emoji,
    get_display_prefix,
    get_image_from_message,
    number_emoji,
)
from utils.image.img_to_gif import img_to_animated_gif


class Emote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    # --- shared helpers (take a resolved image source/name) ---

    async def _do_emote_add(self, ctx, name, image_source):
        # get the input image
        try:
            img_bytes, url = await get_image_from_message(
                ctx, image_source, return_type="bytes"
            )
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        # check if there is enough emote space
        nb_emoji, nb_animated = await number_emoji(ctx)
        if nb_emoji + nb_animated >= 2 * ctx.guild.emoji_limit:
            return await ctx.send(":x: The server is full")

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
                ":x: Invalid image type. Only PNG, JPEG and GIF are supported."
            )
        except disnake.HTTPException as e:
            if e.code == 30008:
                return await ctx.send(
                    f":x: Maximum number of emojis reached ({ctx.guild.emoji_limit})"
                )
            else:
                return await ctx.send(f":x: {e.text}")
        except asyncio.TimeoutError:
            return await ctx.send(
                ":x: You're getting ratelimited by discord, retry again in 20/30 min"
            )

        await ctx.send(
            ":white_check_mark: Successfully added the emoji {}".format(
                format_emoji(emoji)
            )
        )

    async def _do_emote_remove(self, ctx, name):
        emotes = [x for x in ctx.guild.emojis if x.name == name]
        if len(emotes) == 0:
            return await ctx.send(":x: There is no emote with that name on this server.")
        nb_emote = len(emotes)
        deleted_emojis = ""
        for emote in emotes:
            deleted_emojis += f" {format_emoji(emote)}"

        await ctx.send(
            f":white_check_mark: {nb_emote} emote(s) with the name `:{name}:` have been deleted:"
            + deleted_emojis
        )
        for emote in emotes:
            await emote.delete()

    async def _do_emote_list(self, ctx):
        emotes = ctx.guild.emojis
        if len(emotes) == 0:
            return await ctx.send(":x: There are no emotes in this server")
        res = [""]
        i = 0
        for emote in emotes:
            emote_text = f"{format_emoji(emote)} `:{emote.name}:`\n"
            if len(res[i]) + len(emote_text) > 2000:
                i += 1
                res.append("")
            res[i] += emote_text

        # first chunk goes through the normal send (works for both prefix and
        # slash invocations), any additional chunks go through the channel to
        # avoid the single-interaction-response constraint
        await ctx.send(res[0])
        for msg in res[1:]:
            await ctx.channel.send(msg)

    async def _do_emote_number(self, ctx):
        nb_static, nb_anim = await number_emoji(ctx)
        await ctx.send(
            f"There are {nb_anim+nb_static} emojis in this server:\n\t- {nb_static} emojis\n\t- {nb_anim} animated emojis"
        )

    # --- prefix commands ---

    @commands.group(
        usage="[add|remove|list|number]",
        description="Manage the server custom emotes.",
        aliases=["emoji"],
        invoke_without_command=True,
    )
    async def emote(self, ctx, subcommand):
        return await ctx.send(
            f":x: Sub-command {subcommand} is not found\nUsage: `{get_display_prefix(self.bot)}{ctx.command.name} {ctx.command.usage}`"
        )

    @emote.command(
        usage="<name> <url|image>",
        description="""Add the image as a custom emoji.""",
        help="""\t- `<name>`: name of the emoji to add\n
                  \t- `<url|image>`: an image URL or an attached image""",
    )
    @commands.has_permissions(manage_emojis=True)
    async def add(self, ctx, name, url=None):
        await self._do_emote_add(ctx, name, url)

    @emote.command(
        usage="<name>",
        description="""Remove a custom emoji from the server.""",
        aliases=["delete", "rm"],
    )
    @commands.has_permissions(manage_emojis=True)
    async def remove(self, ctx, name):
        await self._do_emote_remove(ctx, name)

    @emote.command(
        description="Show all of the server custom emojis and their names.",
        aliases=["show"],
    )
    async def list(self, ctx):
        await self._do_emote_list(ctx)

    @emote.command(
        description="Give the number of emojis and animated emojis on the server",
        aliases=["nb"],
    )
    async def number(self, ctx):
        await self._do_emote_number(ctx)

    # --- slash commands ---

    @commands.slash_command(
        name="emote",
        default_member_permissions=disnake.Permissions(manage_emojis=True),
    )
    async def _emote(self, inter):
        pass

    @_emote.sub_command(name="add", description="Add the image as a custom emoji.")
    @commands.has_permissions(manage_emojis=True)
    async def _emote_add(self, inter, name: str, image: InterImage = None):
        await self._do_emote_add(inter, name, image.url if image else None)

    @_emote.sub_command(
        name="remove", description="Remove a custom emoji from the server."
    )
    @commands.has_permissions(manage_emojis=True)
    async def _emote_remove(self, inter, name: str):
        await self._do_emote_remove(inter, name)

    @_emote.sub_command(
        name="list",
        description="Show all of the server custom emojis and their names.",
    )
    async def _emote_list(self, inter):
        await inter.response.defer()
        await self._do_emote_list(inter)

    @_emote.sub_command(
        name="number",
        description="Give the number of emojis and animated emojis on the server.",
    )
    async def _emote_number(self, inter):
        await self._do_emote_number(inter)


def setup(bot: commands.Bot):
    bot.add_cog(Emote(bot))
