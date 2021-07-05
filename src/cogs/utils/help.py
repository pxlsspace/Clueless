import discord
from discord.embeds import Embed
from discord.ext import commands

EMBED_COLOR = 0xffd1ec
DEFAULT_PREFIX = ">"
class HelpCommand(commands.HelpCommand):

    def __init__(self, **options):
        super().__init__(**options)

    # function called on ">help"
    async def send_bot_help(self, mapping):
        prefix = DEFAULT_PREFIX

        description = f'Use `{prefix}help [command]` to gain more information about that command.\n'
        emb = discord.Embed(title='Command help',
            color=EMBED_COLOR,
            description=description)       

        for cog in mapping:
            # ignore cog if it's empty or has no command
            if cog == None or len(cog.get_commands()) == 0:
                continue
            name = f'**{cog.qualified_name}**'
            value = ""
            for command in cog.get_commands():
                value += f"• `{prefix}{command.name}{command.usage or ''}`: {command.description or 'N/A'}\n"
            if value != "":
                emb.add_field(name=name,value=value,inline=False)

        emb.set_footer(text="<> is a required argument. [] is an optional argument. {} is a set of required items, you must choose one.")
        await self.get_destination().send(embed=emb)

    # function called on ">help <cog name>"
    async def send_cog_help(self, cog):
        return await self.get_destination().send("❌ Invalid command name.")

    # function called on ">help <group command>"
    async def send_group_help(self, group):
        prefix = DEFAULT_PREFIX
        emb = discord.Embed(title = f'**Command {group.name}**',color = EMBED_COLOR)
        emb.add_field(name="Description: ",value=group.description or "N/A",inline=False)
        emb.add_field(name="Usage:",value=f"`{prefix}{group.name}{group.usage or ''}`",inline=False)

        if group.aliases != None and len(group.aliases) > 0: 
            aliases = [a for a in group.aliases]
            value=""
            for a in aliases:
                value += f'`{a}` '
            emb.add_field(name="Alias(es): ",value=value,inline=False)

        if group.commands != None and len(group.commands) > 0:
            commands_value = ""
            for command in group.commands:
                commands_value += f"• `{command.name}{command.usage or ''}`: {command.description or 'N/A'}\n"
            emb.add_field(name="Sub-commands: ",value=commands_value,inline=False)

        await self.get_destination().send(embed=emb)


    # function called on ">help <command>"
    async def send_command_help(self, command):
        prefix = DEFAULT_PREFIX
        emb = discord.Embed(title = f'**Command {command.name}**',color = EMBED_COLOR)
        emb.add_field(name="Usage:",value=f"`{prefix}{command.name}{command.usage or ''}`",inline=False)
        emb.add_field(name="Description:",value=command.description or "N/A",inline=False)

        if command.aliases != None and len(command.aliases) > 0: 
            aliases = [a for a in command.aliases]
            value=""
            for a in aliases:
                value += f'`{a}` '
            emb.add_field(name="Alias(es): ",value=value,inline=False)

        await self.get_destination().send(embed=emb)

