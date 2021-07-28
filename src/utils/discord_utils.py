from io import BytesIO
import discord
import PIL
from utils.utils import get_content

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
    ''' format a number in a string: 1234567 -> 1 234 567'''
    return f'{int(num):,}'.replace(","," ") # convert to string


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

    # getting the image from url
    try:
        image_bytes = await get_content(url,'image')
    except Exception as e:
        raise ValueError (e)

    return image_bytes, url

def image_to_file(image:PIL.Image,filename:str,embed:discord.Embed=None) -> discord.File:
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
