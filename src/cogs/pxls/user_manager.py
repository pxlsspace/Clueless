import disnake
from disnake.ext import commands
from datetime import datetime

from utils.discord_utils import UserConverter, autocomplete_pxls_name
from utils.font.font_manager import DEFAULT_FONT, get_all_fonts, get_allowed_fonts
from utils.image.image_utils import hex_str_to_int
from utils.setup import db_users
from utils.plot_utils import get_theme, theme_list
from utils.time_converter import format_timezone
from utils.timezoneslib import get_timezone


class UserManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="setname")
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

    @commands.slash_command(name="unsetname")
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

    @commands.slash_command(name="theme")
    async def _theme(
        self,
        inter: disnake.AppCmdInter,
        theme: str = commands.Param(default=None, choices=[t.name for t in theme_list]),
    ):
        """Set your theme for the graphs."""
        await self.theme(inter, theme)

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
            set_theme_text = "*Use `{0}theme [theme name]` to change your theme.*".format(
                ctx.prefix if isinstance(ctx, commands.Context) else "/"
            )
            return await ctx.send(available_themes_text + set_theme_text)

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
        """Show someone's linked pxls username, theme and timezone."

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
        prefix = ctx.prefix if isinstance(ctx, commands.Context) else "/"
        # get the pxls username
        if discord_user["pxls_user_id"] is None:
            pxls_username = f"*Not set\n(use `{prefix}setname <pxls username>`)*"
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
            tz_str = f"*Not set\n(use `{prefix}settimezone <timezone>`)*"
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

    @commands.slash_command(name="settimezone")
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

    @commands.slash_command(name="unsettimezone")
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

    @commands.slash_command(name="setfont")
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


def setup(bot: commands.Bot):
    bot.add_cog(UserManager(bot))
