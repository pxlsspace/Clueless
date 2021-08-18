import discord
import numpy as np
from datetime import datetime
from discord.ext import commands
from PIL import Image

from utils.discord_utils import format_number, image_to_file
from utils.setup import stats, db_connection as db_conn
from utils.time_converter import format_datetime, td_format

class PxlsStats(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command(
        description = "Show some general pxls stats.",
        aliases = ["gstats","gs"])
    async def generalstats(self,ctx):
        async with ctx.typing():
            # getting the general stats from pxls.space/stats
            gen_stats = stats.get_general_stats()
            total_users = gen_stats["total_users"]
            total_factions = gen_stats["total_factions"]
            total_placed = gen_stats["total_pixels_placed"]
            active_users = gen_stats["users_active_this_canvas"]

            # calculate canvas stats
            board = await stats.fetch_board()
            virginmap = await stats.fetch_virginmap()
            placemap = await stats.fetch_placemap()
            total_amount = np.sum(board!=255)
            total_placeable = np.sum(placemap!=255)
            total_non_virgin = np.sum(virginmap==0)

            # get canvas info
            canvas_code = await stats.get_canvas_code()
            last_updated = stats.last_updated_to_date(stats.get_last_updated())
            # find the earliest datetime for the current canvas
            sql = "SELECT MIN(datetime),datetime FROM record WHERE canvas_code = ?"
            start_date = await db_conn.sql_select(sql,canvas_code)
            start_date = start_date[0]["datetime"]

            general_stats_text = "• Total Users: `{}`\n• Total Factions: `{}`".format(
                format_number(total_users),format_number(total_factions))

            canvas_stats_text = """
            • Total Pixels `{}`/`{}` (`{}%` placeable)\n• Total Placed: `{}`\n• Total Non-Virgin: `{}`\n• Percentage Non-Virgin:\n{} `{}%`""".format(
                format_number(int(total_placeable)),
                format_number(int(total_amount)),
                format_number(total_placeable/total_amount*100),
                format_number(total_placed),
                format_number(int(total_non_virgin)),
                make_progress_bar(total_non_virgin/total_placeable*100),
                format_number(total_non_virgin/total_placeable*100),
            )

            info_text = "• Canvas Code: `{}`\n• Start Date: {}\n• Time Elapsed: {}\n• Canvas Users: `{}`".format(
                canvas_code,
                format_datetime(start_date),
                td_format(datetime.utcnow()-start_date,hide_seconds=True),
                active_users
            )

            # create an embed with all the infos
            emb = discord.Embed(title="Pxls.space Stats",color=0x66c5cc)
            emb.add_field(name="**General Stats**",value=general_stats_text,inline=False)
            emb.add_field(name="**Canvas Info**",value=info_text,inline=False)
            emb.add_field(name="**Canvas Stats**",value=canvas_stats_text,inline=False)
            emb.add_field(name="\u200b",value="Last updated: "+format_datetime(last_updated),inline=False)

            # set the board image as thumbnail
            board_array = stats.palettize_array(board)
            board_img = Image.fromarray(board_array)
            f = image_to_file(board_img,"board.png")
            emb.set_thumbnail(url="attachment://board.png")

            await ctx.send(embed=emb,file=f)

    @commands.command(
    usage = "<username> [-c]",
    description = "Show the pixel count for a pxls user.",
    help = """- `<username>`: a pxls username
              - `[-c|-canvas]`: to see the canvas count.""")
    async def stats(self,ctx,name,option=None):

        if option == "-c" or option == "-canvas":
            number = stats.get_canvas_stat(name)
            text = "Canvas"
        else:
            number = stats.get_alltime_stat(name)
            text = "All-time"

        if not number:
            return await ctx.send ("❌ User not found.")
        else:
            msg = f'**{text} stats for {name}**: {number} pixels.'
            return await ctx.send(msg)

    @commands.command(description="Get the current pxls board.",usage = "[-virgin|-initial]")
    async def board(self,ctx,*options):
        async with ctx.typing():
            if "-virginmap" in options or "-virgin" in options:
                array = await stats.fetch_virginmap()
            elif "-initial" in options:
                array = await stats.fetch_initial_canvas()
                array = stats.palettize_array(array)
            else:
                array = stats.board_array
                array = stats.palettize_array(array)

            board_img = Image.fromarray(array)
            file = image_to_file(board_img,"board.png")
            await ctx.send(file=file)

def make_progress_bar(percentage,nb_char=20):
    full = "▓"
    empty = "░"
    res_bar = ""
    bar_idx = int((percentage/100)*nb_char)
    for i in range(nb_char):
        if i < bar_idx:
            res_bar += full
        else:
            res_bar += empty
    return res_bar

def setup(client):
    client.add_cog(PxlsStats(client))
