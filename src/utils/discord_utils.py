from io import BytesIO
import discord
from PIL import Image
from discord.ext import commands
from utils.utils import get_content
import re

STATUS_EMOJIS = {
    "bot": "<a:status_bot:878677107042025552>",
    "fast": "<:status_fast:878642193861079060>",
    "online": "<:status_online:878641779010842655>",
    "idle": "<:status_idle:878641855619809280>",
    "offline": "<:status_offline:878642079914410004>",
    "inactive": "<a:status_inactive:878675014726086706>",
}


def format_table(table, column_names, alignments=None, name=None):
    """Format the leaderboard in a string to be printed
    - :param table: a 2D array to format
    - :param column_names: a list of column names, must be the same lengh as the table rows
    - :alignments: a list of alignments
        - '^': centered
        - '<': aligned on the left
        - '>': aligned on the right
    - :name: add a '+' in front of of the row containing 'name' in the 2nd column"""
    if not table:
        return
    if len(table[0]) != len(column_names):
        raise ValueError("The number of column in table and column_names don't match.")
    if alignments and len(table[0]) != len(alignments):
        raise ValueError("The number of column in table and alignments don't match.")

    # find the longest columns
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
        if name:
            str_table += (("+ " if row[1] == name else "  ") + row_format.format(*row) + "\n")
        else:
            str_table += " " + row_format.format(*row) + "\n"

    return str_table


def format_number(num):
    """Format a number in a string.
    >>> format_number(1234567) -> '1 234 567'
    >>> format_number(1234.56789) -> '1 234.56' # round with 2 decimals
    >>> format_number(None) -> '???'
    >>> format_number('not a number') -> 'not a number' """
    if isinstance(num, int):
        return f"{int(num):,}".replace(",", " ")  # convert to string
    elif isinstance(num, float):
        return f"{round(float(num),2):,}".replace(",", " ")  # convert to string
    elif num is None:
        return "???"
    else:
        return str(num)


EMOJI_REGEX = r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>"
IMAGE_URL_REGEX = r"(?:http\:|https\:)?\/\/.*\.(?:png|jpg|gif)"


class ImageNotFoundError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


async def get_image_from_message(ctx, url=None, search_last_messages=True, accept_emojis=True):
    """Get an image from a discord Context or check on images among the 100
    last messages sent in the channel. Return a byte image and the image url"""
    message_limit = 100
    try:
        # try to get the image from the initial message
        return await get_image(ctx.message, url, accept_emojis)
    except ImageNotFoundError as e:
        # if no image was found in the message we check for images in the last
        # 100 messages sent in the channel
        if search_last_messages:
            async for message in ctx.channel.history(limit=message_limit):
                try:
                    return await get_image(message, accept_emojis=False)
                except Exception:
                    pass
        # no image was found in the last 100 images
        raise ValueError(e)

    except ValueError as e:
        # if an image was found but an error occured, we raise it
        raise ValueError(e)


async def get_image(message: discord.Message, url=None, accept_emojis=True):
    """Get an image from a discord message,
    raise ValueError if the URL isn't valid
    return a byte image and the image url"""

    # check the attachements
    if message and len(message.attachments) > 0:
        for a in message.attachments:
            content_type = a.content_type
            if content_type is not None and "image" in content_type:
                url = a.url
                break
        if url is None:
            raise ValueError("Invalid file type. Only images are supported.")

    # check the embeds
    elif message and len(message.embeds) > 0:
        for e in message.embeds:
            if e.image:
                url = message.embeds[0].image.url
                break
            elif e.type == "image" and e.url:
                url = e.url

    # check the message content
    elif url is not None or (message and message.content is not None):
        content = url or message.content
        # try to find a image URL in the message content
        urls = re.findall(IMAGE_URL_REGEX, content)
        if len(urls) > 0:
            url = urls[0]
        # try to find an emoji if no image URL found
        elif accept_emojis:
            results = re.findall(EMOJI_REGEX, content)
            if len(results) != 0:
                emoji_id = results[0][2]
                is_animated = results[0][0] == "a"
                url = "https://cdn.discordapp.com/emojis/{}.{}".format(
                    emoji_id, "gif" if is_animated else "png"
                )

    if url is None:
        raise ImageNotFoundError("No image or url found.")

    # getting the image from url
    try:
        image_bytes = await get_content(url, "image")
    except Exception as e:
        raise ValueError(e)
    return image_bytes, url


def image_to_file(image: Image.Image, filename: str, embed: discord.Embed = None) -> discord.File:
    """Convert a pillow Image to a discord File
    attach the file to a discord embed if one is given"""

    with BytesIO() as image_binary:
        image.save(image_binary, "PNG")
        image_binary.seek(0)
        image = discord.File(image_binary, filename=filename)
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

            if found := discord.utils.find(check, ctx.guild.members):
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

            if found := discord.utils.find(check, ctx.bot.users):
                return found
            raise commands.UserNotFound(argument)
