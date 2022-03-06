import disnake
from disnake.ext import commands


from utils.discord_utils import get_embed_author
from utils.setup import db_servers

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
        "emoji": "<a:icon_reddit:939539009833668619>",
    },
    "Pixel Art": {
        "description": "Useful tools to make pixel art.",
        "emoji": "<a:icon_pixelart:939537785658933350>",
    },
    "Pxls": {
        "description": "Most pxls related commands.",
        "emoji": "<a:icon_pxls:939538707919306783> ",
    },
    "Pxls Template": {
        "description": "Commands to handle pxls templates.",
        "emoji": "<a:icon_template:939539139567681578> ",
    },
    "Other": {
        "description": None,
        "emoji": "<a:icon_other:939539309873209426>",
    },
}

HOME_EMOJI = "<a:icon_home:939542127472439338>"


async def autocomplete_commands(inter: disnake.AppCmdInter, user_input: str):
    commands = []
    for cmd in inter.bot.all_slash_commands.values():
        commands.append(cmd.name)
        for child in cmd.children.values():
            commands.append(child.qualified_name)
    categories = list(get_slash_mapping(inter.bot).keys())
    commands += categories
    return [cmd for cmd in commands if user_input.lower() in cmd.lower()][:25]


class HelpButton(disnake.ui.Button):
    def __init__(self, category_name, is_slash) -> None:
        self.category = category_name
        self.is_slash = is_slash
        if self.category == "Home":
            label = ""
            style = disnake.ButtonStyle.blurple
            emoji = HOME_EMOJI
        else:
            label = self.category
            style = disnake.ButtonStyle.gray
            category_infos = CATEGORIES[self.category]
            emoji = category_infos["emoji"]

        custom_id = "help:{}:{}".format(
            self.category,
            "slash" if self.is_slash else "",
        )
        super().__init__(style=style, emoji=emoji, label=label, custom_id=custom_id)


class HelpView(disnake.ui.View):
    def __init__(self, categories, current_category, is_slash):
        super().__init__(timeout=None)
        self.categories = categories
        self.current_category = current_category
        self.is_slash = is_slash
        self.update_buttons()

    def update_buttons(self):
        for c in self.children[:]:
            self.remove_item(c)
        if self.current_category:
            self.add_item(HelpButton("Home", self.is_slash))

        for category in self.categories:
            if category != self.current_category and category != "Other":
                self.add_item(HelpButton(category, self.is_slash))

        if "Other" in self.categories and self.current_category != "Other":
            self.add_item(HelpButton("Other", self.is_slash))


class Help(commands.Cog):
    """A cog with all the help commands to get information about the other commands."""

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    async def send_home_help(self, ctx, author, is_slash):
        """Called when >help or /help is used."""
        if is_slash:
            categories = get_slash_mapping(self.bot)
            prefix = "/"
        else:
            categories = get_bot_mapping(self.bot)
            prefix = await db_servers.get_prefix(self.bot, ctx)

        # create the embed header
        home_emoji = HOME_EMOJI
        emb = disnake.Embed(title=f"{home_emoji} Command help", color=EMBED_COLOR)
        emb.description = (
            f"Use `{prefix}help [command]` to see more information about a command.\n"
            + f"Use `{prefix}help [category]` to see more information about a category.\n"
        )
        emb.set_author(name=ctx.me, icon_url=ctx.me.display_avatar)
        emb.set_footer(text=f"Requested by {author}", icon_url=author.display_avatar)

        # add a field and button per category
        for category, category_commands in categories.items():
            if category != "Other":
                category_infos = CATEGORIES.get(category) or CATEGORIES[None]
                category_emoji = category_infos["emoji"]
                commands_text = ""
                for c in category_commands:
                    if isinstance(c, disnake.ApplicationCommand):
                        commands_text += f"`{c.qualified_name}` "
                    else:
                        commands_text += f"`{c.name}` "
                emb.add_field(
                    name=f"{category_emoji} {category}",
                    value=commands_text,
                    inline=False,
                )
        # add the "Other" category after the loop so it's always last
        if "Other" in categories:
            commands = categories["Other"]
            category_infos = CATEGORIES.get("Other") or CATEGORIES[None]
            category_emoji = category_infos["emoji"]
            commands_text = ""
            for c in commands:
                if isinstance(c, disnake.ApplicationCommand):
                    commands_text += f"`{c.qualified_name}` "
                else:
                    commands_text += f"`{c.name}` "
            emb.add_field(
                name=f"{category_emoji} Other", value=commands_text, inline=False
            )
        view = HelpView(categories, None, is_slash)

        if isinstance(ctx, disnake.MessageInteraction):
            await ctx.edit_original_message(embed=emb, view=view)
        else:
            await ctx.send(embed=emb, view=view)

    async def send_category_help(
        self, ctx, category_name, author, is_slash, send_buttons=True
    ):
        """called when >help <category> or /help <category> is used."""
        if category_name == "Home":
            return await self.send_home_help(ctx, author, is_slash)

        if is_slash:
            categories = get_slash_mapping(self.bot)
            prefix = "/"
        else:
            categories = get_bot_mapping(self.bot)
            prefix = await db_servers.get_prefix(self.bot, ctx)

        category_infos = CATEGORIES[category_name]
        commands = categories[category_name]
        category_description = category_infos["description"]
        category_emoji = category_infos["emoji"]
        commands_text = ""
        for command in commands:
            commands_text += "• `{}{}`: {}\n".format(
                prefix,
                command.qualified_name,
                command.description or "N/A",
            )

        emb = disnake.Embed(
            title=f"{category_emoji} {category_name} Category",
            color=EMBED_COLOR,
            description=f"Use `{prefix}help [command]` to see more information about a command.\n",
        )
        if category_description:
            emb.add_field(
                name="**Description**", value=category_description, inline=False
            )
        emb.add_field(name="**Commands**", value=commands_text, inline=False)
        emb.set_author(name=ctx.me, icon_url=ctx.me.display_avatar)
        emb.set_footer(text=f"Requested by {author}", icon_url=author.display_avatar)

        if send_buttons:
            view = HelpView(categories, category_name, is_slash)
        elif isinstance(ctx, disnake.AppCmdInter):
            view = disnake.utils.MISSING
        else:
            view = None

        if isinstance(ctx, disnake.MessageInteraction):
            await ctx.edit_original_message(embed=emb, view=view)
        else:
            await ctx.send(embed=emb, view=view)

    async def send_command_help(self, ctx, command, is_slash):
        """called when >help <command> or /help <command> is used."""
        if is_slash:
            prefix = "/"
            command_name = command.qualified_name
            command_usage = get_slash_command_usage(command)
            command_params = get_slash_command_parameters(command)
            description = command.body.description
        else:
            prefix = ctx.prefix
            command_name = command.qualified_name
            command_usage = command.usage
            command_params = command.help
            description = command.description
        prefix = "/" if is_slash else ctx.prefix
        emb = disnake.Embed(title=f"**Command {command_name}**", color=EMBED_COLOR)
        emb.set_author(name=ctx.me, icon_url=ctx.me.display_avatar)
        emb.add_field(
            name="Usage:",
            value=f"`{prefix}{command_name}{(' ' + command_usage) if command_usage else ''}`",
            inline=False,
        )
        emb.add_field(name="Description:", value=description or "N/A", inline=False)
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
        emb = disnake.Embed(title=f"**Command {group.name}**", color=EMBED_COLOR)
        emb.set_author(name=ctx.me, icon_url=ctx.me.display_avatar)
        emb.add_field(
            name="Description: ", value=group.description or "N/A", inline=False
        )
        emb.add_field(
            name="Usage:",
            value=f"`{prefix}{group.name}{(' ' + group.usage) if group.usage else ''}`",
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
                commands_value += "• `{}{} {}`: {}\n".format(
                    prefix,
                    command.qualified_name,
                    command.usage or "",
                    command.description or "N/A",
                )
            emb.add_field(name="Sub-commands: ", value=commands_value, inline=False)

        await ctx.send(embed=emb)

    @commands.command(name="help", description="Show all the commands.")
    async def help(self, ctx, *, command_name=None):
        return await self.handle_help(ctx, command_name, is_slash=False)

    @commands.slash_command(name="help")
    async def _help(
        self,
        inter: disnake.AppCmdInter,
        command_name: str = commands.Param(
            default=None, name="command-or-category", autocomplete=autocomplete_commands
        ),
    ):
        """Show all the slash commands.

        Parameters
        ----------
        command_name: The name of the command or category you want more information about."""
        await self.handle_help(inter, command_name, is_slash=True)

    async def handle_help(self, ctx, command_name, is_slash):
        # show all the commands if no command is given
        if command_name is None:
            return await self.send_home_help(ctx, ctx.author, is_slash)
        # check if it's a category
        elif (is_slash and command_name.title() in get_slash_mapping(self.bot)) or (
            not (is_slash) and command_name.title() in get_bot_mapping(self.bot)
        ):
            return await self.send_category_help(
                ctx, command_name.title(), ctx.author, is_slash, send_buttons=False
            )
        # check if it's a command
        else:
            command_name = command_name.lower()
            keys = command_name.split(" ")
            if is_slash:
                cmd = self.bot.all_slash_commands.get(keys[0])
            else:
                cmd = self.bot.all_commands.get(keys[0])
            if cmd is None:
                return await ctx.send(
                    f":x: No command or category named `{command_name}` found."
                )
            # check if the command is a sub-command
            for key in keys[1:]:
                try:
                    if is_slash:
                        found = cmd.children.get(key)
                    else:
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

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        """Handle what to do when a button a pressed on the help command."""
        custom_id = inter.component.custom_id
        parsed_id = custom_id.split(":")

        # check that the button was a help button
        if not parsed_id or parsed_id[0] != "help":
            return

        # check if the help command was a slash or prefix
        is_slash = parsed_id[-1] == "slash"
        category_name = parsed_id[1]

        # check on the author
        command_author = await get_embed_author(inter)
        if command_author != inter.author or command_author is None:
            emb = disnake.Embed(title="This isn't your command!", color=0xFF3621)
            emb.description = (
                "Use the help command yourself to interact with the buttons."
            )
            return await inter.send(embed=emb, ephemeral=True)

        # handle the button
        await inter.response.defer(with_message=False)  # maybe to delete?
        if category_name == "Home":
            await self.send_home_help(inter, command_author, is_slash)
        else:
            await self.send_category_help(
                inter, category_name, command_author, is_slash
            )


def setup(bot: commands.Bot):
    bot.add_cog(Help(bot))


def get_bot_mapping(bot: commands.Bot):
    """Get all the prefix commands groupped by category."""
    categories = {}
    for command in bot.commands:
        if command and not command.hidden and command.enabled:
            category_name = get_cog_category(command.cog)
            # categories are organized by cog folders
            try:
                categories[category_name].append(command)
            except KeyError:
                categories[category_name] = [command]
    return categories


def get_slash_mapping(bot: commands.Bot):
    """Get all the prefix commands groupped by category."""
    categories = {}
    for command in bot.slash_commands:
        if command:
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
    category_name = (
        cog_dir[0].replace("_", " ").title() if len(cog_dir) > 0 else "Other"
    )
    return category_name


def fullname(o):
    """Get the full name of a class/object."""
    klass = o.__class__
    module = klass.__module__
    if module == "builtins":
        return klass.__qualname__  # avoid outputs like 'builtins.str'
    return module + "." + klass.__qualname__


def get_slash_command_usage(slash_command: commands.InvokableSlashCommand):
    """Get all the slash command options as a string."""
    res_options = []
    sub_commands = []
    for o in slash_command.body.options:
        if o.type.value in (1, 2):
            sub_commands.append(o.name)
            continue
        if o.choices:
            o_choices = "|".join([c.name for c in o.choices])
        else:
            o_type = TYPES[o.type.value]
            o_choices = o_type

        option = f"{o.name}:{o_choices}"
        if o.required:
            res_options.append(f"<{option}>")
        else:
            res_options.append(f"[{option}]")
    if sub_commands:
        return f"<{'|'.join(sub_commands)}>"
    else:
        return " ".join(res_options)


def get_slash_command_parameters(slash_command: commands.InvokableSlashCommand):
    """Get all the slash command parameters as a string."""
    params = []
    for o in slash_command.body.options:
        if o.type.value in (1, 2):
            option = f"/{slash_command.name} {o.name}"
        else:
            if o.choices:
                o_choices = "|".join([c.name for c in o.choices])
            else:
                o_type = TYPES[o.type.value]
                o_choices = o_type

            option = f"{o.name}:{o_choices}"
            if o.required:
                option = f"<{option}>"
            else:
                option = f"[{option}]"
        params.append(f"- `{option}`: {o.description or 'N/A'}")
    return "\n".join(params)
