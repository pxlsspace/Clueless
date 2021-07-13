import discord
from discord.embeds import Embed
from discord.ext import commands

EMBED_COLOR = 0xffd1ec
class HelpCommand(commands.HelpCommand):

    def __init__(self, **options):
        super().__init__(**options)

    # function called on ">help"
    async def send_bot_help(self, mapping):
        prefix = self.context.prefix

        text = "```\n"
        for cog in mapping:
            # ignore cog if it's empty or has no command
            if cog == None or len(cog.get_commands()) == 0:
                continue
            #value = ""
            for command in cog.get_commands():
                if command.hidden == True:
                    continue
                text += "• {:<13}: {}\n".format(
                    prefix + command.name,
                    command.description or 'N/A'
                )
        text+="```"
        #description = f'Use `{prefix}help [command]` to gain more information about that command.\n'

        emb = discord.Embed(title='Command help',
            color=EMBED_COLOR,
            description=text)
        #emb.set_thumbnail(url=self.context.me.avatar_url)
        emb.set_footer(text=f'Use {prefix}help [command] to see more information about a command.\n')
        await self.get_destination().send(embed=emb)

    # function called on ">help <cog name>"
    async def send_cog_help(self, cog):
        return await self.get_destination().send(f'No command called "{cog.qualified_name}" found.')

    # function called on ">help <group command>"
    async def send_group_help(self, group):
        if group.hidden == True:
            return await self.get_destination().send(f'No command called "{group}" found.')
        prefix = self.context.prefix
        emb = discord.Embed(title = f'**Command {group.name}**',color = EMBED_COLOR)
        emb.set_thumbnail(url=self.context.me.avatar_url)
        emb.add_field(name="Description: ",value=group.description or "N/A",inline=False)
        emb.add_field(name="Usage:",value=f"`{prefix}{group.name}{group.usage or ''}`",inline=False)
        emb.set_footer(text="<> is a required argument. [] is an optional argument. {} is a set of required items, you must choose one.")

        if group.aliases != None and len(group.aliases) > 0: 
            aliases = [a for a in group.aliases]
            value=""
            for a in aliases:
                value += f'`{a}` '
            emb.add_field(name="Alias(es): ",value=value,inline=False)

        if group.commands != None and len(group.commands) > 0:
            commands_value = ""
            for command in group.commands:
                if command.hidden == True:
                    continue
                commands_value += f"• `{command.name} {command.usage or ''}`: {command.description or 'N/A'}\n"
            emb.add_field(name="Sub-commands: ",value=commands_value,inline=False)

        await self.get_destination().send(embed=emb)


    # function called on ">help <command>"
    async def send_command_help(self, command):
        if command.hidden == True:
            return await self.get_destination().send(f'No command called "{command}" found.')
        prefix = self.context.prefix
        emb = discord.Embed(title = f'**Command {command.name}**',color = EMBED_COLOR)
        emb.set_thumbnail(url=self.context.me.avatar_url)
        emb.add_field(name="Usage:",value=f"`{prefix}{command.name} {command.usage or ''}`",inline=False)
        emb.add_field(name="Description:",value=command.description or "N/A",inline=False)
        emb.set_footer(text="<> is a required argument. [] is an optional argument. {} is a set of required items, you must choose one.")

        if command.aliases != None and len(command.aliases) > 0: 
            aliases = [a for a in command.aliases]
            value=""
            for a in aliases:
                value += f'`{a}` '
            emb.add_field(name="Alias(es): ",value=value,inline=False)

        if command.help != None:
            emb.add_field(name="Parameter(s):",value = command.help)
        await self.get_destination().send(embed=emb)

