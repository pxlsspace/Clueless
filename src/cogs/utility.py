import discord
from discord.ext import commands
from discord.ext.commands.converter import RoleConverter
from discord.ext.commands.errors import RoleNotFound
import requests
import json
import os
from dotenv import load_dotenv
from utils.database import update_blacklist_role, get_blacklist_role, update_prefix
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
            update_prefix(prefix,ctx.guild.id)
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


    @commands.group(hidden=True,invoke_without_command=True,description = "Show the current blacklist role.")
    @commands.check_any(commands.is_owner(),commands.has_permissions(manage_roles=True))
    async def blacklist(self,ctx):
        # show the current role
        current_role_id = get_blacklist_role(ctx.guild.id)
        if current_role_id == None:
            return await ctx.send(f"No blacklist role assigned, use `{ctx.prefix}{ctx.command} addrole <role>`")
        current_role = ctx.guild.get_role(int(current_role_id))
        if current_role == None:
            return await ctx.send(f"The current blacklist role is invalid, use `{ctx.prefix}{ctx.command} <role>`")
        else:
            no_role_mention = discord.AllowedMentions(roles=False) # to avoid pinging when showing the role
            return await ctx.send(f"Current blacklist role: <@&{current_role.id}>.",allowed_mentions=no_role_mention)

    @blacklist.command(
        description = "Add a blacklist role, any user with this role won't be able to use the bot.",
        usage = "<role name|role id|@role>"
        )
    async def addrole(self,ctx,role):
        # check that the role exists and save it
        try:
            role = await RoleConverter().convert(ctx,role)
        except RoleNotFound as e:
            return await ctx.send(f"❌ {e}")
        update_blacklist_role(ctx.guild.id,role.id)
        no_role_mention = discord.AllowedMentions(roles=False) # to avoid pinging when showing the role
        await ctx.send(f"✅ Blacklist role set to <@&{role.id}>.",allowed_mentions=no_role_mention)

    @blacklist.command(description = "Remove the current blacklist role.")
    async def removerole(self,ctx):
        update_blacklist_role(ctx.guild.id,None)
        await ctx.send("✅ Blacklist role removed.")

def setup(client):
    client.add_cog(Utility(client))
