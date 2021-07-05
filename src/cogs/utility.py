import discord
from discord.ext import commands
import requests
import json
import os
from dotenv import load_dotenv
from cogs.utils.database import *

class Utility(commands.Cog):
    ''' Various utility commands'''

    def __init__(self, client):
        load_dotenv()
        self.client = client

    @commands.command(description="`>ping`: pong!")
    async def ping(self,ctx):
        await ctx.send(f"pong! (bot latency: `{round(self.client.latency*1000,2)}` ms)")


    @commands.command(
        usage = " <text>",
        description = "Repeats your text."
    )
    async def echo(self,ctx,text):
        await ctx.send(text)


    @commands.command(
        usage = " [prefix]",
        description = "Changes the bot prefix for this server or shows the server prefix."
    )
    async def prefix(self,ctx,prefix=None):
        if prefix == None:
            prefix = ctx.prefix
            await ctx.send("Current prefix: `"+prefix+"`")
        else:
            update_prefix(prefix,ctx.guild.id)
            await ctx.send("Prefix set to `"+prefix+"`")


    @commands.command(
        usage = " <amount> <currency>",
        description = "Converts currency from euro to rand or rand to euro."
    )
    async def convert(self,ctx,*args):
        apikey = os.environ.get("CURRCONV_API_KEY")
        r = requests.get(f'https://free.currconv.com/api/v7/convert?q=EUR_ZAR,ZAR_EUR&compact=ultra&apiKey={apikey}')
        EUR_ZAR = json.loads(r.text)["EUR_ZAR"]
        ZAR_EUR = json.loads(r.text)["ZAR_EUR"]

        test_list_eur = ["euros","euro","eu","€","e"]
        test_list_zar = ["rand","zar","r"]
        currency=args[1]
        currency=currency.lower()
        res_eur = [ele for ele in test_list_eur if(ele in currency)]
        res_zar = [ele for ele in test_list_zar if(ele in currency)]

        amount = int(args[0])
        if bool(res_eur):
            await ctx.send(f'{amount}€ = {round(amount*EUR_ZAR,2)} rand')
            return

        if bool(res_zar):
            
            await ctx.send(f'{amount} rand = {round(amount*ZAR_EUR,2)}€')
            return


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
