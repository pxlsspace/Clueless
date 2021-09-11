import os
import sys
from discord.ext import commands
from dotenv import load_dotenv
import traceback
from datetime import timezone
from discord_slash import SlashCommand
from discord_slash.context import SlashContext

from utils.help import *
from utils.setup import DEFAULT_PREFIX, db_stats, db_servers, db_users

load_dotenv()
intents = discord.Intents.all()
client = commands.Bot(command_prefix=db_servers.get_prefix,help_command=HelpCommand(),intents=intents)
slash = SlashCommand(client,sync_commands=True,sync_on_cog_reload=True)

### on event functions ###
@client.event
async def on_connect():
    # create db tables if they dont exist
    await db_servers.create_tables()
    await db_users.create_tables()
    await db_stats.create_tables()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_slash_command(ctx):
    await on_command(ctx)

@client.event
async def on_command(ctx):
    # log commands used in a channel
    log_channel_id = os.environ.get("COMMAND_LOG_CHANNEL")

    try:
        log_channel = await client.fetch_channel(log_channel_id)
    except:
        return

    slash_command = isinstance(ctx,SlashContext)
    if slash_command:
        command_name = ctx.command
    else:
        command_name = ctx.command.qualified_name

    if isinstance(ctx.channel, discord.channel.DMChannel):
            context = "DM"
    else:
        context = f"• **Server**: {ctx.guild.name} "
        context += f"• **Channel**: <#{ctx.channel.id}>\n"

    message_time = ctx.message.created_at if not slash_command else ctx.created_at
    message_time = message_time.replace(tzinfo=timezone.utc)
    message = f"By <@{ctx.author.id}> "
    message += f"on <t:{int(message_time.timestamp())}>\n"
    if not slash_command:
        message += f"```{ctx.message.content}```"
        message += f"[link to the message]({ctx.message.jump_url})\n"
    else:
        if "options" in ctx.data:
            options = " ".join([f'{o["name"]}:{o["value"]}' for o in ctx.data["options"]])
        else:
            options=""
        message += f'```/{command_name}{" " + options}```'

    emb = discord.Embed(
        color=0x00bb00,
        title = "Command '{}' used.".format(command_name))
    emb.add_field(name="Context:",value=context,inline=False)
    emb.add_field(name="Message:",value=message,inline=False)
    emb.set_thumbnail(url=ctx.author.avatar_url)

    await log_channel.send(embed=emb)

@client.event
async def on_slash_command_error(ctx,error):
    await on_command_error(ctx,error)

@client.event
async def on_command_error(ctx,error):
    if isinstance(error, commands.CommandNotFound):
        return
    slash_command = isinstance(ctx,SlashContext)
    if slash_command:
        command_name = ctx.command
    else:
        command_name = ctx.command.qualified_name
    # handled errors
    if not slash_command and isinstance(error,commands.MissingRequiredArgument):
        text = "❌ " + str(error) + "\n"
        text += f'Usage: `{ctx.prefix}{command_name} {ctx.command.usage}`'
        return await ctx.send(text)
    if isinstance(error, commands.MissingPermissions) or isinstance(error,commands.NotOwner):
       return await ctx.send(f"❌ You don't have permissions to use the `{command_name}` command.")
    if isinstance(error,commands.CommandOnCooldown):
        return await ctx.send(f"❌ {error}")
    if  isinstance(error, OverflowError) or (isinstance(error,commands.CommandInvokeError) and isinstance(error.original,OverflowError)):
        return await ctx.send("❌ Overflow error. <a:bruhkitty:880829401359589446>")

    # unhandled errors
    if slash_command:
        if not isinstance(error,discord.errors.NotFound):
            embed = discord.Embed(color=0xff4747,title="Unexpected error.",
               description="<a:peepoLeaveNope:822571977390817340> An unexpected error occurred, please contact the bot developer if the problem persists.")
            await ctx.reply(embed=embed,hidden=True)
    else:
        await ctx.message.add_reaction(r'a:peepoLeaveNope:822571977390817340')
    print('Ignoring exception in command {}:'.format(command_name), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    # send message in log error channel
    log_channel_id = os.environ.get("ERROR_LOG_CHANNEL")
    try:
        log_channel = await client.fetch_channel(log_channel_id)
    except:
        return
    if log_channel != None:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb = tb[2:4]
        tb = "".join(tb)

        if isinstance(ctx.channel, discord.channel.DMChannel):
            context = "DM"
        else:
            context = f"• **Server**: {ctx.guild.name} ({ctx.guild.id})\n"
            context += f"• **Channel**: <#{ctx.channel.id}>\n"

        message_time = ctx.message.created_at if not slash_command else ctx.created_at
        message_time = message_time.replace(tzinfo=timezone.utc)
        message = f"By <@{ctx.author.id}> "
        message += f"on <t:{int(message_time.timestamp())}>\n"
        
        if not slash_command:
            message += f"```{ctx.message.content}```"
            message += f"[link to the message]({ctx.message.jump_url})\n"
        else:
            if "options" in ctx.data:
                options = " ".join([f'{o["name"]}:{o["value"]}' for o in ctx.data["options"]])
            else:
                options=""
            message += f'```/{command_name}{" " + options}```'
        emb = discord.Embed(
            color=0xff0000,
            title = "Unexpected exception in command '{}'".format(command_name))
        emb.add_field(name="Context:",value=context,inline=False)
        emb.add_field(name="Message:",value=message,inline=False)
        emb.add_field(name="Error:",value=f'```{error.__class__.__name__}: {error}```' ,inline=False)
        emb.add_field(name="Traceback:",value=f"```\n{tb}```",inline=False)

        await log_channel.send(embed=emb)

@client.event
async def on_message(message):
    await client.wait_until_ready()

    # check that the user isn't the bot itself
    if message.author == client.user:
        return
    
    # check that the user isn't an other bot
    if message.author.bot:
        return

    # add the user to the db and check if the user is blacklisted
    discord_user = await db_users.get_discord_user(message.author.id)
    if discord_user["is_blacklisted"] == True:
        return

    if message.guild:
        # check that server is in the db
        server = await db_servers.get_server(message.guild.id)
        if server == None:
            await db_servers.create_server(message.guild.id,DEFAULT_PREFIX)
            print("joined a new server: {0.name} (id: {0.id})".format(message.guild))

        # check if user has a blacklisted role
        blacklist_role_id = await db_servers.get_blacklist_role(message.guild.id)
        if blacklist_role_id != None:
            blacklist_role = message.guild.get_role(int(blacklist_role_id))
            if blacklist_role != None:
                if blacklist_role in message.author.roles:
                    return

    if message.content == ">_>":
        return await message.channel.send("<_<")

    if message.content == 'aa':
        await message.channel.send('<:watermelonDEATH:856212273718886400>')

    if client.user in  message.mentions:
        await message.add_reaction("<:peepopinged:867331826442960926>") 
    await client.process_commands(message)

@client.event
async def on_guild_join(guild):
    await db_servers.create_server(guild.id,DEFAULT_PREFIX)
    print("joined a new server: {0.name} (id: {0.id})".format(guild))

if __name__ == "__main__":

    # loading cogs
    commands_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cogs")
    for path, subdirs, files in os.walk(commands_dir):
        parent_dir = path
        for extension in files:
            if extension.endswith(".py"):
                try:
                    if parent_dir != commands_dir:
                        relpath = os.path.relpath(os.path.join(parent_dir,extension),commands_dir)
                        extension = ".".join(os.path.split(relpath))
                    client.load_extension("cogs." + extension[:-3])
                except Exception as e:
                    print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

    # run the bot
    client.run(os.environ.get("DISCORD_TOKEN"))