import discord
from discord.embeds import Embed
from discord.ext import commands

EMBED_COLOR = 0x66c5cc
class HelpCommand(commands.HelpCommand):

    def __init__(self, **options):
        super().__init__(**options)

    # function called on ">help"
    async def send_bot_help(self, mapping):
        prefix = self.context.prefix
        categories = {}

        for cog in mapping:
            if cog == None:
                commands = mapping[cog]
                cog_dir = "Other"
            else:
                if len(cog.get_commands()) == 0:
                    continue
                commands = cog.get_commands()
                # get the directory of the cog
                cog_fullname = fullname(cog)
                cog_fullname = cog_fullname.split(".")
                cog_dir = cog_fullname[1:-2]
                cog_dir = cog_dir[0].capitalize() if len(cog_dir)>0 else "Other"

            for command in commands:
                if command.hidden == False:
                    text = "• `{}{}`: {}".format(
                        prefix,
                        command.name,
                        command.description or 'N/A')

                    # categories are organized by cog folders
                    try:
                        categories[cog_dir].append(text)
                    except KeyError:
                        categories[cog_dir] = [text]

        # create the embed header
        emb = discord.Embed(
            title='Command help',
            color=EMBED_COLOR,
            description=f'Use `{prefix}help [command]` to see more information about a command.')
        emb.set_thumbnail(url=self.context.me.avatar_url)

        # add a field per category
        for category in categories:
            if category != "Other":
                emb.add_field(name=category,value="\n".join(categories[category]),inline=False)
        if "Other" in categories:
            emb.add_field(name="Other",value="\n".join(categories["Other"]),inline=False)

        await self.get_destination().send(embed=emb)

    # function called on ">help <cog name>"
    async def send_cog_help(self, cog):
        return await self.get_destination().send(f'No command called "{cog.qualified_name}" found.')

    # function called on ">help <group command>"
    async def send_group_help(self, group):
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
                commands_value += f"• `{command.qualified_name} {command.usage or ''}`: {command.description or 'N/A'}\n"
            emb.add_field(name="Sub-commands: ",value=commands_value,inline=False)

        await self.get_destination().send(embed=emb)


    # function called on ">help <command>"
    async def send_command_help(self, command):
        prefix = self.context.prefix
        emb = discord.Embed(title = f'**Command {command.qualified_name}**',color = EMBED_COLOR)
        emb.set_thumbnail(url=self.context.me.avatar_url)
        emb.add_field(name="Usage:",value=f"`{prefix}{command.qualified_name} {command.usage or ''}`",inline=False)
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

def fullname(o):
    ''' get the full name of a class/object'''
    klass = o.__class__
    module = klass.__module__
    if module == 'builtins':
        return klass.__qualname__ # avoid outputs like 'builtins.str'
    return module + '.' + klass.__qualname__
