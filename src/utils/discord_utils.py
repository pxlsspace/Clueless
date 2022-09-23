import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO

import disnake
from disnake import ButtonStyle
from disnake.ext import commands
from PIL import Image

from main import tracked_templates
from utils.image import PALETTES
from utils.pxls.template_manager import get_template_from_url, parse_template
from utils.setup import db_canvas, db_stats, stats
from utils.utils import get_content, in_executor

STATUS_EMOJIS = {
    "bot": "<a:status_botting:955632660653408266>",
    "fast": "<:status_fast:955632659739078747>",
    "online": "<:status_online:955632659810381864>",
    "idle": "<:status_idle:955632660238204950>",
    "offline": "<:status_offline:955632659952979998>",
    "inactive": "<:status_inactive:955632659743248434>",
}


def format_table(table, column_names, alignments=None, name=None, autoformat=False):
    """Format the leaderboard in a string to be printed
    - :param table: a 2D array to format
    - :param column_names: a list of column names, must be the same lengh as the table rows
    - :alignments: a list of alignments
        - '^': centered
        - '<': aligned on the left
        - '>': aligned on the right
    - :name: add a '+' in front of of the row containing 'name' in the 2nd column
    - :autoformat: format the text with format_number automatically
    """

    if not table:
        return
    if len(table[0]) != len(column_names):
        raise ValueError("The number of column in table and column_names don't match.")
    if alignments and len(table[0]) != len(alignments):
        raise ValueError("The number of column in table and alignments don't match.")

    if autoformat:
        table = [[format_number(c) for c in row] for row in table]

    # find the longest columns
    table = table.copy()
    table.insert(0, column_names)
    longest_cols = [
        (max([len(str(row[i])) for row in table])) for i in range(len(table[0]))
    ]

    # format the header
    LINE = "-" * (sum(longest_cols) + len(table[0] * 3))
    if alignments:
        row_format = " | ".join(
            [
                f"{{:{alignments[i]}" + str(longest_col) + "}"
                for i, longest_col in enumerate(longest_cols)
            ]
        )
        title_format = row_format
    else:
        title_format = " | ".join(
            ["{:^" + str(longest_col) + "}" for longest_col in longest_cols]
        )

        row_format = " | ".join(
            ["{:>" + str(longest_col) + "}" for longest_col in longest_cols]
        )

    str_table = f"{LINE}\n"
    str_table += "  " if name else " "
    str_table += f"{title_format.format(*table[0])}\n{LINE}\n"

    # format the body
    for row in table[1:]:
        # replace None values with an empty string
        row = ["" if r is None else str(r) for r in row]
        if name:
            str_table += (
                ("+ " if row[1] == name else "  ") + row_format.format(*row) + "\n"
            )
        else:
            str_table += " " + row_format.format(*row) + "\n"

    return str_table


def format_number(num):
    """Format a number in a string.
    >>> format_number(1234567) -> '1 234 567'
    >>> format_number(1234.56789) -> '1 234.56' # round with 2 decimals
    >>> format_number(None) -> '???'
    >>> format_number('not a number') -> 'not a number'"""
    if isinstance(num, int):
        return f"{int(num):,}".replace(",", " ")  # convert to string
    elif isinstance(num, float):
        return f"{round(float(num),2):,}".replace(",", " ")  # convert to string
    elif num is None:
        return "???"
    else:
        return str(num)


EMOJI_REGEX = r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>"
IMAGE_URL_REGEX = r"(?:http\:|https\:)?\/\/.*\.(?:png|jpg|jpeg|gif|webp)"
URL_REGEX = (
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


class ImageNotFoundError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


async def get_image_from_message(
    ctx,
    url=None,
    *,
    return_type="image_RGBA",
    search_last_messages=True,
    accept_emojis=True,
    accept_templates=True,
):
    """Get an image from a discord Context or check on images among the 100
    last messages sent in the channel. Return bytes or PIL.Image image and the image url"""
    assert return_type and return_type in ["image_RGBA", "image", "bytes"]
    message_limit = 100
    initial_message = None
    if isinstance(ctx, commands.Context):
        initial_message = ctx.message
    try:
        # try to get the image from the initial message
        return await get_image(
            initial_message,
            url,
            return_type,
            accept_emojis,
            accept_templates,
            accept_embeds=False,
        )
    except ImageNotFoundError as e:
        # if the message is a reply, we try to find an image in the replied message
        ref = initial_message.reference if initial_message else None
        if ref and isinstance(ref.resolved, disnake.Message):
            reply_message = ref.resolved
            try:
                return await get_image(
                    reply_message,
                    url=None,
                    return_type=return_type,
                    accept_emojis=False,
                    accept_templates=False,
                    accept_embeds=True,
                )
            except Exception:
                pass

        # if no image was found in the message we check for images in the last
        # 100 messages sent in the channel
        if search_last_messages:
            async for message in ctx.channel.history(limit=message_limit):
                if message != initial_message:
                    try:
                        return await get_image(
                            message,
                            url=None,
                            return_type=return_type,
                            accept_emojis=False,
                            accept_templates=False,
                            accept_embeds=True,
                        )
                    except Exception:
                        pass
        # no image was found in the last 100 images
        raise ValueError(e)

    except ValueError as e:
        # if an image was found but an error occurred, we raise it
        raise ValueError(e)


async def get_image(
    message: disnake.Message,
    url=None,
    return_type="image_RGBA",
    accept_emojis=True,
    accept_templates=True,
    accept_embeds=True,
):
    """Get an image from a discord message,
    raise ValueError if the URL isn't valid
    return a byte image and the image url"""
    res_image = None
    # check the attachments
    if message and len(message.attachments) > 0:
        for a in message.attachments:
            content_type = a.content_type
            if content_type is not None and "image" in content_type:
                url = a.url
                break
        if url is None:
            raise ValueError("Invalid file type. Only images are supported.")

    # check the embeds
    elif message and len(message.embeds) > 0 and accept_embeds:
        for e in message.embeds:
            if e.image:
                url = get_image_url(message.embeds[0].image)
                break
            elif e.type == "image" and e.url:
                url = get_image_url(e)

    # check the message content
    elif url is not None:
        url_dict = get_url(url, accept_emojis, accept_templates)
        if url_dict is not None:
            if url_dict["type"] == "template":
                temp_url = url_dict["url"]
                temp = await get_template_from_url(temp_url)
                temp_image = Image.fromarray(temp.get_array())
                url = temp.stylized_url  # this isn't really the image URL but oh well ..
                if return_type == "bytes":
                    # convert to bytes
                    temp_bytes = BytesIO()
                    temp_image.save(temp_bytes, format="PNG")
                    res_image = temp_bytes.getvalue()
                else:
                    res_image = temp_image
            else:
                url = url_dict["url"]
    if url is None:
        raise ImageNotFoundError("No image or url found.")

    # download the image from url
    if not res_image:
        try:
            res_image = await get_content(url, "image")
        except Exception as e:
            raise ValueError(e)
        if return_type in ["image", "image_RGBA"]:
            res_image = Image.open(BytesIO(res_image))
            if return_type == "image_RGBA":
                res_image = res_image.convert("RGBA")
    return res_image, url


def get_url(content, accept_emojis=True, accept_templates=True):
    """Get the URL from a content that can be:
    - a string URL
    - a custom emoji
    - a pxls template

    Return a dictionary like:
    {url: <url>, type: <type>}"""

    # template
    if accept_templates and parse_template(content):
        return dict(url=content, type="template")

    # image URL
    urls = re.findall(IMAGE_URL_REGEX, content)
    if len(urls) > 0:
        url = urls[0]
        return dict(url=url, type="image_url")

    # emoji
    elif accept_emojis:
        results = re.findall(EMOJI_REGEX, content)
        if len(results) != 0:
            emoji_id = results[0][2]
            is_animated = results[0][0] == "a"
            url = "https://media.discordapp.net/emojis/{}.{}".format(
                emoji_id, "gif" if is_animated else "png"
            )
            return dict(url=url, type="emoji")

    return None


def get_image_url(image) -> str:
    if hasattr(image, "proxy_url") and image.proxy_url:
        return image.proxy_url
    else:
        return image.url


@in_executor()
def image_to_file(
    image: Image.Image, filename: str, embed: disnake.Embed = None
) -> disnake.File:
    """Convert a pillow Image to a discord File
    attach the file to a discord embed if one is given"""

    with BytesIO() as image_binary:
        image.save(image_binary, "PNG")
        image_binary.seek(0)
        image = disnake.File(image_binary, filename=filename)
        if embed:
            embed.set_image(url=f"attachment://{filename}")
        return image


async def number_emoji(ctx):
    emojis = await ctx.guild.fetch_emojis()
    nb_static = 0
    nb_anim = 0
    for e in emojis:
        if e.animated:
            nb_anim += 1
        else:
            nb_static += 1
    return nb_static, nb_anim


def format_emoji(emoji):
    """formats a discord emoji into a string"""
    res = "<{1}:{0.name}:{0.id}>".format(emoji, "a" if emoji.animated else "")
    return res


def get_urls_from_list(input_list: list = None):
    """Extract all the URLs from the input list and put them in an other list.

    Parameters
    ----------
    input_list (list): a list of string containing URLs
    image_url (bool): if set to true, only the image URLs will be parsed

    Return
    ------
    A tuple with 2 lists (tuple(list, list)):
        - the `input_list` without the URLs
        - a list with all the URLs found (can be images or templates)
    """
    not_url_list = []
    url_list = []
    # search for possible URLs in the input_list
    if input_list:
        input_list = list(input_list)
        for possible_url in input_list:
            url_dict = get_url(possible_url)
            if url_dict:
                url_list.append(url_dict["url"])
            else:
                not_url_list.append(possible_url)
    return (not_url_list, url_list)


class MemberConverter(commands.Converter):
    "Case insensitive commands.MemberConverter"

    async def convert(self, ctx, argument):
        """
        This will raise MemberNotFound if the member is not found.
        """
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.MemberNotFound:
            # Let's try a utils.find:
            def check(member):
                return (
                    member.name.lower() == argument.lower()
                    or member.display_name.lower() == argument.lower()
                    or str(member).lower() == argument.lower()
                    or str(member.id) == argument
                )

            if found := disnake.utils.find(check, ctx.guild.members):
                return found
            raise commands.MemberNotFound(argument)


class UserConverter(commands.Converter):
    "Case insensitive commands.UserConverter"

    async def convert(self, ctx, argument):
        """
        This will take into account members if a guild exists.
        Raises UserNotFound if the user is not found.
        """
        if ctx.guild:
            try:
                return await MemberConverter().convert(ctx, argument)
            except commands.MemberNotFound:
                pass

        try:
            return await commands.UserConverter().convert(ctx, argument)
        except commands.UserNotFound:

            def check(user):
                return (
                    user.name.lower() == argument.lower()
                    or str(user).lower() == argument.lower()
                    or str(user.id) == argument
                )

            if found := disnake.utils.find(check, ctx.bot.users):
                return found
            raise commands.UserNotFound(argument)


async def get_embed_author(inter: disnake.MessageInteraction) -> disnake.User:
    """Get the author User from an embed if it has "Requested by name#0000" in the footer,
    return ``None`` if not found."""
    embeds = inter.message.embeds
    if not embeds:
        return None
    try:
        found = re.findall(r"Requested by (.*)#([0-9]{4})", embeds[0].footer.text)
        if not found:
            return None
        name = found[0][0]
        discrim = found[0][1]
        predicate = lambda u: u.name == name and u.discriminator == discrim  # noqa: E731
        result = disnake.utils.find(predicate, inter.bot.users)
        return result
    except Exception:
        return None


# --- Injections --- #
@dataclass
class InterImage:
    """A data class to store image links from application commmands"""

    url: str


@commands.register_injection
async def get_image_from_inter(
    inter: disnake.CommandInteraction,
    image_link: str = commands.Param(name="image-link", default=None),
    image_file: disnake.Attachment = commands.Param(name="image-file", default=None),
) -> InterImage:
    """Get an image either from a link or attachment.

    Parameters
    ----------
    image_link: Can be an image URL/link or a custom emoji or template link.
    image_file: An image attachment.
    """
    if image_file:
        image_link = get_image_url(image_file)
    return InterImage(image_link)


# --- Autocompletes --- #
async def autocomplete_palette(inter: disnake.AppCmdInter, user_input: str):
    """Auto-complete with all the colors of the current palette"""
    palette = stats.get_palette()
    color_names = [c["name"] for c in palette]
    return [color for color in color_names if user_input.lower() in color.lower()][:25]


async def autocomplete_palette_with_none(inter: disnake.AppCmdInter, user_input: str):
    """Like autocomplete_palette() but with "none" as option."""
    palette = stats.get_palette()
    color_names = [c["name"] for c in palette] + ["none"]
    return [color for color in color_names if user_input.lower() in color.lower()][:25]


async def autocomplete_pxls_name(inter: disnake.AppCmdInter, user_input: str):
    """Auto-complete with all the pxls names in the database."""
    names = await db_stats.get_all_pxls_names()
    return [name for name in names if user_input.lower() in name.lower()][:25]


async def autocomplete_builtin_palettes(inter: disnake.AppCmdInter, user_input: str):
    """Auto-complete with all the built-in palettes and pxls colors."""
    palette = stats.get_palette()
    color_names = [c["name"] for c in palette] + ["none"]
    palette_names = [name.title() for name in [p["names"][0] for p in PALETTES]]
    res_list = palette_names + color_names
    return [color for color in res_list if user_input.lower() in color.lower()][:25]


async def autocomplete_templates(inter: disnake.AppCmdInter, user_input: str):
    """Get all the public template names."""
    template_names = [t.name for t in tracked_templates.get_all_public_templates()]
    template_names.append("@combo")
    return [
        temp_name
        for temp_name in template_names
        if user_input.lower() in temp_name.lower()
    ][:25]


async def autocomplete_user_templates(inter: disnake.AppCmdInter, user_input: str):
    """Get all the user-owned template names."""
    author_id = inter.author.id
    if author_id in tracked_templates.progress_admins:
        return await autocomplete_templates(inter, user_input)
    else:
        template_names = [
            t.name
            for t in tracked_templates.get_all_public_templates()
            if t.owner_id == inter.author.id
        ]
        return [
            temp_name
            for temp_name in template_names
            if user_input.lower() in temp_name.lower()
        ][:25]


async def autocomplete_log_canvases(inter: disnake.AppCmdInter, user_input: str):
    canvas_codes = await db_canvas.get_logs_canvases()
    return [c for c in canvas_codes if user_input.lower() in c.lower()][:25]


async def autocomplete_canvases(inter: disnake.AppCmdInter, user_input: str):
    canvas_codes = await db_canvas.get_all_canvases()
    return [c for c in canvas_codes if user_input.lower() in c.lower()][:25]


# --- Views --- #
class AuthorView(disnake.ui.View):
    """A view with an interaction check allowing only
    the command author to interact with the view"""

    def __init__(self, author: disnake.User, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.author = author

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.author != self.author:
            embed = disnake.Embed(
                title="This isn't your command!",
                description="You cannot interact with a command you did not call.",
                color=disnake.Color.red(),
            )
            await inter.send(ephemeral=True, embed=embed)
            return False
        return await super(AuthorView, self).interaction_check(inter)


class CooldownView(disnake.ui.View):
    """A view with a cooldown"""

    def __init__(self, rate, per, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cd = commands.CooldownMapping.from_cooldown(
            rate, per, lambda inter: inter.user
        )

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # check the command cooldown
        retry_after = self.cd.update_rate_limit(inter)
        if retry_after:
            # rate limited
            embed = disnake.Embed(
                title="You're doing this too quick!",
                description=f"You are on cooldown for this interaction, try again in **{round(retry_after,2)}s**.",
                color=disnake.Color.red(),
            )
            await inter.send(ephemeral=True, embed=embed)
            return False
        return await super(CooldownView, self).interaction_check(inter)


class Confirm(disnake.ui.View):
    """Simple View that gives a confirmation menu."""

    message: disnake.Message

    def __init__(self, author: disnake.User, timeout=180):
        super().__init__(timeout=timeout)
        self.value = None
        self.author = author

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.author != self.author:
            embed = disnake.Embed(
                title="This isn't your command!",
                description="You cannot interact with a command you did not call.",
                color=0xFF3621,
            )
            await inter.send(ephemeral=True, embed=embed)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children[:]:
            self.remove_item(c)
        # make sure to update the message with the new buttons
        await self.message.edit(view=self)

    # When the confirm button is pressed, set the inner value to `True`,
    # remove the buttons and stop the View from listening to more input.
    @disnake.ui.button(label="Confirm", style=disnake.ButtonStyle.green)
    async def confirm(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ):
        self.value = True
        await interaction.response.edit_message(view=None)
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @disnake.ui.button(label="Cancel", style=disnake.ButtonStyle.red)
    async def cancel(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ):
        self.value = False
        await interaction.response.edit_message(view=None)
        self.stop()


class PaginatorView(disnake.ui.View):
    """Defines a simple paginator of buttons for the embed."""

    def __init__(self, embeds: list[disnake.Embed], images: list[Image.Image] = []):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.images = images
        self.change_page(0)

        self.first_page.disabled = True
        self.prev_page.disabled = True
        # no buttons if there is only one page
        if len(embeds) <= 1:
            self.children = []

    @disnake.ui.button(emoji="<:arrowfirst:955585658615910451>", style=ButtonStyle.gray)
    async def first_page(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        self.change_page(0)
        embed = self.embeds[self.embed_count]
        files = await self.get_file(embed)

        self.first_page.disabled = True
        self.prev_page.disabled = True
        self.next_page.disabled = False
        self.last_page.disabled = False
        await inter.response.edit_message(embed=embed, files=files, view=self)

    @disnake.ui.button(emoji="<:arrowleft:955585658922102844>", style=ButtonStyle.gray)
    async def prev_page(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        self.change_page(self.embed_count - 1)
        embed = self.embeds[self.embed_count]
        files = await self.get_file(embed)

        self.next_page.disabled = False
        self.last_page.disabled = False
        if self.embed_count == 0:
            self.first_page.disabled = True
            self.prev_page.disabled = True
        await inter.response.edit_message(embed=embed, files=files, view=self)

    @disnake.ui.button(style=ButtonStyle.blurple, label="...")
    async def page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()

    @disnake.ui.button(emoji="<:arrowright:955585658863357972>", style=ButtonStyle.gray)
    async def next_page(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        self.change_page(self.embed_count + 1)
        embed = self.embeds[self.embed_count]
        files = await self.get_file(embed)

        self.first_page.disabled = False
        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
            self.last_page.disabled = True
        await inter.response.edit_message(embed=embed, files=files, view=self)

    @disnake.ui.button(emoji="<:arrowlast:955585658867572787>", style=ButtonStyle.gray)
    async def last_page(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        self.change_page(len(self.embeds) - 1)

        embed = self.embeds[self.embed_count]
        files = await self.get_file(embed)

        self.first_page.disabled = False
        self.prev_page.disabled = False
        self.next_page.disabled = True
        self.last_page.disabled = True
        await inter.response.edit_message(embed=embed, files=files, view=self)

    async def get_file(self, embed):
        if self.images:
            file = await image_to_file(
                self.images[self.embed_count], "progress.png", embed
            )
            files = [file]
        else:
            files = []
        return files

    async def update_embeds(
        self, inter: disnake.MessageInteraction, new_embeds, new_images=None
    ):
        self.embeds = new_embeds
        self.images = new_images

        self.change_page(0)
        embed = self.embeds[self.embed_count]
        files = await self.get_file(embed)

        self.first_page.disabled = True
        self.prev_page.disabled = True
        self.next_page.disabled = False
        self.last_page.disabled = False
        await inter.message.edit(embed=embed, files=files, view=self)

    def change_page(self, new_index):
        self.embed_count = new_index
        self.page.label = f"{self.embed_count+1}/{len(self.embeds)}"


class DropdownView(PaginatorView):
    """A view for a dropdown with a cooldown and user check"""

    message: disnake.Message

    def __init__(self, author, dropdown, embeds, images):
        self.author = author
        super().__init__(embeds, images)
        self.add_item(dropdown)
        self.cd = commands.CooldownMapping.from_cooldown(1, 1, lambda inter: inter.user)

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # check that the command author is the user who interracted
        if inter.author != self.author:
            embed = disnake.Embed(
                title="This isn't your command!",
                description="You cannot interact with a command you did not call.",
                color=0xFF3621,
            )
            await inter.send(ephemeral=True, embed=embed)
            return False
        # check the command cooldown
        retry_after = self.cd.update_rate_limit(inter)
        if retry_after:
            # rate limited
            embed = disnake.Embed(
                title="You're doing this too quick!",
                description=f"You are on cooldown for this interaction, try again in **{round(retry_after,2)}s**.",
                color=0xFF3621,
            )
            await inter.send(ephemeral=True, embed=embed)
            return False
        return True

    async def on_timeout(self):
        # remove the dropdown on timeout
        for c in self.children[:]:
            self.remove_item(c)
        await self.message.edit(view=self)


class MoreInfoView(AuthorView):
    """A view used to add:
    - a Link button that opens `url`
    - a "more Info" button that switches the view message between "embed" and "embed_expaneded"
    - a "speed graph`" buttons that runs the `speed function` on `template_name`
    - a "groupped speed graph`" buttons that runs the `speed function` on `template_name`
      with the groupy option to:
          - day if the tracking time > 2 days
          - hours if the tracking day is between 2 hours and 2 days
          - 5min if the tracking time is under 2 hours
    - a refresh button"""

    message: disnake.Message

    def __init__(
        self,
        author,
        embed,
        embed_expanded,
        url,
        speed_function,
        template_name,
        tracking_since,
        add_refresh=True,
        display=0,
        state=0,
    ) -> None:
        super().__init__(author=author, timeout=300)
        self.state = state  # 0: collapsed, 1: expanded
        self.embeds = [embed, embed_expanded]
        self.emojis = ["<:arrowdown:955585658787885077>", "<:arrowup:955585658758516797>"]
        self.speed_function = speed_function
        self.template_name = template_name
        self.tracking_since = tracking_since
        self.display = display
        self.add_refresh = add_refresh

        self.children.insert(0, disnake.ui.Button(label="Template", url=url))
        self.switch.emoji = self.emojis[self.state]
        if add_refresh:
            self.update_refresh_btn_id()
        else:
            self.remove_item(self.refresh_button)

    async def on_timeout(self) -> None:
        # disable all the buttons except the url and refresh ones
        if all([c.custom_id == self.children[1].custom_id for c in self.children[1:-1]]):
            self.stop()
            return
        for c in self.children[1:-1]:
            c.disabled = True
        if not self.add_refresh:
            self.refresh_button.disabled = True
        await self.message.edit(view=self)

    def update_refresh_btn_id(self):
        if self.add_refresh:
            self.refresh_button.custom_id = f"prog_refresh:{self.template_name},{self.display},{self.state},{self.author.id}"

    @disnake.ui.button(
        style=disnake.ButtonStyle.blurple,
        emoji="<:arrowdown:955585658787885077>",
    )
    async def switch(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.state = 1 - self.state
        emb = self.embeds[self.state]
        button.emoji = self.emojis[self.state]
        self.update_refresh_btn_id()
        await inter.response.edit_message(embed=emb, view=self)

    @disnake.ui.button(
        style=disnake.ButtonStyle.blurple,
        emoji="<:graph:955585658888544337>",
    )
    async def progress_speed(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if not await self.check_tracking_time(inter):
            return
        button.disabled = True
        await inter.message.edit(view=self)
        await inter.response.defer(with_message=True)
        await self.speed_function(inter, self.template_name)

    @disnake.ui.button(
        style=disnake.ButtonStyle.blurple,
        emoji="<:graph_bars:974811872471691314>",
    )
    async def progress_speed_grouped(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if not await self.check_tracking_time(inter):
            return
        tracking_time = datetime.utcnow() - self.tracking_since
        if tracking_time > timedelta(days=2):
            groupby = "day"
        elif tracking_time > timedelta(hours=2):
            groupby = "hour"
        else:
            groupby = "5min"
        button.disabled = True
        await inter.message.edit(view=self)
        await inter.response.defer(with_message=True)
        await self.speed_function(inter, self.template_name, groupby=groupby)

    @disnake.ui.button(
        style=disnake.ButtonStyle.green, emoji="<:refresh:976870681729962017>"
    )
    async def refresh_button(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        pass

    async def check_tracking_time(self, inter):
        if (
            self.tracking_since is None
            or datetime.utcnow() - self.tracking_since < timedelta(minutes=5)
        ):
            await inter.send(
                embed=disnake.Embed(
                    color=disnake.Color.red(),
                    description="Not enough data to make graphs yet, try again in ~5 minutes.",
                ),
                ephemeral=True,
            )
            return False
        return True


class AddTemplateView(AuthorView):
    """View with a template link and a "add to tracker" button that sends
    a modal for the template name and add it to the tracker."""

    message: disnake.Message

    def __init__(self, author: disnake.User, template_url: str, add_func):
        super().__init__(author)
        self.add_func = add_func
        self.template_url = template_url
        self.children.insert(
            0, disnake.ui.Button(label="Open Template", url=template_url)
        )

    async def on_timeout(self) -> None:
        # disable all the buttons except the url one
        for c in self.children[1:]:
            c.disabled = True
        await self.message.edit(view=self)

    @disnake.ui.button(label="+ Add To Tracker", style=disnake.ButtonStyle.blurple)
    async def add_to_tracker(
        self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction
    ):
        # send a modal
        modal_id = os.urandom(16).hex()
        await button_inter.response.send_modal(
            title="Add a template to the tracker.",
            custom_id=modal_id,
            components=[
                disnake.ui.TextInput(
                    label="Name",
                    placeholder="The name of the template.",
                    custom_id="name",
                    style=disnake.TextInputStyle.short,
                    min_length=2,
                    max_length=40,
                ),
            ],
        )

        try:
            # wait until the user submits the modal.
            modal_inter: disnake.ModalInteraction = await button_inter.bot.wait_for(
                "modal_submit",
                check=lambda i: i.custom_id == modal_id
                and i.author.id == button_inter.author.id,
                timeout=300,
            )
        except asyncio.TimeoutError:
            # The user didn't submit the modal in the specified period of time.
            # This is done since Discord doesn't dispatch any event for when a modal is closed/dismissed.
            return

        name = modal_inter.text_values["name"]
        await modal_inter.response.defer()

        if await self.add_func(modal_inter, name, self.template_url):
            button.disabled = True
            button.label = "✓ Added"
            self.stop()
            await button_inter.message.edit(view=self)


class ResizeButton(disnake.ui.Button):
    """Buttons for the resize view"""

    def __init__(self, amount, func):
        super().__init__(style=disnake.ButtonStyle.gray)
        self.func = func
        self.update_amount(amount)

    def update_amount(self, new_amount):
        self.amount = new_amount
        self.label = f"{'+' if new_amount > 0 else ''}{new_amount}"

    async def callback(self, inter: disnake.MessageInteraction):
        assert self.view is not None
        await inter.response.defer()
        view: ResizeView = self.view
        try:
            embed, file = await self.func(view.image_width + self.amount)
            view.image_width += self.amount

        except ValueError as e:
            await inter.send(f":x: {e}", ephemeral=True)
        else:
            await inter.message.edit(embed=embed, file=file, view=view)


class ResizeView(CooldownView, AuthorView):
    """View used with the resize command"""

    message: disnake.Message

    def __init__(self, author: disnake.User, image_width: int, func):
        super().__init__(rate=5, per=5, author=author)
        self.image_width = image_width
        self.func = func
        # True: buttons will increase the width, False: buttons will decrease it
        self.state = False
        amounts = [-1, -10, -50, -100]
        for amount in amounts:
            self.add_item(ResizeButton(amount, self.func))

    async def on_timeout(self):
        # remove the dropdown on timeout
        for c in self.children[:]:
            self.remove_item(c)
        await self.message.edit(view=self)

    @disnake.ui.button(label="+", style=disnake.ButtonStyle.blurple)
    async def plus_minus(self, button: disnake.Button, inter: disnake.MessageInteraction):
        """invert the buttons"""
        self.state = not self.state
        button.label = "-" if self.state else "+"
        for c in self.children[1:]:
            c.update_amount(-c.amount)
        await inter.response.edit_message(view=self)


class CreateTemplateView(disnake.ui.View):
    message: disnake.Message

    def __init__(self, ctx, template):
        super().__init__()
        self.template_image_url = None
        self.ctx = ctx
        self.template = template  # the template object

    async def on_timeout(self) -> None:
        # delete everything
        for c in self.children[:]:
            self.remove_item(c)
        await self.message.edit(view=self)

    @disnake.ui.button(label="Create Template (no style)", style=ButtonStyle.blurple)
    async def temp_no_style(self, btn: disnake.Button, inter: disnake.MessageInteraction):
        # No style: uses the previously sent image to generate the template fast
        await inter.response.defer()
        url = self.template.generate_url(self.template_image_url)
        await inter.send(
            embed=disnake.Embed(title="Template Link", color=0x66C5CC, description=url)
        )
        await self.on_timeout()
        self.stop()

    @disnake.ui.button(label="Create Template (custom)", style=ButtonStyle.blurple)
    async def temp_custom(self, btn: disnake.Button, inter: disnake.MessageInteraction):
        # Custom Template: invoke the template command from the template Cog which sends
        # the styled image and the template link
        await inter.response.defer(with_message=True)

        # disable the buttons so they're not clickable during the processing
        for c in self.children:
            c.disabled = True
        await inter.message.edit(view=self)

        if await self.ctx.bot.cogs.get("Template").template(
            inter,
            image_url=self.template_image_url,
            style_name="custom",
            glow=False,
            title=self.template.title,
            ox=self.template.ox,
            oy=self.template.oy,
            nocrop=True,
            matching="fast",
        ):
            # delete all the buttons
            await self.on_timeout()
            self.stop()
        else:
            # template creation failed: re-enable the buttons
            for c in self.children:
                c.disabled = False
            await inter.message.edit(view=self)


class UserinfoView(AuthorView):
    """A view for the /userinfo command that adds:
    - a Link button that opens `profile_url`
    - a "Speed" button that runs the `speed_function` on `username`
    - a "Speed by Canvas" button that runs the `speed_function` on `username` with the
    parameter groupby="canvas"
    """

    message: disnake.Message

    def __init__(
        self, author: disnake.User, profile_url, speed_function, username, canvas
    ):
        super().__init__(author, timeout=300)
        self.children.insert(0, disnake.ui.Button(label="Profile", url=profile_url))
        if not canvas:
            self.remove_item(self.children[1])
        self.username = username
        self.speed_function = speed_function
        self.username = username

    async def on_timeout(self) -> None:
        # disable all the buttons except the url one
        for c in self.children[1:]:
            c.disabled = True
        await self.message.edit(view=self)

    @disnake.ui.button(
        label="Speed",
        style=disnake.ButtonStyle.blurple,
        emoji="<:graph:955585658888544337>",
    )
    async def speed(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        button.disabled = True
        await inter.message.edit(view=self)
        await inter.response.defer(with_message=True)
        await self.speed_function(inter, self.username)

    @disnake.ui.button(
        label="Speed by Canvas",
        style=disnake.ButtonStyle.blurple,
        emoji="<:graph_bars:974811872471691314>",
    )
    async def speed_group_canvas(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        button.disabled = True
        await inter.message.edit(view=self)
        await inter.response.defer(with_message=True)
        await self.speed_function(inter, self.username, groupby="canvas")
