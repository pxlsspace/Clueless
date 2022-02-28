import os
import disnake
import re
import platform
import time
from datetime import datetime, timedelta, timezone
from disnake.ext import commands
from dotenv import load_dotenv

from utils.setup import BOT_INVITE, SERVER_INVITE, VERSION, db_servers, db_users
from utils.time_converter import str_to_td, td_format
from utils.timezoneslib import get_timezone
from utils.utils import ordinal
from utils.discord_utils import format_number, image_to_file
from utils.table_to_image import table_to_image


class Utility(commands.Cog):
    """Various utility commands"""

    def __init__(self, bot: commands.Bot):
        load_dotenv()
        self.bot: commands.Bot = bot

    @commands.slash_command(name="ping")
    async def _ping(self, inter: disnake.AppCmdInter):
        """pong! (show the bot latency)."""
        await self.ping(inter)

    @commands.command(description="pong! (show the bot latency)")
    async def ping(self, ctx):
        await ctx.send(f"pong! (bot latency: `{round(self.bot.latency*1000,2)}` ms)")

    @commands.slash_command(name="echo")
    async def _echo(self, inter: disnake.AppCmdInter, text: str):
        """Repeat your text.

        Parameters
        ----------
        text: The text to repeat."""

        await self.echo(inter, text=text)

    @commands.command(usage="<text>", description="Repeat your text.")
    async def echo(self, ctx, *, text):
        allowed_mentions = disnake.AllowedMentions(everyone=False)
        await ctx.send(text, allowed_mentions=allowed_mentions)

    @commands.command(usage="[prefix]", description="Change or display the bot prefix.")
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx, prefix=None):
        if prefix is None:
            prefix = ctx.prefix
            await ctx.send("Current prefix: `" + prefix + "`")
        else:
            await db_servers.update_prefix(prefix, ctx.guild.id)
            await ctx.send("✅ Prefix set to `" + prefix + "`")

    choices = ["years", "months", "weeks", "days", "hours", "minutes", "seconds"]

    @commands.slash_command(name="timeconvert")
    async def _timeconvert(
        self,
        inter: disnake.AppCmdInter,
        time: str,
        unit: str = commands.Param(choices=choices, default=None),
    ):
        """Convert time formats.

        Parameters
        ----------
        time: A time duration in the format ?y?mo?w?d?h?m?s
        unit: Convert the time to this unit."""
        if unit:
            await self.timeconvert(inter, time, "-" + unit)
        else:
            await self.timeconvert(inter, time)

    @commands.command(
        usage="<?y?mo?w?d?h?m?s> {-year|month|week|day|hour|minute|second}",
        description="Convert time formats.",
        aliases=["converttime", "tconvert", "tc"],
    )
    async def timeconvert(self, ctx, input, *options):
        try:
            time = str_to_td(input)
        except OverflowError:
            return await ctx.send("❌ The time given is too big.")
        if not time:
            return await ctx.send(
                "❌ Invalid `time` parameter, format must be `?y?mo?w?d?h?m?s`."
            )

        if len(options) > 0:
            options = [o.lower().strip("s") for o in options]
            if "-year" in options or "-y" in options:
                res_nb = time / timedelta(days=365)
                res_unit = "year"
            elif "-month" in options:
                res_nb = time / timedelta(days=30)
                res_unit = "month"
            elif "-week" in options or "-w" in options:
                res_nb = time / timedelta(weeks=1)
                res_unit = "week"
            elif "-day" in options or "-d" in options:
                res_nb = time / timedelta(days=1)
                res_unit = "day"
            elif "-hour" in options or "-h" in options:
                res_nb = time / timedelta(hours=1)
                res_unit = "hour"
            elif "-minute" in options or "-m" in options:
                res_nb = time / timedelta(minutes=1)
                res_unit = "minute"
            elif "-second" in options or "-s" in options:
                res_nb = time / timedelta(seconds=1)
                res_unit = "second"
            else:
                return await ctx.send(f"❌ unrecognized arguments: {' '.join(options)}")
            res = f"{format_number(res_nb)} {res_unit}{'s' if res_nb >= 2 else ''}"
        else:
            res = td_format(time)

        await ctx.send(f"{str_to_td(input,raw=True)} = {res}.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def rl(self, ctx, extension):
        try:
            self.bot.reload_extension("cogs." + extension)
        except Exception as e:
            return await ctx.send("```❌ {}: {} ```".format(type(e).__name__, e))

        await ctx.send(f"✅ Extension `{extension}` has been reloaded")

    @commands.slash_command(name="time")
    async def _time(self, inter: disnake.AppCmdInter, timezone: str = None):
        """Show the current time in a timezone.

        Parameters
        ----------
        timezone: A timezone name (ex: 'UTC+8', US/Pacific, PST)."""
        await self.time(inter, timezone)

    @commands.command(
        name="time",
        description="Show the current time in a timezone.",
        usage="<timezone>",
    )
    async def time(self, ctx, timezone: str = None):
        if timezone is None:
            discord_user = await db_users.get_discord_user(ctx.author.id)
            timezone = discord_user["timezone"] or "UTC"
        tz = get_timezone(timezone)
        if tz is None:
            return await ctx.send("❌ Timezone not found.")

        await ctx.send(
            "Current `{}` time: {}".format(
                timezone,
                datetime.astimezone(datetime.now(), tz).strftime(
                    "**%H:%M** (%Y-%m-%d)"
                ),
            )
        )

    @commands.group(hidden=True, usage="<sql expression>")
    @commands.is_owner()
    async def sql(self, ctx, *, sql_expression):
        async with ctx.typing():
            start = time.time()
            try:
                rows = await db_servers.db.sql_select(sql_expression)
            except Exception as e:
                return await ctx.send(f"❌ SQL error: ```{e}```")
        end = time.time()
        if len(rows) == 0:
            return await ctx.send("No match found.")
        elif len(rows) > 100:
            return await ctx.send(f"❌ Too many lines to show ({len(rows)})")

        titles = rows[0].keys()
        rows = [list(row) for row in rows]
        img = table_to_image(rows, titles)
        file = image_to_file(img, "table.png")
        content = f"Nb lines: {len(rows)}\nTime: {round(end-start,3)}s"
        await ctx.send(file=file, content=content)

    @commands.command(hidden=True, usage="<sql expression>")
    @commands.is_owner()
    async def sqlcommit(self, ctx, *, sql_expression):
        async with ctx.typing():
            try:
                nb_lines = await db_servers.db.sql_update(sql_expression)
            except Exception as e:
                return await ctx.send(f"❌ SQL error: ```{e}```")
        return await ctx.send(f"Done! ({nb_lines} lines affected)")

    # Populate the command usage database with logs sent in the log channel
    # (This is meant to be used only once)
    @commands.command(hidden=True, enabled=False)
    @commands.is_owner()
    async def log2db(self, ctx):
        log_channel_id = os.environ.get("COMMAND_LOG_CHANNEL")
        try:
            log_channel = await self.bot.fetch_channel(log_channel_id)
        except Exception:
            return await ctx.send(":x: log channel not set.")
        await ctx.send("parsing log messages ...")
        async with ctx.typing():
            count = 0
            async for log in log_channel.history(limit=None, oldest_first=True):
                count += 1

                # command name
                title = log.embeds[0].title
                command_name_match = re.findall("Command '(.*)' used.", title)
                if command_name_match:
                    command_name = command_name_match[0]
                else:
                    continue

                # context
                context = log.embeds[0].fields[0].value
                context_regex = r"(?P<DM>DM)|• \*\*Server\*\*\:(?P<server_name>.*) • \*\*Channel\*\*\: <#(?P<channel_id>\d*)>"
                context_match = re.search(context_regex, context).groupdict()
                dm = True if context_match["DM"] else False
                server_name = context_match["server_name"]
                channel_id = context_match["channel_id"]

                content = log.embeds[0].fields[1].value
                content = content.replace("\n", " ")  # remove new lines to make it easier for regex
                # author and date
                author_and_date_regex = r"By <@(?P<user_id>\d*)> on <t:(?P<timestamp>\d*)>"
                author_and_date_match = re.search(author_and_date_regex, content).groupdict()
                user_id = author_and_date_match["user_id"]
                timestamp = author_and_date_match["timestamp"]
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                dt = dt.replace(tzinfo=None)

                # message content
                message_regex = r"```(?P<command>.*)`\`\`"
                message_match = re.search(message_regex, content).groupdict()
                args = message_match["command"]
                is_slash = "/" == args[0]

                await db_servers.create_command_usage(
                    command_name,
                    dm,
                    server_name,
                    channel_id,
                    user_id,
                    dt,
                    args,
                    is_slash,
                )
            await ctx.send(
                ":white_check_mark: finished parsing {} messages from {}".format(
                    count, log_channel.mention
                )
            )

    @commands.slash_command(name="botinfo")
    async def _botinfo(self, inter: disnake.AppCmdInter):
        """Show some stats and information about the bot."""
        await self.botinfo(inter)

    @commands.command(description="Show some stats and information about the bot.")
    async def botinfo(self, ctx):
        app_info = await self.bot.application_info()
        owner = app_info.owner
        me = ctx.me
        bot_age = td_format(disnake.utils.utcnow() - me.created_at, hide_seconds=True)
        server_prefix = await db_servers.get_prefix(self.bot, ctx)
        # get some bot stats
        guild_count = len(self.bot.guilds)
        commands_count = len(self.bot.commands)
        slash_commands_count = len(self.bot.slash_commands)
        usage_count = await db_servers.db.sql_select(
            "SELECT COUNT(*) FROM command_usage"
        )
        usage_count = usage_count[0][0]
        user_count = await db_servers.db.sql_select(
            "SELECT COUNT(DISTINCT author_id) FROM command_usage"
        )
        user_count = user_count[0][0]
        prefix_usage = await db_servers.db.sql_select(
            "SELECT COUNT(*) FROM command_usage WHERE is_slash = FALSE"
        )
        prefix_usage_percentage = round((prefix_usage[0][0] / usage_count) * 100, 2)
        stats = f"• Currently in **{guild_count}** servers\n"
        stats += f"• Number of commands: **{commands_count}** prefix commands | **{slash_commands_count}** slash commands\n"
        stats += f"• Used **{format_number(usage_count)}** times by **{user_count}** different users\n"
        stats += (
            f"• **{prefix_usage_percentage}%** of the commands are used with a prefix"
        )

        # get the top 5 of the most used commands
        sql = """
            SELECT command_name, COUNT(command_name) as usage
            FROM command_usage
            GROUP BY command_name
            ORDER BY COUNT(command_name) DESC
            LIMIT 5
        """
        top_commands_array = await db_servers.db.sql_select(sql)
        top_commands = ""
        for i, command in enumerate(top_commands_array):
            command_name = command["command_name"]
            usage = format_number(command["usage"])
            top_commands += "{}) `>{}` | used **{}** times (**{}%**)\n".format(
                i + 1,
                command_name,
                usage,
                format_number((int(command["usage"]) / usage_count) * 100),
            )

        # get user info
        sql = """
            SELECT * FROM (
                SELECT
                    RANK() OVER(ORDER BY COUNT() DESC) as rank,
                    author_id,
                    COUNT() as usage
                FROM command_usage
                GROUP BY author_id
            ) WHERE author_id = ?
        """  # usage count and rank
        user_usage = await db_servers.db.sql_select(sql, ctx.author.id)
        if user_usage:
            user_usage_count = user_usage[0]["usage"]
            user_usage_rank = user_usage[0]["rank"]
            user_usage_rank = ordinal(user_usage_rank)
        else:
            user_usage_count = 0
            user_usage_rank = None

        sql = """
            SELECT command_name, COUNT(command_name) as usage
            FROM command_usage
            WHERE author_id = ?
            GROUP BY command_name
            ORDER BY COUNT(command_name) DESC
            LIMIT 1
        """  # most used command
        most_used_command = await db_servers.db.sql_select(sql, ctx.author.id)

        user_info = f"• You have used this bot **{user_usage_count}** times!\n"
        user_info += f"• Your user rank is: **{user_usage_rank}**"
        if most_used_command:
            user_info += "\n• Your most used command is `>{}` with **{}** uses, that's **{}%** of your total uses.".format(
                most_used_command[0]["command_name"],
                most_used_command[0]["usage"],
                format_number((int(most_used_command[0]["usage"]) / user_usage_count) * 100),
            )

        # format and send the data in an embed
        embed = disnake.Embed(title="Bot Information", color=0x66C5CC)
        embed.description = f"Creator: {owner}\n"
        embed.description += f"Bot version: `{VERSION}` - Ping: `{round(self.bot.latency*1000,2)} ms`\n"
        embed.description += f"Bot age: {bot_age}\n"
        embed.description += f"Server prefix: `{server_prefix}`"
        embed.add_field(name="**Bot Stats**", value=stats, inline=False)
        embed.add_field(
            name=f"**Top {len(top_commands_array)} Commands**",
            value=top_commands,
            inline=False,
        )
        embed.add_field(name=f"**Your stats** ({ctx.author})", value=user_info)

        embed.set_thumbnail(url=ctx.me.display_avatar)
        embed.set_author(name=me, icon_url=me.display_avatar)
        versions = "This bot runs on Python {} using disnake {} 🐍".format(
            platform.python_version(), disnake.__version__,
        )
        embed.set_footer(text=versions)

        class Invites(disnake.ui.View):
            def __init__(self, bot_invite, server_invite):
                super().__init__()
                self.add_item(disnake.ui.Button(label="Add the bot to your server", url=bot_invite))
                self.add_item(disnake.ui.Button(label="Join the Clueless dev server", url=server_invite))
        invites = Invites(BOT_INVITE, SERVER_INVITE)
        await ctx.send(embed=embed, view=invites)


def setup(bot: commands.Bot):
    bot.add_cog(Utility(bot))
