import discord
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from datetime import datetime

from utils.discord_utils import UserConverter
from utils.image.image_utils import hex_str_to_int
from utils.setup import db_users, GUILD_IDS
from utils.plot_utils import get_theme, theme_list
from utils.time_converter import format_timezone
from utils.timezoneslib import get_timezone

class UserManager(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @cog_ext.cog_slash(
        name="setname",
        description="Link your discord account to a pxls username.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="username",
            description="A pxls username.",
            option_type=3,
            required=True
        )]
    )
    async def _setname(self,ctx:SlashContext, username: str):
        await self.setname(ctx,username)

    @commands.command(description = "Link your discord account to a pxls username.",usage="<pxls username>")
    async def setname(self,ctx,username):
        pxls_user_id = await db_users.get_pxls_user_id(username)
        if pxls_user_id == None:
            return await ctx.send("❌ Can't find this pxls username.")
        await db_users.set_pxls_user(ctx.author.id,pxls_user_id)
        await ctx.send(f"✅ Pxls username successfully set to **{username}**.")

    @cog_ext.cog_slash(
        name="unsetname",
        description="Unlink your discord account from a pxls username.",
        guild_ids=GUILD_IDS)
    async def _unsetname(self,ctx:SlashContext):
        await self.unsetname(ctx)

    @commands.command(description = "Unlink your discord account from a pxls username.")
    async def unsetname(self,ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["pxls_user_id"] == None:
            return await ctx.send("❌ You haven't set any pxls username.")
        await db_users.set_pxls_user(ctx.author.id,None)
        await ctx.send("✅ Pxls username successfully unset.")

    @cog_ext.cog_slash(name="theme",
        description="Set your theme for the graphs.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="theme",
            description="Theme",
            option_type=3,
            required=False,
            choices=[create_choice(t.name,t.name) for t in theme_list]
        )]
    )
    async def _theme(self,ctx:SlashContext, theme=None):
        await self.theme(ctx,theme)

    @commands.command(description = "Set your theme for the graphs",
        usage="[theme name]",aliases=["themes"])
    async def theme(self,ctx,theme=None):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"

        available_themes_text = "**Available themes:**\n"
        for t in theme_list:

            available_themes_text+= "{1} `{0.name}`: {0.description}\n"\
                .format(t,"✓" if t.name == current_user_theme else "☐")

        if theme == None:
            set_theme_text = "*Use `{0}theme [theme name]` to change your theme.*"\
                .format(ctx.prefix if isinstance(ctx,commands.Context) else '/')
            return await ctx.send(available_themes_text + set_theme_text)

        if not theme in [t.name for t in theme_list]:
            error_msg = "❌ Can't find this theme.\n"
            return await ctx.send(error_msg + available_themes_text)

        await db_users.set_user_theme(ctx.author.id,theme)
        await ctx.send(f"✅ Theme successfully set to **{theme}**.")

    @cog_ext.cog_slash(
        name="whoami",
        description="Show your linked pxls username and theme.",
        guild_ids=GUILD_IDS)
    async def _whoami(self,ctx:SlashContext):
        await self.whoami(ctx)

    @cog_ext.cog_slash(
        name="whois",
        description="Show someone's linked pxls username and theme.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="user",
            description="A discord user.",
            option_type=6,
            required=True
        )]
    )
    async def _whois(self,ctx:SlashContext, user):
        if not isinstance(user,(discord.member.Member, discord.user.User)):
            # the ID is passed if fetching the user object failed
            # so we fetch the user object from the ID "manually"
            user = await self.client.fetch_user(user)
        await self.whoami(ctx,user)

    @commands.command(
        name="whoami",
        usage = "[discord name]",
        aliases = ["whois"],
        description="Show your or anyone's linked pxls username and theme.")
    async def p_whoami(self,ctx,user=None):
        if user:
            # check that the user exists
            try:
                user = await UserConverter().convert(ctx,user)
            except commands.UserNotFound as e:
                return await ctx.send(f"❌ {e}")
        await self.whoami(ctx,user)


    async def whoami(self,ctx,user=None):
        if user:
            title = f"🤔 Who is {user.name}?"
        else:
            user = ctx.author
            title = "🤔 Who am I?"
            
        discord_user = await db_users.get_discord_user(user.id)

        # get the pxls username
        if discord_user["pxls_user_id"] == None:
            pxls_username = "*Not set\n(use `{}setname <pxls username>`)*".format(
                ctx.prefix if isinstance(ctx,commands.Context) else '/'
            )
        else:
            pxls_username = await db_users.get_pxls_user_name(discord_user["pxls_user_id"])
        
        # get the user theme
        user_theme = discord_user["color"] or "default"

        #get the timezone
        tz_str = discord_user["timezone"]
        if tz_str == None:
            tz_str = "*Not set\n(use `{}settimezone <timezone>`)*".format(
                ctx.prefix if isinstance(ctx,commands.Context) else '/')
            current_time = None
        else:
            tz = get_timezone(tz_str)
            current_time = datetime.astimezone(datetime.now(),tz).strftime("%H:%M %Z (%Y-%m-%d)")
            tz_str = format_timezone(tz)

        color = get_theme(user_theme).get_palette(1)[0]
        color = hex_str_to_int(color)
        text = f"• **Discord name:** {user}\n"
        text += f"• **Graph theme:** {user_theme}\n"
        text += f"• **Pxls username:** {pxls_username}\n"
        text += f"• **Timezone:** {tz_str}\n"
        if current_time:
            text += f"• **Current time:** {current_time}"
        embed = discord.Embed(title=title,description=text,color=color)
        embed.set_thumbnail(url=user.avatar_url)
        await ctx.send(embed=embed)

    @cog_ext.cog_slash(
        name="settimezone",
        description="Set your timezone for the graphs and time inputs.",
        guild_ids=GUILD_IDS,
        options=[create_option(
            name="timezone",
            description="Your timezone name (ex: 'UTC+8', US/Pacific, PST).",
            option_type=3,
            required=True
        )]
    )
    async def _settimezone(self,ctx,timezone):
        await self.settimezone(ctx,timezone)

    @commands.command(
        name="settimezone",
        description = "Set your timezone for the graphs and time inputs.",
        aliases = ["settz","timezone"],
        usage = "<timezone>",
        help="- `<timezone>`: your timezone name (ex: 'UTC+8', US/Pacific, PST)")
    async def settimezone(self, ctx, timezone:str):
        tz = get_timezone(timezone)
        if tz == None:
            return await ctx.send("❌ Timezone not found.")
        await db_users.set_user_timezone(ctx.author.id,timezone)
        await ctx.send("✅ Timezone successfully set to `{}`.\nCurrent time: {}".format(
            timezone,
            datetime.astimezone(datetime.now(),tz).strftime("**%H:%M** %Z (%Y-%m-%d)")
        ))

    @cog_ext.cog_slash(
        name="unsettimezone",
        description="Unset your timezone.",
        guild_ids=GUILD_IDS)
    async def _unsettimezone(self,ctx:SlashContext):
        await self.unsettimezone(ctx)

    @commands.command(description = "Unset your timezone.",aliases=["unsettz"])
    async def unsettimezone(self,ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["timezone"] == None:
            return await ctx.send("❌ You haven't set any timezone.")
        await db_users.set_user_timezone(ctx.author.id,None)
        await ctx.send("✅ Timezone successfully unset.")

def setup(client):
    client.add_cog(UserManager(client))