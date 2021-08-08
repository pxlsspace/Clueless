import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

from utils.setup import db_servers_manager as db_servers
from utils.time_converter import str_to_td, td_format
from utils.utils import get_content

class Utility(commands.Cog):
    ''' Various utility commands'''

    def __init__(self, client):
        load_dotenv()
        self.client = client

    @commands.command(description="pong! (show the bot latency)")
    async def ping(self,ctx):
        await ctx.send(f"pong! (bot latency: `{round(self.client.latency*1000,2)}` ms)")


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

    @commands.command(
        usage="<?d?h?m?s>",
        description = "Convert time formats.",
        aliases = ["converttime","tconvert","tc"]
        )
    async def timeconvert(self,ctx,input):
        time = str_to_td(input)
        if not time:
            return await ctx.send(f"❌ Invalid `time` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
        await ctx.send(f"{input} = {td_format(time)}.")


    @commands.command(hidden=True)
    @commands.is_owner()
    async def rl(self,ctx,extension):
        try:
            self.client.reload_extension("cogs."+extension)
        except Exception as e:
            return await ctx.send('``` {}: {} ```'.format(type(e).__name__, e))
            
        await ctx.send(f"✅ Extension `{extension}` has been reloaded")

def setup(client):
    client.add_cog(Utility(client))
