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