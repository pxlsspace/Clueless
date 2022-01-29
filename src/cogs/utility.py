import os
import discord
import re
import platform
import discord_slash
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from dotenv import load_dotenv
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from discord_slash.utils.manage_components import create_button, create_actionrow
from discord_slash.model import ButtonStyle

from utils.setup import BOT_INVITE, SERVER_INVITE, db_servers, GUILD_IDS, VERSION
from utils.time_converter import str_to_td, td_format
from utils.timezoneslib import get_timezone
from utils.utils import get_content, ordinal
from utils.discord_utils import format_number, image_to_file
from utils.help import fullname
from utils.table_to_image import table_to_image


class Utility(commands.Cog):
    """Various utility commands"""

    def __init__(self, client):
        load_dotenv()
        self.client = client

    @cog_ext.cog_slash(
        name="ping", description="pong! (show the bot latency).", guild_ids=GUILD_IDS
    )
    async def _ping(self, ctx: SlashContext):
        await self.ping(ctx)

    @commands.command(description="pong! (show the bot latency)")
    async def ping(self, ctx):
        await ctx.send(f"pong! (bot latency: `{round(self.client.latency*1000,2)}` ms)")

    @cog_ext.cog_slash(
        name="echo",
        description="Repeat your text.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="text",
                description="The text to repeat.",
                option_type=3,
                required=True,
            )
        ],
    )
    async def _echo(self, ctx: SlashContext, text: str):
        await self.echo(ctx, text=text)

    @commands.command(usage="<text>", description="Repeat your text.")
    async def echo(self, ctx, *, text):
        allowed_mentions = discord.AllowedMentions(everyone=False)
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

    @commands.command(
        hidden=True,
        usage="<amount> <currency>",
        description="Convert currency between Euro and SA Rand.",
        help="""- `<amount>`: a number to convert
                  - `<currency>`: either: 'euros', 'euro', 'EUR', '€', 'e' or 'rand', 'ZAR', 'R' (not case-sensitive)""",
    )
    async def convert(self, ctx, amount, currency):
        try:
            amount = float(amount)
        except ValueError:
            return await ctx.send("❌ `amount` parameter must be a number.")
        apikey = os.environ.get("CURRCONV_API_KEY")
        url = f"https://free.currconv.com/api/v7/convert?q=EUR_ZAR,ZAR_EUR&compact=ultra&apiKey={apikey}"
        json_response = await get_content(url, "json")
        EUR_ZAR = json_response["EUR_ZAR"]
        ZAR_EUR = json_response["ZAR_EUR"]

        test_list_eur = ["euros", "euro", "eu", "eur", "€", "e"]
        test_list_zar = ["rand", "zar", "r"]

        if currency.lower() in test_list_eur:
            return await ctx.send(f"{amount}€ = {round(amount*EUR_ZAR,2)} rand")
        elif currency.lower() in test_list_zar:
            return await ctx.send(f"{amount} rand = {round(amount*ZAR_EUR,2)}€")
        else:
            return await ctx.send("❌ Invalid `currency` parameter.")

    choices = ["years", "months", "weeks", "days", "hours", "minutes", "seconds"]

    @cog_ext.cog_slash(
        name="timeconvert",
        description="Convert time formats.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="time",
                description="A time duration in the format ?y?mo?w?d?h?m?s",
                option_type=3,
                required=True,
            ),
            create_option(
                name="unit",
                description="Convert the time to this unit.",
                option_type=3,
                required=False,
                choices=[create_choice(name=c, value=c) for c in choices],
            ),
        ],
    )
    async def _timeconvert(self, ctx: SlashContext, time, unit=None):
        if unit:
            await self.timeconvert(ctx, time, "-" + unit)
        else:
            await self.timeconvert(ctx, time)

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

    @cog_ext.cog_slash(
        name="rl",
        description="Reload a bot extension (owner only).",
        guild_ids=[389486136763875340],
        options=[
            create_option(
                name="extension",
                description="The extension to reload.",
                option_type=3,
                required=True,
            )
        ],
    )
    async def _rl(self, ctx: SlashContext, extension):
        appinfo = await self.client.application_info()
        if ctx.author != appinfo.owner:
            raise commands.NotOwner()

        await self.rl(ctx, extension)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def rl(self, ctx, extension):
        try:
            self.client.reload_extension("cogs." + extension)
        except Exception as e:
            return await ctx.send("```❌ {}: {} ```".format(type(e).__name__, e))

        await ctx.send(f"✅ Extension `{extension}` has been reloaded")

    @cog_ext.cog_slash(
        name="help",
        description="Show all the slash commands and their description.",
        guild_ids=GUILD_IDS,
    )
    async def _help(self, ctx: SlashContext):
        categories = {}
        for command in self.client.slash.commands.values():
            if command and command.name != "rl":
                cog_fullname = fullname(command.cog)
                cog_fullname = cog_fullname.split(".")
                cog_dir = cog_fullname[1:-2]
                cog_dir = cog_dir[0].capitalize() if len(cog_dir) > 0 else "Other"

                text = f"• `/{command.name}`: {command.description}"

                # categories are organized by cog folders
                try:
                    categories[cog_dir].append(text)
                except KeyError:
                    categories[cog_dir] = [text]

        embed = discord.Embed(title="Command help", color=0x66C5CC)
        embed.set_thumbnail(url=ctx.me.avatar_url)

        for category in categories:
            if category != "Other":
                embed.add_field(
                    name=f"**{category}**",
                    value="\n".join(categories[category]),
                    inline=False,
                )
        if "Other" in categories:
            embed.add_field(
                name="**Other**", value="\n".join(categories["Other"]), inline=False
            )

        await ctx.send(embed=embed)

    @cog_ext.cog_slash(
        name="time",
        description="Show the current time in a timezone.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="timezone",
                description="A timezone name (ex: 'UTC+8', US/Pacific, PST).",
                option_type=3,
                required=True,
            )
        ],
    )
    async def _time(self, ctx, timezone):
        await self.time(ctx, timezone)

    @commands.command(
        name="time",
        description="Show the current time in a timezone.",
        usage="<timezone>",
    )
    async def time(self, ctx, timezone: str):
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
            try:
                rows = await db_servers.db.sql_select(sql_expression)
            except Exception as e:
                return await ctx.send(f"❌ SQL error: ```{e}```")
        if len(rows) == 0:
            return await ctx.send("No match found.")
        elif len(rows) > 100:
            return await ctx.send(f"❌ Too many lines to show ({len(rows)})")

        titles = rows[0].keys()
        rows = [list(row) for row in rows]
        img = table_to_image(rows, titles)
        file = image_to_file(img, "table.png")
        await ctx.send(file=file)

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
    @commands.command(hidden=True)
    @commands.is_owner()
    async def log2db(self, ctx):
        log_channel_id = os.environ.get("COMMAND_LOG_CHANNEL")
        try:
            log_channel = await self.client.fetch_channel(log_channel_id)
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

    @cog_ext.cog_slash(
        name="botinfo",
        description="Show some stats and information about the bot.",
        guild_ids=GUILD_IDS,
    )
    async def _botinfo(self, ctx: SlashContext):
        await self.botinfo(ctx)

    @commands.command(description="Show some stats and information about the bot.")
    async def botinfo(self, ctx):
        app_info = await self.client.application_info()
        owner = app_info.owner
        me = ctx.me
        bot_age = td_format(datetime.now() - me.created_at, hide_seconds=True)

        # get some bot stats
        guild_count = len(self.client.guilds)
        command_count = len(self.client.commands)
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
        stats += f"• **{command_count}** commands available\n"
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
            top_commands += f"{i+1}) `>{command_name}` | used **{usage}** times\n"

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
            user_info += "\n• Your most used command is `>{}` with **{}** use".format(
                most_used_command[0]["command_name"], most_used_command[0]["usage"]
            )

        # format and send the data in an embed
        embed = discord.Embed(title="Bot Information", color=0x66C5CC)
        embed.description = f"Creator: {owner}\n"
        embed.description += f"Bot version: `{VERSION}` - Ping: `{round(self.client.latency*1000,2)} ms`\n"
        embed.description += f"Bot age: {bot_age}"
        embed.add_field(name="**Bot Stats**", value=stats, inline=False)
        embed.add_field(
            name=f"**Top {len(top_commands_array)} Commands**",
            value=top_commands,
            inline=False,
        )
        embed.add_field(name=f"**Your stats** ({ctx.author})", value=user_info)

        embed.set_thumbnail(url=ctx.me.avatar_url)
        embed.set_author(name=me, icon_url=me.avatar_url)
        versions = "This bot runs on Python {} using discord.py {} and discord-interactions {}".format(
            platform.python_version(), discord.__version__, discord_slash.__version__
        )
        embed.set_footer(text=versions)

        buttons = [
            create_button(
                style=ButtonStyle.URL,
                label="Add the bot to your server",
                url=BOT_INVITE,
            ),
            create_button(
                style=ButtonStyle.URL,
                label="Join the Clueless dev server",
                url=SERVER_INVITE,
            ),
        ]
        action_row = create_actionrow(*buttons)
        await ctx.send(embed=embed, components=[action_row])


def setup(client):
    client.add_cog(Utility(client))
