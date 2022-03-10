import os
import disnake
import traceback
from disnake.ext import commands
from dotenv import load_dotenv
from datetime import timezone

from utils.pxls.template_manager import TemplateManager
from utils.setup import (
    DEFAULT_PREFIX,
    db_stats,
    db_servers,
    db_users,
    db_templates,
    GUILD_IDS,
)
from utils.log import get_logger, setup_loggers, close_loggers


load_dotenv()
intents = disnake.Intents.all()
activity = disnake.Activity(
    type=disnake.ActivityType.watching, name="you placing those pixels 👀"
)
allowed_mentions = disnake.AllowedMentions(
    everyone=False,
    users=False,
    roles=False,
    replied_user=False,
)
bot = commands.Bot(
    command_prefix=db_servers.get_prefix,
    help_command=None,
    intents=intents,
    case_insensitive=True,
    activity=activity,
    test_guilds=GUILD_IDS,
    reload=bool(GUILD_IDS),
    allowed_mentions=allowed_mentions,
)

tracked_templates = TemplateManager()


@bot.event
async def on_connect():
    # create db tables if they dont exist
    await db_servers.create_tables()
    await db_users.create_tables()
    await db_stats.create_tables()
    await db_templates.create_tables()


@bot.event
async def on_ready():
    logger.info("We have logged in as {0.user}".format(bot))


@bot.event
async def on_slash_command(ctx):
    await on_command(ctx)


@bot.event
async def on_command(ctx):
    """Save the command usage in the database and in a discord channel if set"""
    slash_command = isinstance(ctx, disnake.ApplicationCommandInteraction)
    if slash_command:
        command_name = ctx.application_command.qualified_name
    else:
        command_name = ctx.command.qualified_name

    is_dm = ctx.guild is None

    if is_dm:
        server_name = None
        channel_id = None
        context = "DM"
    else:
        server_name = ctx.guild.name
        channel_id = ctx.channel.id
        context = f"• **Server**: {server_name} "
        context += f"• **Channel**: <#{channel_id}>\n"

    message_time = ctx.message.created_at if not slash_command else ctx.created_at
    message_time = message_time.replace(tzinfo=timezone.utc)
    author_id = ctx.author.id
    message = f"By <@{author_id}> "
    message += f"on <t:{int(message_time.timestamp())}>\n"
    if not slash_command:
        if len(message + ctx.message.content) > 1024:
            args = "[Message too long to show]"
        else:
            args = ctx.message.content
        message += f"```{args}```"
        message += f"[link to the message]({ctx.message.jump_url})\n"
    else:
        options = ""
        for key, value in ctx.filled_options.items():
            options += f" {key}:{value}"
        args = f"/{command_name}{options}"
        if len(message + args) >= 1024:
            message += "```[Command too long to show]```"
        else:
            message += f"```{args}```"

    # save commands used in the database
    await db_servers.create_command_usage(
        command_name,
        is_dm,
        server_name,
        channel_id,
        author_id,
        message_time.replace(tzinfo=None),
        args,
        slash_command,
    )

    # log commands used in a channel if a log channel is set
    log_channel_id = os.environ.get("COMMAND_LOG_CHANNEL")
    try:
        log_channel = await bot.fetch_channel(log_channel_id)
    except Exception:
        return
    emb = disnake.Embed(color=0x00BB00, title="Command '{}' used.".format(command_name))
    emb.add_field(name="Context:", value=context, inline=False)
    emb.add_field(name="Message:", value=message, inline=False)
    emb.set_thumbnail(url=ctx.author.display_avatar)
    await log_channel.send(embed=emb)


@bot.event
async def on_slash_command_error(ctx, error):
    await on_command_error(ctx, error)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    ignored = (commands.CommandNotFound, commands.DisabledCommand)
    if isinstance(error, ignored):
        return

    slash_command = isinstance(ctx, disnake.ApplicationCommandInteraction)
    if slash_command:
        command_name = ctx.application_command.qualified_name
    else:
        command_name = ctx.command.qualified_name

    # handled errors
    if not slash_command and isinstance(error, commands.MissingRequiredArgument):
        text = "❌ " + str(error) + "\n"
        text += f"Usage: `{ctx.prefix}{command_name} {ctx.command.usage}`"
        return await ctx.send(text)

    if isinstance(error, (commands.MissingPermissions, commands.NotOwner)):
        return await ctx.send(
            f"❌ You don't have permissions to use the `{command_name}` command."
        )

    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"❌ {error}")

    if isinstance(error, OverflowError):
        return await ctx.send("❌ Overflow error. <a:bruhkitty:880829401359589446>")

    if isinstance(error, (disnake.errors.Forbidden, disnake.Forbidden)):
        # Try to send error message
        missing_perms_emoji = "<:Im_missing_permissions:950557152815222806>"
        try:
            embed = disnake.Embed(
                color=0xFF4747,
                title="Missing Permissions",
                description=f"{missing_perms_emoji} I'm missing permissions to run this command.",
            )
            return await ctx.send(embed=embed)
        except Exception:
            # Try to add reaction
            try:
                return await ctx.message.add_reaction(missing_perms_emoji)
            except Exception:
                # Give up
                return

    # unhandled errors
    try:
        if slash_command:
            if not isinstance(error, disnake.errors.NotFound):
                embed = disnake.Embed(
                    color=0xFF4747,
                    title="Unexpected error.",
                    description="<a:peepoLeaveNope:822571977390817340> An unexpected error occurred, please contact the bot developer if the problem persists.",
                )
                await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.message.add_reaction(r"a:peepoLeaveNope:822571977390817340")
    except Exception:
        pass

    logger.exception(
        f"Unexpected exception in command {command_name} by {ctx.author}:",
        exc_info=error,
    )

    # send message in log error channel
    log_channel_id = os.environ.get("ERROR_LOG_CHANNEL")
    try:
        log_channel = await bot.fetch_channel(log_channel_id)
    except Exception:
        return
    if log_channel is not None:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb = tb[2:4]
        tb = "".join(tb)

        if ctx.guild is None:
            context = "DM"
        else:
            context = f"• **Server**: {ctx.guild.name} ({ctx.guild.id})\n"
            context += f"• **Channel**: <#{ctx.channel.id}>\n"

        message_time = ctx.message.created_at if not slash_command else ctx.created_at
        message_time = message_time.replace(tzinfo=timezone.utc)
        message = f"By <@{ctx.author.id}> "
        message += f"on <t:{int(message_time.timestamp())}>\n"

        if not slash_command:
            if len(message + ctx.message.content) >= 1024:
                message += "```[Message too long to show]```"
            else:
                message += f"```{ctx.message.content}```"
            message += f"[link to the message]({ctx.message.jump_url})\n"
        else:
            options = ""
            for key, value in ctx.filled_options.items():
                options += f" {key}:{value}"
            args = f"/{command_name}{options}"
            if len(message + args) >= 1024:
                message += "```[Command too long to show]```"
            else:
                message += f"```{args}```"
        emb = disnake.Embed(
            color=0xFF0000,
            title="Unexpected exception in command '{}'".format(command_name),
        )
        emb.add_field(name="Context:", value=context, inline=False)
        emb.add_field(name="Message:", value=message, inline=False)
        emb.add_field(
            name="Error:",
            value=f"```{error.__class__.__name__}: {error}```",
            inline=False,
        )
        emb.add_field(name="Traceback:", value=f"```\n{tb}```", inline=False)

        await log_channel.send(embed=emb)


@bot.event
async def on_message(message):
    await bot.wait_until_ready()

    # check that the user isn't the bot itself
    if message.author == bot.user:
        return

    # check that the user isn't an other bot
    if message.author.bot:
        return

    # add the user to the db and check if the user is blacklisted
    discord_user = await db_users.get_discord_user(message.author.id)
    if discord_user["is_blacklisted"]:
        return

    if message.guild:
        # check that server is in the db
        server = await db_servers.get_server(message.guild.id)
        if server is None:
            await db_servers.create_server(message.guild.id, DEFAULT_PREFIX)
            logger.info(
                "joined a new server: {0.name} (id: {0.id})".format(message.guild)
            )

        # check if user has a blacklisted role
        blacklist_role_id = await db_servers.get_blacklist_role(message.guild.id)
        if blacklist_role_id is not None:
            blacklist_role = message.guild.get_role(int(blacklist_role_id))
            if blacklist_role is not None:
                if blacklist_role in message.author.roles:
                    return

    if message.content == ">_>":
        try:
            return await message.channel.send("<_<")
        except Exception:
            pass

    if message.content == "aa":
        try:
            await message.channel.send("<:watermelonDEATH:856212273718886400>")
        except Exception:
            pass

    if bot.user in message.mentions:
        try:
            await message.add_reaction("<:peepopinged:867331826442960926>")
        except Exception:
            pass
    await bot.process_commands(message)


@bot.event
async def on_guild_join(guild):
    await db_servers.create_server(guild.id, DEFAULT_PREFIX)
    logger.info("joined a new server: {0.name} (id: {0.id})".format(guild))

    # get the log channel
    log_channel_id = os.environ.get("ERROR_LOG_CHANNEL")
    try:
        log_channel = await bot.fetch_channel(log_channel_id)
    except Exception:
        # don't log if no log channel is set
        return

    # make the embed and send it in the log channel
    embed = disnake.Embed(
        title="**Joined a new server!**",
        color=0x66C5CC,
        timestamp=guild.created_at,
    )
    embed.add_field(name="**Server Name**", value=guild.name)
    embed.add_field(name="**Owner**", value=guild.owner)
    embed.add_field(name="**Members**", value=guild.member_count)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"ID • {guild.id} | Server Created")
    await log_channel.send(embed=embed)


@bot.event
async def on_guild_remove(guild):
    await db_servers.delete_server(guild.id)
    logger.info("left server: {0.name} (id: {0.id})".format(guild))

    # get the log channel
    log_channel_id = os.environ.get("ERROR_LOG_CHANNEL")
    try:
        log_channel = await bot.fetch_channel(log_channel_id)
    except Exception:
        # don't log if no log channel is set
        return

    # make the embed and send it in the log channel
    embed = disnake.Embed(
        title="**Left a server**",
        color=0xFF3621,
        timestamp=guild.created_at,
    )
    embed.add_field(name="**Server Name**", value=guild.name)
    embed.add_field(name="**Owner**", value=guild.owner)
    embed.add_field(name="**Members**", value=guild.member_count)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"ID • {guild.id} | Server Created")
    await log_channel.send(embed=embed)


if __name__ == "__main__":

    # setting up loggers
    setup_loggers()
    logger = get_logger("main")

    # loading cogs
    logger.debug("Loading cogs")
    commands_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cogs")
    for path, subdirs, files in os.walk(commands_dir):
        parent_dir = path
        for extension in files:
            if extension.endswith(".py"):
                try:
                    if parent_dir != commands_dir:
                        relpath = os.path.relpath(
                            os.path.join(parent_dir, extension), commands_dir
                        )
                        extension = ".".join(os.path.split(relpath))
                    bot.load_extension("cogs." + extension[:-3])
                except Exception:
                    logger.exception(f"Failed to load extension {extension}")
    try:
        # __start__
        logger.debug("Starting bot ...")
        bot.run(os.environ.get("DISCORD_TOKEN"))
    finally:
        # __exit__
        logger.critical("Bot shut down.")
        close_loggers()
