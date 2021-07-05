import os
import requests
import json
import discord

from discord import embeds
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv

from cogs.utils.database import *
from cogs.utils.help import *

DEFAULT_PREFIX = "$"
load_dotenv()

client = commands.Bot(command_prefix=get_prefix,help_command=HelpCommand())
#client.remove_command("help")

### on event functions ###
@client.event
async def on_ready():

    print('We have logged in as {0.user}'.format(client))

    # create db tables if they dont exist
    create_tables()

@client.event
async def on_command_error(ctx,error):
    await ctx.message.add_reaction(r'a:peepoLeaveNope:822571977390817340')
    await ctx.send(error)
    raise(error)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == 'a':
        await message.channel.send('<:watermelonDEATH:856212273718886400>')

    if message.content == 'what':
        await message.add_reaction('👽')

    await client.process_commands(message)
    
@client.event
async def on_guild_join(guild):
    create_server(guild.id,DEFAULT_PREFIX)
    print("joined a new server id: "+str(guild.id))

### commands ###
@client.command(description="`>ping`: pong!")
async def ping(ctx):
    await ctx.send(f"pong! (bot latency: `{round(client.latency*1000,2)}` ms)")

@client.command(
    usage = " <text>",
    description = "Repeats your text."
)
async def echo(ctx,text):
    await ctx.send(text)

@client.command(
    usage = " [prefix]",
    description = "Changes the bot prefix for this server or shows the server prefix."
)
async def prefix(ctx,prefix=None):
    if prefix == None:
        prefix = ctx.prefix
        await ctx.send("Current prefix: `"+prefix+"`")
    else:
        update_prefix(prefix,ctx.guild.id)
        await ctx.send("Prefix set to `"+prefix+"`")

@client.command(
    usage = " <amount> <currency>",
    description = "Converts currency from euro to rand or rand to euro."
)
async def convert(ctx,*args):
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


@client.command(aliases = ["rl"])
@commands.has_permissions(administrator=True)
async def reload(ctx,extension):
    try:
        client.reload_extension("cogs."+extension)
    except Exception as e:
        return await ctx.send('``` {}: {} ```'.format(type(e).__name__, e))
        
    await ctx.send(f"✅ Extension `{extension}` has been reloaded")

if __name__ == "__main__":
    # loading cogs
    for extension in os.listdir("./src/cogs"):
        if extension.endswith('.py'):
            try:
                client.load_extension("cogs." + extension[:-3])
            except Exception as e:
                print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

    # test bot
    client.run(os.environ.get("DISCORD_TOKEN"))