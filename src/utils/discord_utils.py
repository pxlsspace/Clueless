from io import BytesIO
import discord
from PIL import Image
from discord.ext import commands
from discord.ext.commands.core import command
from utils.utils import get_content
import re

def format_table(table,column_names,alignments=None,name=None):
    ''' Format the leaderboard in a string to be printed
    - :param table: a 2D array to format
    - :param column_names: a list of column names, must be the same lengh as the table rows
    - :alignments: a list of alignments
        - '^': centered
        - '<': aligned on the left
        - '>': aligned on the right
    - :name: add a '+' in front of of the row containing 'name' in the 2nd column'''
    if not table:
        return
    if len(table[0]) != len(column_names):
        raise ValueError("The number of column in table and column_names don't match.")
    if alignments and len(table[0]) != len(alignments):
        raise ValueError("The number of column in table and alignments don't match.")

    # find the longest columns
    table.insert(0,column_names)
    longest_cols = [
        (max([len(str(row[i])) for row in table]))
        for i in range(len(table[0]))]

    # format the header
    LINE = "-"*(sum(longest_cols) + len(table[0]*3))
    if alignments:
        row_format = " | ".join([f"{{:{alignments[i]}" + str(longest_col) + "}" for i,longest_col in enumerate(longest_cols)])
        title_format = row_format
    else:
        title_format = " | ".join(["{:^" + str(longest_col) + "}" for longest_col in longest_cols])

        row_format = " | ".join(["{:>" + str(longest_col) + "}" for longest_col in longest_cols])


    str_table = f'{LINE}\n'
    str_table += "  " if name else " " 
    str_table += f'{title_format.format(*table[0])}\n{LINE}\n'

    # format the body
    for row in table[1:]:
        if name:
            str_table += ("+ " if row[1] == name else "  ") + row_format.format(*row) + "\n"
        else:
            str_table += " " + row_format.format(*row) + "\n"

    return str_table

def format_number(num):
    ''' Format a number in a string.
    >>> format_number(1234567) -> '1 234 567'
    >>> format_number(1234.56789) -> '1 234.56' # round with 2 decimals
    >>> format_number(None) -> '???' 
    >>> format_number('not a number') -> 'not a number' '''
    if isinstance(num,int):
        return f'{int(num):,}'.replace(","," ") # convert to string
    elif isinstance(num,float):
        return f'{round(float(num),2):,}'.replace(","," ") # convert to string
    elif num == None:
        return '???'
    else:
        return str(num)

EMOJI_REGEX = r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>"

async def get_image_from_message(ctx,url=None):
    """ get an image from a discord context/message,
    raise ValueError if the URL isn't valid 
    return a byte image and the image url """
    # if no url in the command, we check the attachments
    if url == None:
        if len(ctx.message.attachments) == 0:
            raise ValueError("No image or url found.")    
        if not "image" in ctx.message.attachments[0].content_type:
            raise ValueError("Invalid file type. Only images are supported.")

        url = ctx.message.attachments[0].url
    else:
        # check if it's an emoji
        results = re.findall(EMOJI_REGEX,url)
        if len(results) != 0:
            emoji_id = results[0][2]
            is_animated = results[0][0] == 'a'
            url = "https://cdn.discordapp.com/emojis/{}.{}".format(emoji_id,'gif' if is_animated else 'png')

    # getting the image from url
    try:
        image_bytes = await get_content(url,'image')
    except Exception as e:
        raise ValueError (e)

    return image_bytes, url

def image_to_file(image:Image.Image,filename:str,embed:discord.Embed=None) -> discord.File:
    """ Convert a pillow Image to a discord File
    attach the file to a discord embed if one is given """

    with BytesIO() as image_binary:
        image.save(image_binary, 'PNG')
        image_binary.seek(0)
        image = discord.File(image_binary, filename=filename)
        if embed:
            embed.set_image(url=f'attachment://{filename}')
        return image

async def number_emoji(ctx):
    emojis = await ctx.guild.fetch_emojis()
    nb_static = 0
    nb_anim = 0
    for e in emojis:
        if e.animated == True:
            nb_anim += 1
        else:
            nb_static += 1
    return nb_static, nb_anim

def format_emoji(emoji):
    '''formats a discord emoji into a string'''
    res ="<{1}:{0.name}:{0.id}>".format(emoji, "a" if emoji.animated else "")
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
                    member.name.lower() == argument.lower() or
                    member.display_name.lower() == argument.lower() or
                    str(member).lower() == argument.lower() or
                    str(member.id) == argument
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
                    user.name.lower() == argument.lower() or
                    str(user).lower() == argument.lower() or
                    str(user.id) == argument
                )
            if found := discord.utils.find(check, ctx.bot.users):
                return found
            raise commands.UserNotFound(argument)
