import discord
from discord.ext import commands
import requests
import json
import os
from dotenv import load_dotenv
from utils.database import update_prefix
from utils.time_converter import str_to_td, td_format

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
    async def echo(self,ctx,text):
        await ctx.send(text)


    @commands.command(
        usage = "[prefix]",
        description = "Change or display the bot prefix."
    )
    async def prefix(self,ctx,prefix=None):
        if prefix == None:
            prefix = ctx.prefix
            await ctx.send("Current prefix: `"+prefix+"`")
        else:
            update_prefix(prefix,ctx.guild.id)
            await ctx.send("Prefix set to `"+prefix+"`")


    @commands.command(
        usage = "<amount> <currency>",
        description = "Convert currency between Euro and South African Rand.",
        help = """- `<amount>`: a number to convert
                  - `<currency>`: either: 'euros', 'euro', 'EUR', '€', 'e' or 'rand', 'ZAR', 'R' (not case-sensitive)"""
    )
    async def convert(self,ctx,amount,currency):
        try:
            amount = float(amount)
        except ValueError:
            return await ctx.send("❌ `amount` parameter must be a number.")
        apikey = os.environ.get("CURRCONV_API_KEY")
        r = requests.get(f'https://free.currconv.com/api/v7/convert?q=EUR_ZAR,ZAR_EUR&compact=ultra&apiKey={apikey}')
        EUR_ZAR = json.loads(r.text)["EUR_ZAR"]
        ZAR_EUR = json.loads(r.text)["ZAR_EUR"]

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
        description = "Converts time formats.",
        aliases = ["converttime","tconvert","tc"]
        )
    async def timeconvert(self,ctx,input):
        time = str_to_td(input)
        if not time:
            return await ctx.send(f"❌ Invalid `time` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
        await ctx.send(f"{input} = {td_format(time)}.")


    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def rl(self,ctx,extension):
        try:
            self.client.reload_extension("cogs."+extension)
        except Exception as e:
            return await ctx.send('``` {}: {} ```'.format(type(e).__name__, e))
            
        await ctx.send(f"✅ Extension `{extension}` has been reloaded")



def setup(client):
    client.add_cog(Utility(client))
