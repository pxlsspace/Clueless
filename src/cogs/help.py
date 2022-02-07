import discord
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option
from discord_slash.model import ButtonStyle
from discord_slash.utils.manage_components import (
    create_button,
    create_actionrow,
    ComponentContext,
)

from utils.discord_utils import get_embed_author
from utils.setup import GUILD_IDS, db_servers

TYPES = {
    3: "text",
    4: "integer",
    5: "True|False",
    6: "@user",
    7: "#channel",
    8: "@role",
    9: "user|role",
    10: "number",
}

EMBED_COLOR = 0x66C5CC
CATEGORIES = {
    "Reddit": {
        "description": "Get random images from reddit.",
        "emoji_id": 939539009833668619,
    },
    "Pixel Art": {
        "description": "Useful tools to make pixel art.",
        "emoji_id": 939537785658933350,
    },
    "Pxls": {
        "description": "Most pxls related commands.",
        "emoji_id": 939538707919306783,
    },
    "Pxls Template": {
        "description": "Commands to handle pxls templates.",
        "emoji_id": 939539139567681578,
    },
    "Other": {
        "description": None,
        "emoji_id": 939539309873209426,
    },
}

HOME_EMOJI_ID = 939542127472439338


class Help(commands.Cog):
    """A cog with all the help commands to get information about the other commands."""

    def __init__(self, client):
        self.client = client

    def get_buttons(self, categories, current_category, is_slash):
        """Create the buttons depending on the categories and current categories."""
        buttons = []
        if current_category:
            home_emoji = self.client.get_emoji(HOME_EMOJI_ID)
            buttons.append(
                create_button(
                    style=ButtonStyle.blue,
                    custom_id=("slash_" if is_slash else "") + "Home",
                    emoji=home_emoji,
                )
            )
        for category in categories:
            if category != current_category and category != "Other":
                category_infos = CATEGORIES[category]
                category_emoji_id = category_infos["emoji_id"]
                category_emoji = self.client.get_emoji(id=category_emoji_id)
                button_id = "{}{}".format(
                    "slash_" if is_slash else "",
                    category,
                )
                buttons.append(
                    create_button(
                        style=ButtonStyle.gray,
                        label=category,
                        custom_id=button_id,
                        emoji=category_emoji,
                    )
                )
        if "Other" in categories and current_category != "Other":
            category_infos = CATEGORIES["Other"]
            category_emoji_id = category_infos["emoji_id"]
            category_emoji = self.client.get_emoji(id=category_emoji_id)
            buttons.append(
                create_button(
                    style=ButtonStyle.gray,
                    label="Other",
                    custom_id=("slash_" if is_slash else "") + "Other",
                    emoji=category_emoji,
                )
            )
        return buttons

    async def send_home_help(self, ctx, author, is_slash):
        """Called when >help or /help is used."""
        if is_slash:
            categories = get_slash_mapping(self.client.slash)
            prefix = "/"
        else:
            categories = get_client_mapping(self.client)
            prefix = await db_servers.get_prefix(self.client, ctx)

        # create the embed header
        home_emoji = self.client.get_emoji(HOME_EMOJI_ID)
        emb = discord.Embed(title=f"{home_emoji} Command help", color=EMBED_COLOR)
        emb.description = (
            f"Use `{prefix}help [command]` to see more information about a command.\n"
            + f"Use `{prefix}help [category]` to see more information about a category.\n"
        )
        emb.set_author(name=ctx.me, icon_url=ctx.me.avatar_url)
        emb.set_footer(text=f"Requested by {author}", icon_url=author.avatar_url)

        # add a field and button per category
        for category, category_commands in categories.items():
            if category != "Other":
                category_infos = CATEGORIES.get(category) or CATEGORIES[None]
                category_emoji_id = category_infos["emoji_id"]
                category_emoji = self.client.get_emoji(id=category_emoji_id)
                commands_text = " ".join([f"`{c.name}`" for c in category_commands])
                emb.add_field(
                    name=f"{category_emoji} {category}",
                    value=commands_text,
                    inline=False,
                )
        # add the "Other" category after the loop so it's always last
        if "Other" in categories:
            commands = categories["Other"]
            category_infos = CATEGORIES.get("Other") or CATEGORIES[None]
            category_emoji_id = category_infos["emoji_id"]
            category_emoji = ctx.bot.get_emoji(id=category_emoji_id)
            commands_text = " ".join([f"`{c.name}`" for c in commands])
            emb.add_field(
                name=f"{category_emoji} Other", value=commands_text, inline=False
            )
        buttons = self.get_buttons(categories, None, is_slash)
        action_row = create_actionrow(*buttons)

        if isinstance(ctx, ComponentContext):
            await ctx.edit_origin(embed=emb, components=[action_row])
        else:
            await ctx.send(embed=emb, components=[action_row])

    async def send_category_help(self, ctx, category_name, author, is_slash, send_buttons=True):
        """called when >help <category> or /help <category> is used."""
        if category_name == "Home":
            return await self.send_home_help(ctx, author, is_slash)

        if is_slash:
            categories = get_slash_mapping(self.client.slash)
            prefix = "/"
        else:
            categories = get_client_mapping(self.client)
            prefix = await db_servers.get_prefix(self.client, ctx)

        category_infos = CATEGORIES[category_name]
        commands = categories[category_name]
        category_description = category_infos["description"]
        category_emoji_id = category_infos["emoji_id"]
        category_emoji = self.client.get_emoji(id=category_emoji_id)
        commands_text = ""
        for command in commands:
            commands_text += "• `{}{}`: {}\n".format(
                prefix, command.name, command.description or "N/A"
            )

        emb = discord.Embed(
            title=f"{category_emoji} {category_name} Category",
            color=EMBED_COLOR,
            description=f"Use `{prefix}help [command]` to see more information about a command.\n"
        )
        if category_description:
            emb.add_field(
                name="**Description**", value=category_description, inline=False
            )
        emb.add_field(name="**Commands**", value=commands_text, inline=False)
        emb.set_author(name=ctx.me, icon_url=ctx.me.avatar_url)
        emb.set_footer(text=f"Requested by {author}", icon_url=author.avatar_url)

        if send_buttons:
            buttons = self.get_buttons(categories, category_name, is_slash)
            action_row = create_actionrow(*buttons)
            components = [action_row]
        else:
            components = None

        if isinstance(ctx, ComponentContext):
            await ctx.edit_origin(embed=emb, components=components)
        else:
            await ctx.send(embed=emb, components=components)

    async def send_command_help(self, ctx, command, is_slash):
        """called when >help <command> or /help <command> is used."""
        if is_slash:
            prefix = "/"
            command_name = command.name
            command_usage = get_slash_command_usage(command)
            command_params = get_slash_command_parameters(command)
        else:
            prefix = ctx.prefix
            command_name = command.qualified_name
            command_usage = command.usage
            command_params = command.help
        prefix = "/" if is_slash else ctx.prefix
        emb = discord.Embed(title=f"**Command {command_name}**", color=EMBED_COLOR)
        emb.set_author(name=ctx.me, icon_url=ctx.me.avatar_url)
        emb.add_field(
            name="Usage:",
            value=f"`{prefix}{command_name} {command_usage or ''}`",
            inline=False,
        )
        emb.add_field(
            name="Description:", value=command.description or "N/A", inline=False
        )
        emb.set_footer(
            text="<> is a required argument. [] is an optional argument. | means 'or'"
        )

        if not (is_slash) and command.aliases is not None and len(command.aliases) > 0:
            aliases = [a for a in command.aliases]
            value = ""
            for a in aliases:
                value += f"`{a}` "
            emb.add_field(name="Alias(es): ", value=value, inline=False)

        if command_params:
            emb.add_field(name="Parameter(s):", value=command_params)
        await ctx.send(embed=emb)

    async def send_group_help(self, ctx, group):
        """Called when ">help <group command> is used."""
        prefix = ctx.prefix
        emb = discord.Embed(title=f"**Command {group.name}**", color=EMBED_COLOR)
        emb.set_author(name=ctx.me, icon_url=ctx.me.avatar_url)
        emb.add_field(
            name="Description: ", value=group.description or "N/A", inline=False
        )
        emb.add_field(
            name="Usage:",
            value=f"`{prefix}{group.name}{group.usage or ''}`",
            inline=False,
        )
        emb.set_footer(
            text="<> is a required argument. [] is an optional argument. | means 'or'"
        )

        if group.aliases is not None and len(group.aliases) > 0:
            aliases = [a for a in group.aliases]
            value = ""
            for a in aliases:
                value += f"`{a}` "
            emb.add_field(name="Alias(es): ", value=value, inline=False)

        if group.commands is not None and len(group.commands) > 0:
            commands_value = ""
            for command in group.commands:
                if command.hidden:
                    continue
                commands_value += "• `{} {}`: {}".format(
                    command.qualified_name,
                    command.usage or '',
                    command.description or 'N/A',
                )
            emb.add_field(name="Sub-commands: ", value=commands_value, inline=False)

        await ctx.send(embed=emb)

    @commands.command(name="help", description="Show all the commands.")
    async def help(self, ctx, *, command_name=None):
        return await self.handle_help(ctx, command_name, is_slash=False)

    @cog_ext.cog_slash(
        name="help",
        description="Show all the slash commands.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="command_name",
                description="The name of the command or category you want more information about.",
                option_type=3,
                required=False,
            )
        ],
    )
    async def _help(self, ctx: SlashContext, command_name=None):
        await self.handle_help(ctx, command_name, is_slash=True)

    async def handle_help(self, ctx, command_name, is_slash):
        if command_name is None:
            await self.send_home_help(ctx, ctx.author, is_slash)
        elif (
            (is_slash and command_name.title() in get_slash_mapping(self.client.slash))
            or (not(is_slash) and command_name.title() in get_client_mapping(self.client))
        ):
            await self.send_category_help(
                ctx, command_name.title(), ctx.author, is_slash, send_buttons=False
            )
        else:
            command_name = command_name.lower()
            keys = command_name.split(" ")
            if is_slash:
                cmd = self.client.slash.commands.get(keys[0])
            else:
                cmd = self.client.all_commands.get(keys[0])
            if cmd is None:
                return await ctx.send(
                    f":x: No command or category named `{command_name}` found."
                )

            for key in keys[1:]:
                try:
                    found = cmd.all_commands.get(key)
                except AttributeError:
                    return await ctx.send(
                        f":x: No subcommand named `{command_name}` found."
                    )
                else:
                    if found is None:
                        return await ctx.send(
                            f":x: No subcommand named `{command_name}` found."
                        )
                    cmd = found

            if isinstance(cmd, commands.Group):
                return await self.send_group_help(ctx, cmd)
            else:
                return await self.send_command_help(ctx, cmd, is_slash)

    @cog_ext.cog_component(
        use_callback_name=False,
        components=(
            list(CATEGORIES.keys()) + ["Home"]
            + [f"slash_{c}" for c in list(CATEGORIES.keys()) + ["Home"]]
        ),
    )
    async def help_buttons_callback(self, ctx: ComponentContext):
        """Handle what to do when a button a pressed on the help command."""
        # check if the help command was a slash or prefix
        if ctx.custom_id.startswith("slash_"):
            category_name = ctx.custom_id[6:]
            is_slash = True
        else:
            category_name = ctx.custom_id
            is_slash = False

        # check on the author
        command_author = await get_embed_author(ctx)
        if command_author != ctx.author or command_author is None:
            emb = discord.Embed(title="This isn't your command!", color=0xFF3621)
            emb.description = "Use the help command yourself to interact with the buttons."
            return await ctx.reply(embed=emb, hidden=True)

        # handle the button
        await ctx.defer(edit_origin=True)
        if category_name == "Home":
            await self.send_home_help(ctx, command_author, is_slash)
        else:
            await self.send_category_help(ctx, category_name, command_author, is_slash)


def setup(client):
    client.add_cog(Help(client))


def get_client_mapping(client: commands.Bot):
    """Get all the prefix commands groupped by category."""
    categories = {}
    mapping = {cog: cog.get_commands() for cog in client.cogs.values()}
    mapping[None] = [c for c in client.commands if c.cog is None]

    for cog in mapping:
        if cog is None:
            commands = mapping[cog]
            category_name = "Other"
        else:
            if len(cog.get_commands()) == 0:
                continue
            commands = cog.get_commands()
            # get the directory of the cog
            category_name = get_cog_category(cog)

        for command in commands:
            if not command.hidden:
                # categories are organized by cog folders
                try:
                    categories[category_name].append(command)
                except KeyError:
                    categories[category_name] = [command]
    return categories


def get_slash_mapping(slash):
    """Get all the prefix commands groupped by category."""
    categories = {}
    for command in slash.commands.values():
        if command and command.name != "rl":
            category_name = get_cog_category(command.cog)
            # categories are organized by cog folders
            try:
                categories[category_name].append(command)
            except KeyError:
                categories[category_name] = [command]
    return categories


def get_cog_category(cog: commands.Cog) -> str:
    """Retrieve a cog "category name" which is definied by it's parent folder name."""
    cog_fullname = fullname(cog)
    cog_fullname = cog_fullname.split(".")
    cog_dir = cog_fullname[1:-2]
    category_name = cog_dir[0].replace("_", " ").title() if len(cog_dir) > 0 else "Other"
    return category_name


def fullname(o):
    """Get the full name of a class/object."""
    klass = o.__class__
    module = klass.__module__
    if module == "builtins":
        return klass.__qualname__  # avoid outputs like 'builtins.str'
    return module + "." + klass.__qualname__


def get_slash_command_usage(slash_command):
    """Get all the slash command options as a string."""
    options = []
    for o in slash_command.options:
        if o["type"] in (1, 2):
            continue
        o_name = o["name"]
        if o["choices"]:
            o_choices = "|".join([c["name"] for c in o["choices"]])
        else:
            o_type = TYPES[o["type"]]
            o_choices = o_type

        option = f"{o_name}:{o_choices}"
        if o["required"]:
            options.append(f"<{option}>")
        else:
            options.append(f"[{option}]")
    return " ".join(options)


def get_slash_command_parameters(slash_command):
    """Get all the slash command parameters as a string."""
    params = []
    for o in slash_command.options:
        if o["type"] in (1, 2):
            continue
        o_name = o["name"]
        if o["choices"]:
            o_choices = "|".join([c["name"] for c in o["choices"]])
        else:
            o_type = TYPES[o["type"]]
            o_choices = o_type

        option = f"{o_name}:{o_choices}"
        if o["required"]:
            option = f"<{option}>"
        else:
            option = f"[{option}]"
        params.append(f"- `{option}`: {o['description'] or 'N/A'}")
    return "\n".join(params)
