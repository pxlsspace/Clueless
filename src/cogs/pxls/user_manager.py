import sqlite3
import disnake
import asyncio
from disnake.ext import commands
from datetime import datetime

from utils.discord_utils import STATUS_EMOJIS, UserConverter, autocomplete_pxls_name
from utils.font.font_manager import DEFAULT_FONT, get_all_fonts, get_allowed_fonts
from utils.image.image_utils import hex_str_to_int
from utils.pxls.archives import check_key
from utils.setup import db_users, db_canvas
from utils.plot_utils import get_theme, theme_list
from utils.time_converter import format_timezone
from utils.timezoneslib import get_timezone


class UserManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="user")
    async def user(self, inter):
        """Manage your user settings."""
        pass

    @user.sub_command(name="setname")
    async def _setname(
        self,
        inter: disnake.AppCmdInter,
        username: str = commands.Param(autocomplete=autocomplete_pxls_name),
    ):
        """Link your discord account to a pxls username.

        Parameters
        ----------
        username: A pxls username."""
        await self.setname(inter, username)

    @commands.command(
        description="Link your discord account to a pxls username.",
        usage="<pxls username>",
    )
    async def setname(self, ctx, username):
        pxls_user_id = await db_users.get_pxls_user_id(username)
        if pxls_user_id is None:
            return await ctx.send("❌ Can't find this pxls username.")
        await db_users.set_pxls_user(ctx.author.id, pxls_user_id)
        await ctx.send(f"✅ Pxls username successfully set to **{username}**.")

    @user.sub_command(name="unsetname")
    async def _unsetname(self, inter: disnake.AppCmdInter):
        """Unlink your discord account from a pxls username."""
        await self.unsetname(inter)

    @commands.command(description="Unlink your discord account from a pxls username.")
    async def unsetname(self, ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["pxls_user_id"] is None:
            return await ctx.send("❌ You haven't set any pxls username.")
        await db_users.set_pxls_user(ctx.author.id, None)
        await ctx.send("✅ Pxls username successfully unset.")

    @user.sub_command(name="settheme")
    async def _theme(
        self,
        inter: disnake.AppCmdInter,
        theme: str = commands.Param(choices=[t.name for t in theme_list]),
    ):
        """Set your theme for the graphs.

        Parameters
        ----------
        theme: The name of the theme."""
        await self.theme(inter, theme)

    @user.sub_command(name="themes")
    async def _themes(self, inter: disnake.AppCmdInter):
        """Show the list of themes."""
        await self.theme(inter)

    @commands.command(
        description="Set your theme for the graphs",
        usage="[theme name]",
        aliases=["themes"],
    )
    async def theme(self, ctx, theme=None):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"

        available_themes_text = "**Available themes:**\n"
        for t in theme_list:

            available_themes_text += "{1} `{0.name}`: {0.description}\n".format(
                t, "✓" if t.name == current_user_theme else "☐"
            )

        if theme is None:
            if isinstance(ctx, commands.Context):
                set_theme_text = (
                    f"\n*Use `{ctx.prefix }theme <theme name>` to change your theme.*"
                )
            else:
                set_theme_text = (
                    "\n*Use `/user settheme <theme name>` to change your theme.*"
                )
            embed = disnake.Embed(
                title="Available Themes",
                color=0x66C5CC,
                description=available_themes_text + set_theme_text,
            )
            return await ctx.send(embed=embed)

        if theme not in [t.name for t in theme_list]:
            error_msg = "❌ Can't find this theme.\n"
            return await ctx.send(error_msg + available_themes_text)

        await db_users.set_user_theme(ctx.author.id, theme)
        await ctx.send(f"✅ Theme successfully set to **{theme}**.")

    @commands.slash_command(name="whoami")
    async def _whoami(self, inter: disnake.AppCmdInter):
        """Show your linked pxls username, theme and timezone."""
        await self.whoami(inter)

    @commands.slash_command(name="whois")
    async def _whois(self, inter: disnake.AppCmdInter, user: disnake.User):
        """Show someone's linked pxls username, theme and timezone.

        Parameters
        ----------
        user: A discord user."""
        if not isinstance(user, (disnake.member.Member, disnake.user.User)):
            # the ID is passed if fetching the user object failed
            # so we fetch the user object from the ID "manually"
            user = await self.bot.fetch_user(user)
        await self.whoami(inter, user)

    @commands.command(
        name="whoami",
        usage="[discord name]",
        aliases=["whois"],
        description="Show your or anyone's linked pxls username, theme and timezone.",
    )
    async def p_whoami(self, ctx, user=None):
        if user:
            # check that the user exists
            try:
                user = await UserConverter().convert(ctx, user)
            except commands.UserNotFound as e:
                return await ctx.send(f"❌ {e}")
        await self.whoami(ctx, user)

    async def whoami(self, ctx, user=None):
        if user:
            title = f"🤔 Who is {user.name}?"
        else:
            user = ctx.author
            title = "🤔 Who am I?"

        discord_user = await db_users.get_discord_user(user.id)
        is_slash = not isinstance(ctx, commands.Context)
        prefix = "/" if is_slash else ctx.prefix
        # get the pxls username
        if discord_user["pxls_user_id"] is None:
            cmd_name = "user setname" if is_slash else "setname"
            pxls_username = f"*Not set\n(use `{prefix}{cmd_name} <pxls username>`)*"
        else:
            pxls_username = await db_users.get_pxls_user_name(
                discord_user["pxls_user_id"]
            )

        # get the user theme
        user_theme = discord_user["color"] or "default"

        # get the font
        user_font = discord_user["font"] or f"{DEFAULT_FONT} (default)"

        # get the timezone
        tz_str = discord_user["timezone"]
        if tz_str is None:
            cmd_name = "user settimezone" if is_slash else "settimezone"
            tz_str = f"*Not set\n(use `{prefix}{cmd_name} <timezone>`)*"
            current_time = None
        else:
            tz = get_timezone(tz_str)
            current_time = datetime.astimezone(datetime.now(), tz).strftime(
                "%H:%M %Z (%Y-%m-%d)"
            )
            tz_str = format_timezone(tz)

        color = get_theme(user_theme).get_palette(1)[0]
        color = hex_str_to_int(color)
        text = f"• **Discord name:** {user}\n"
        text += f"• **Graph theme:** {user_theme}\n"
        text += f"• **Font**: {user_font}\n"
        text += f"• **Pxls username:** {pxls_username}\n"
        text += f"• **Timezone:** {tz_str}\n"
        if current_time:
            text += f"• **Current time:** {current_time}"
        embed = disnake.Embed(title=title, description=text, color=color)
        embed.set_thumbnail(url=user.display_avatar)
        await ctx.send(embed=embed)

    @user.sub_command(name="settimezone")
    async def _settimezone(self, inter: disnake.AppCmdInter, timezone: str):
        """Set your timezone for the graphs and time inputs.

        Parameters
        ----------
        timezone: Your timezone name (ex: 'UTC+8', US/Pacific, PST)."""
        await self.settimezone(inter, timezone)

    @commands.command(
        name="settimezone",
        description="Set your timezone for the graphs and time inputs.",
        aliases=["settz", "timezone"],
        usage="<timezone>",
        help="- `<timezone>`: your timezone name (ex: 'UTC+8', US/Pacific, PST)",
    )
    async def settimezone(self, ctx, timezone: str):
        tz = get_timezone(timezone)
        if tz is None:
            return await ctx.send("❌ Timezone not found.")
        await db_users.set_user_timezone(ctx.author.id, timezone)
        await ctx.send(
            "✅ Timezone successfully set to `{}`.\nCurrent time: {}".format(
                timezone,
                datetime.astimezone(datetime.now(), tz).strftime(
                    "**%H:%M** %Z (%Y-%m-%d)"
                ),
            )
        )

    @user.sub_command(name="unsettimezone")
    async def _unsettimezone(self, inter: disnake.AppCmdInter):
        """Unset your timezone."""
        await self.unsettimezone(inter)

    @commands.command(description="Unset your timezone.", aliases=["unsettz"])
    async def unsettimezone(self, ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["timezone"] is None:
            return await ctx.send("❌ You haven't set any timezone.")
        await db_users.set_user_timezone(ctx.author.id, None)
        await ctx.send("✅ Timezone successfully unset.")

    allowed_fonts = get_allowed_fonts()

    @user.sub_command(name="setfont")
    async def _setfont(
        self,
        inter: disnake.AppCmdInter,
        font: str = commands.Param(choices=allowed_fonts),
    ):
        """Set your font for the image tables.

        Parameters
        ----------
        font: The font name."""
        await self.setfont(inter, font)

    @commands.command(
        name="setfont",
        description="Set your font for the image tables.",
        aliases=["font"],
        usage="<font name>",
        help="- `<font name>`: The name of the font",
    )
    async def setfont(self, ctx, font: str):
        # check on the font
        if font.lower() not in self.allowed_fonts:
            allowed_fonts = "Allowed Fonts:\n"
            allowed_fonts += " ".join([f"`{f}`" for f in self.allowed_fonts])
            if font.lower() in get_all_fonts():
                return await ctx.send(f":x: This font is not allowed.\n{allowed_fonts}")
            else:
                return await ctx.send(f":x: Font not found.\n{allowed_fonts}")

        await db_users.set_user_font(ctx.author.id, font.lower())
        await ctx.send(f"✅ Font successfully set to `{font.lower()}`.")

    @user.sub_command(name="setkey")
    async def _set_key(self, inter: disnake.AppCmdInter):
        """Set your log keys to get past canvases stats."""
        await self.set_key(inter)

    @commands.command(
        name="setkey", description="Set your log keys to get past canvases stats."
    )
    async def p_set_key(self, ctx):
        await self.set_key(ctx)

    async def set_key(self, inter: disnake.AppCmdInter):
        info_embed = disnake.Embed(
            title="Set your log keys",
            color=0x66C5CC,
            description="Set your log keys to access your stats on past canvases.",
        )
        instructions = """
        1. Go to https://pxls.space/profile?action=data
        2. Copy a log key (512 characters)
        3. Click the `[Add Key]` button
        4. Enter the canvas code and paste the log key
        *(Repeat for every key)*"""
        info_embed.add_field(name="How does this work?", value=instructions)

        info_embed.set_footer(
            text="Note: your log keys will stay private, only you and the bot maintainer will have access to them."
        )

        class AddKeyView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(
                    disnake.ui.Button(
                        label="Add Key",
                        style=disnake.ButtonStyle.blurple,
                        custom_id="add_key",
                    )
                )
                self.add_item(
                    disnake.ui.Button(
                        label="List Keys",
                        style=disnake.ButtonStyle.gray,
                        custom_id="list_keys",
                    )
                )

        await inter.send(embed=info_embed, view=AddKeyView())

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        """Handle what to do when the "add key" or "list keys" button is pressed."""
        custom_id = inter.component.custom_id
        if custom_id not in ["add_key", "list_keys"]:
            return

        if custom_id == "list_keys":
            return await self.keys(inter)
        else:
            await inter.response.send_modal(
                title="Add a log key",
                custom_id="add_log_key",
                components=[
                    disnake.ui.TextInput(
                        label="Canvas Code",
                        placeholder="The canvas code for the key (e.g. '45' or '45a')",
                        custom_id="canvas_code",
                        style=disnake.TextInputStyle.short,
                        min_length=1,
                        max_length=10,
                    ),
                    disnake.ui.TextInput(
                        label="Log Key",
                        placeholder="Your log key for the canvas.",
                        custom_id="log_key",
                        style=disnake.TextInputStyle.paragraph,
                    ),
                ],
            )

            # Wait until the user submits the modal.
            try:
                modal_inter: disnake.ModalInteraction = await self.bot.wait_for(
                    "modal_submit",
                    check=lambda i: i.custom_id == "add_log_key"
                    and i.author.id == inter.author.id,
                    timeout=300,
                )
            except asyncio.TimeoutError:
                return

            canvas_code = modal_inter.text_values["canvas_code"]
            log_key = modal_inter.text_values["log_key"]

            error_embed = disnake.Embed(title="Error", color=disnake.Color.red())
            # check on the canvas code
            canvas = await db_canvas.get_canvas(canvas_code)
            if canvas is None or not canvas["has_logs"]:
                error_embed.description = (
                    ":x: This canvas code is invalid or doesn't have logs yet."
                )

                return await modal_inter.response.send_message(
                    embed=error_embed, ephemeral=True
                )
            # check on the key
            try:
                log_key = check_key(log_key)
            except ValueError as e:
                error_embed.description = f":x: {e}"
                return await modal_inter.response.send_message(
                    embed=error_embed, ephemeral=True
                )

            # add to the db or update
            is_update = False
            try:
                await db_users.create_log_key(modal_inter.author.id, canvas_code, log_key)
            except sqlite3.IntegrityError:
                await db_users.update_key(modal_inter.author.id, canvas_code, log_key)
                is_update = True

            embed = disnake.Embed(
                color=disnake.Color.green(),
                description=f"✅ Log key for canvas `{canvas_code}` successfully {'updated' if is_update else 'added'}.",
            )
            embed.set_author(
                name=modal_inter.author, icon_url=modal_inter.author.display_avatar
            )
            await modal_inter.response.send_message(embed=embed, ephemeral=True)

    @user.sub_command(name="keys")
    async def _keys(self, inter):
        """Check the status of your log keys."""
        await self.keys(inter)

    @commands.command(name="keys", description="Check the status of your log keys.")
    async def p_keys(self, ctx):
        await self.keys(ctx)

    async def keys(self, ctx):
        canvases_with_logs = await db_canvas.get_logs_canvases()
        res = []
        for canvas_code in canvases_with_logs[::-1]:
            key = await db_users.get_key(ctx.author.id, canvas_code)
            if key:
                status = "online"
            else:
                status = "offline"
            res.append(f"{STATUS_EMOJIS.get(status)} `c{canvas_code}`")

        embed = disnake.Embed(color=0x66C5CC)
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        res = [res[i::3] for i in range(3)]

        for i, group in enumerate(res):
            if i == 0:
                title = "**Log Keys**"
            else:
                title = "\u200b"
            embed.add_field(name=title, value="\n".join(group))
        embed.add_field(
            name="Key Status",
            value=f"{STATUS_EMOJIS['online']} = `key added` {STATUS_EMOJIS['offline']} = `key not added`",
            inline=False,
        )
        if isinstance(ctx, commands.Context):
            return await ctx.send(embed=embed)
        else:
            return await ctx.send(embed=embed, ephemeral=True)

    @user.sub_command(name="unsetkey")
    async def _unsetkey(
        self, inter, canvas_code: str = commands.Param(name="canvas-code")
    ):
        """Delete your key from the bot.

        Parameters
        ----------
        canvas_code: The canvas code of the key you wish to delete"""
        await self.unsetkey(inter, canvas_code)

    @commands.command(name="unsetkey", description="Delete your key from the bot.")
    async def p_unsetkey(self, ctx, canvas_code):
        await self.unsetkey(ctx, canvas_code)

    async def unsetkey(self, ctx, canvas_code):
        key = await db_users.get_key(ctx.author.id, canvas_code)
        if key is None:
            return await ctx.send(":x: You haven't set a key for this canvas.")
        else:
            await db_users.delete_key(ctx.author.id, canvas_code)
        return await ctx.send(
            f"✅ Log key for canvas `{canvas_code}` successfully deleted."
        )


def setup(bot: commands.Bot):
    bot.add_cog(UserManager(bot))
