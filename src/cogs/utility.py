import os
import discord
from datetime import timedelta
from discord.ext import commands
from dotenv import load_dotenv
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from datetime import datetime

from utils.setup import db_servers, GUILD_IDS
from utils.time_converter import str_to_td, td_format
from utils.timezoneslib import get_timezone
from utils.utils import get_content
from utils.discord_utils import format_number
from utils.help import fullname

class Utility(commands.Cog):
    ''' Various utility commands'''

    def __init__(self, client):
        load_dotenv()
        self.client = client

    @cog_ext.cog_slash(name="ping",description="pong! (show the bot latency).",
        guild_ids=GUILD_IDS)
    async def _ping(self,ctx:SlashContext):
        await self.ping(ctx)

    @commands.command(description="pong! (show the bot latency)")
    async def ping(self,ctx):
        await ctx.send(f"pong! (bot latency: `{round(self.client.latency*1000,2)}` ms)")

    @cog_ext.cog_slash(name="echo",
        description="Repeat your text.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="text",
            description="The text to repeat.",
            option_type=3,
            required=True
        )]
    )
    async def _echo(self,ctx:SlashContext, text: str):
        await self.echo(ctx,text=text)

    @commands.command(
        usage = "<text>",
        description = "Repeat your text."
    )
    async def echo(self,ctx,*,text):
        allowed_mentions = discord.AllowedMentions(everyone=False) 
        await ctx.send(text, allowed_mentions=allowed_mentions)

    @commands.command(
        usage = "[prefix]",
        description = "Change or display the bot prefix."
    )
    @commands.has_permissions(administrator=True)
    async def prefix(self,ctx,prefix=None):
        if prefix == None:
            prefix = ctx.prefix
            await ctx.send("Current prefix: `"+prefix+"`")
        else:
            await db_servers.update_prefix(prefix,ctx.guild.id)
            await ctx.send("✅ Prefix set to `"+prefix+"`")


    @commands.command(
        hidden = True,
        usage = "<amount> <currency>",
        description = "Convert currency between Euro and SA Rand.",
        help = """- `<amount>`: a number to convert
                  - `<currency>`: either: 'euros', 'euro', 'EUR', '€', 'e' or 'rand', 'ZAR', 'R' (not case-sensitive)"""
    )
    async def convert(self,ctx,amount,currency):
        try:
            amount = float(amount)
        except ValueError:
            return await ctx.send("❌ `amount` parameter must be a number.")
        apikey = os.environ.get("CURRCONV_API_KEY")
        url = f'https://free.currconv.com/api/v7/convert?q=EUR_ZAR,ZAR_EUR&compact=ultra&apiKey={apikey}'
        json_response = await get_content(url,'json')
        EUR_ZAR = json_response["EUR_ZAR"]
        ZAR_EUR = json_response["ZAR_EUR"]

        test_list_eur = ["euros","euro","eu","eur","€","e"]
        test_list_zar = ["rand","zar","r"]

        if currency.lower() in test_list_eur:
            return await ctx.send(f'{amount}€ = {round(amount*EUR_ZAR,2)} rand')
        elif currency.lower() in test_list_zar:
            return await ctx.send(f'{amount} rand = {round(amount*ZAR_EUR,2)}€')
        else:
            return await ctx.send("❌ Invalid `currency` parameter.")

    choices = ["years","months","weeks","days","hours","minutes","seconds"]
    @cog_ext.cog_slash(name="timeconvert",
        description="Convert time formats.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="time",
            description="A time duration in the format ?y?mo?w?d?h?m?s",
            option_type=3,
            required=True
        ),
        create_option(
            name="unit",
            description="Convert the time to this unit.",
            option_type=3,
            required=False,
            choices=[
                create_choice(name=c, value=c
                )
            for c in choices]
        )]
    )
    async def _timeconvert(self,ctx:SlashContext, time,unit=None):
        if unit:
            await self.timeconvert(ctx,time,"-" + unit)
        else:
            await self.timeconvert(ctx,time)

    @commands.command(
        usage="<?y?mo?w?d?h?m?s> {-year|month|week|day|hour|minute|second}",
        description = "Convert time formats.",
        aliases = ["converttime","tconvert","tc"]
        )
    async def timeconvert(self,ctx,input, *options):
        try:
            time = str_to_td(input)
        except OverflowError:
            return await ctx.send(f"❌ The time given is too big.")
        if not time:
            return await ctx.send(f"❌ Invalid `time` parameter, format must be `?y?mo?w?d?h?m?s`.")

        if len(options) > 0:
            options = [o.lower().strip("s") for o in options]
            if "-year" in options or "-y" in options:
                res_nb = time/timedelta(days=365)
                res_unit = "year"
            elif "-month" in options:
                res_nb = time/timedelta(days=30)
                res_unit = "month"
            elif "-week" in options or "-w" in options:
                res_nb = time/timedelta(weeks=1)
                res_unit = "week"
            elif "-day" in options or "-d" in options:
                res_nb = time/timedelta(days=1)
                res_unit = "day"
            elif "-hour" in options or "-h" in options:
                res_nb = time/timedelta(hours=1)
                res_unit = "hour"
            elif "-minute" in options or "-m" in options:
                res_nb = time/timedelta(minutes=1)
                res_unit = "minute"
            elif "-second" in options or "-s" in options:
                res_nb = time/timedelta(seconds=1)
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
                    required=True
                )
            ])
    async def _rl(self,ctx:SlashContext,extension):
        appinfo = await self.client.application_info()
        if ctx.author != appinfo.owner:
            raise commands.NotOwner()

        await self.rl(ctx,extension)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def rl(self,ctx,extension):
        try:
            self.client.reload_extension("cogs."+extension)
        except Exception as e:
            return await ctx.send('```❌ {}: {} ```'.format(type(e).__name__, e))
            
        await ctx.send(f"✅ Extension `{extension}` has been reloaded")

    @cog_ext.cog_slash(
        name="help",
        description="Show all the slash commands and their description.",
        guild_ids=GUILD_IDS)
    async def _help(self,ctx:SlashContext):
        categories = {}
        for command in self.client.slash.commands.values():
            if command and command.name != "rl":
                cog_fullname = fullname(command.cog)
                cog_fullname = cog_fullname.split(".")
                cog_dir = cog_fullname[1:-2]
                cog_dir = cog_dir[0].capitalize() if len(cog_dir)>0 else "Other"

                text = f"• `/{command.name}`: {command.description}"

                # categories are organized by cog folders
                try:
                    categories[cog_dir].append(text)
                except KeyError:
                    categories[cog_dir] = [text]

        embed = discord.Embed(title="Command help",color=0x66c5cc)
        embed.set_thumbnail(url=ctx.me.avatar_url)

        for category in categories:
            if category != "Other":
                embed.add_field(name=f"**{category}**",value="\n".join(categories[category]),inline=False)
        if "Other" in categories:
            embed.add_field(name="**Other**",value="\n".join(categories["Other"]),inline=False)
    
        await ctx.send(embed=embed)

    @cog_ext.cog_slash(
        name="time",
        description="Show the current time in a timezone.",
        guild_ids=GUILD_IDS,
        options=[create_option(
            name="timezone",
            description="A timezone name (ex: 'UTC+8', US/Pacific, PST).",
            option_type=3,
            required=True
        )]
    )
    async def _time(self,ctx,timezone):
        await self.time(ctx,timezone)

    @commands.command(
        name="time",
        description = "Show the current time in a timezone.",
        usage = "<timezone>")
    async def time(self, ctx, timezone:str):
        tz = get_timezone(timezone)
        if tz == None:
            return await ctx.send("❌ Timezone not found.")

        await ctx.send("Current `{}` time: {}".format(
            timezone,
            datetime.astimezone(datetime.now(),tz).strftime("**%H:%M** (%Y-%m-%d)")
        ))

def setup(client):
    client.add_cog(Utility(client))
