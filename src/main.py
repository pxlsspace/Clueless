import os
import sys
from discord.ext import commands
from dotenv import load_dotenv

from utils.database import *
from utils.help import *
import traceback

DEFAULT_PREFIX = "$"
load_dotenv()

client = commands.Bot(command_prefix=get_prefix,help_command=HelpCommand())

### on event functions ###
@client.event
async def on_ready():

    print('We have logged in as {0.user}'.format(client))

    # create db tables if they dont exist
    create_tables()

@client.event
async def on_command_error(ctx,error):
    if isinstance(error,commands.MissingRequiredArgument):
        text = "❌ " + str(error) + "\n"
        text += f'Usage: `{ctx.prefix}{ctx.command.qualified_name}{ctx.command.usage}`'
        return await ctx.send(text)
    if isinstance(error, commands.CommandNotFound):
        return await ctx.send("❌ " + str(error))

    await ctx.message.add_reaction(r'a:peepoLeaveNope:822571977390817340')
    await ctx.send(error)
    print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

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
    commands_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cogs")
    for extension in os.listdir(commands_dir):
        if extension.endswith('.py'):
            try:
                client.load_extension("cogs." + extension[:-3])
            except Exception as e:
                print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

    # test bot
    client.run(os.environ.get("DISCORD_TOKEN"))