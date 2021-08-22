import discord
import numpy as np
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from PIL import Image

from utils.pxls.cooldown import get_best_possible
from utils.discord_utils import format_number, image_to_file,STATUS_EMOJIS
from utils.setup import stats, db_conn, db_users, db_stats
from utils.time_converter import format_datetime, round_minutes_down, td_format
from utils.arguments_parser import MyParser
from cogs.pixelart.color_breakdown import _colors
from cogs.pixelart.highlight import _highlight

class PxlsStats(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command(
        description = "Show some general pxls stats.",
        aliases = ["gstats","gs","canvasinfo"])
    async def generalstats(self,ctx):
        async with ctx.typing():
            # getting the general stats from pxls.space/stats
            gen_stats = stats.get_general_stats()
            total_users = gen_stats["total_users"]
            total_factions = gen_stats["total_factions"]
            total_placed = gen_stats["total_pixels_placed"]
            active_users = gen_stats["users_active_this_canvas"]

            # calculate canvas stats
            board = stats.board_array
            virginmap = stats.virginmap_array
            placemap = stats.placemap_array
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
            • Total Pixels `{}`/`{}` (`{}%` placeable)\n• Total Placed: `{}`\n• Total Non-Virgin: `{}`\n• Percentage Non-Virgin:\n**|**{}**|** `{}%`""".format(
                format_number(int(total_placeable)),
                format_number(int(total_amount)),
                format_number(total_placeable/total_amount*100),
                format_number(total_placed),
                format_number(int(total_non_virgin)),
                f"`{make_progress_bar(total_non_virgin/total_placeable*100)}`",
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
            emb.add_field(name="\u200b",value="Last updated: "+format_datetime(last_updated,"R"),inline=False)

            # set the board image as thumbnail
            board_array = stats.palettize_array(board)
            board_img = Image.fromarray(board_array)
            f = image_to_file(board_img,"board.png")
            emb.set_thumbnail(url="attachment://board.png")

            await ctx.send(embed=emb,file=f)

    @commands.command(
        aliases = ["uinfo","status"],
        usage = "<username>",
        description = "Show some informations about a pxls user.",
        help = f"""
        -`<username>`: a pxls username (will use your set username if set)\n
        **Status explanation:**
        {STATUS_EMOJIS["fast"]}`online (fast)`: the user is close to the best possible in the last 15 minutes
        {STATUS_EMOJIS["online"]}`online`: the user placed in the last 15 minutes
        {STATUS_EMOJIS["idle"]}`idle`: the user stopped placing 15/30 minutes ago
        {STATUS_EMOJIS["offline"]}`offline`: The user hasn't placed in the last 30 minutes
        {STATUS_EMOJIS["inactive"]}`inactive`: The user hasn't placed on the current canvas
        """)
    async def userinfo(self,ctx,name=None):
        "Show some informations about a pxls user."
        if name == None:
            # select the discord user's pxls username if it has one linked
            discord_user = await db_users.get_discord_user(ctx.author.id)
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id == None:
                return await ctx.send(f"❌ You need to specify a pxls username.")
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                user_id = pxls_user_id
        else:
            user_id = await db_users.get_pxls_user_id(name)
            if user_id == None:
                return await ctx.send ("❌ User not found.")
        
        async with ctx.typing():
            # get current pixels and leaderboard place
            last_leaderboard = await db_stats.get_last_leaderboard()
            user_row = None
            for row in last_leaderboard:
                if row["name"] == name:
                    user_row = row
                    break

            if user_row == None:
                # if the user isn't on the last leaderboard
                alltime_rank = canvas_rank = ">1000"
                alltime_count = canvas_count = None
                last_updated = "-"
            else:
                alltime_rank = user_row["alltime_rank"]
                if alltime_rank > 1000:
                    alltime_rank = ">1000"
                alltime_count = user_row["alltime_count"]

                canvas_rank = user_row["canvas_rank"]
                if canvas_rank > 1000:
                    canvas_rank = ">1000"
                canvas_count = user_row["canvas_count"]
                if canvas_count == 0:
                    canvas_rank = "N/A"

                last_updated = format_datetime(user_row["datetime"],'R')

            alltime_text = "• Rank: `{}`\n• Pixels: `{}`".format(alltime_rank,
                format_number(alltime_count))
            canvas_text = "• Rank: `{}`\n• Pixels: `{}`".format(canvas_rank,
                format_number(canvas_count))

            # get the recent activity stats
            time_intervals = [0.25,1,24,24*7] # in hours
            time_intervals.append(0.5)
            interval_names = ["15 min","hour","day","week"]
            record_id_list = []
            record_list = []
            now_time = datetime.now(timezone.utc)
            current_canvas_code = await stats.get_canvas_code()
            for time_interval in time_intervals:
                time = now_time - timedelta(hours=time_interval) - timedelta(minutes=1)
                time = round_minutes_down(time)
                record = await db_stats.find_record(time,current_canvas_code)
                record_id = record["record_id"]
                record_id_list.append(record_id)
                record_list.append(record)

            sql = """
                SELECT canvas_count, alltime_count, record_id
                FROM pxls_user_stat
                JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
                WHERE pxls_user_id = ?
                AND record_id IN ({})
                ORDER BY record_id
            """.format(", ".join(["?"]*len(record_id_list)))
            rows = await db_conn.sql_select(sql,(user_id,) + tuple(record_id_list))

            diff_list = []
            for id in record_id_list:
                diff = None
                for row in rows:
                    # calcluate the difference for each time if the value is not null
                    # and compare the canvas count if the alltime count is null
                    if row["record_id"] == id:
                        if alltime_count != None and row["alltime_count"] != None:
                            diff = alltime_count - row["alltime_count"]
                        elif canvas_count != None and row["canvas_count"] != None:
                            diff = canvas_count - row["canvas_count"]
                diff_list.append(diff)

            recent_activity = [f"• Last {interval_names[i]}: `{format_number(diff_list[i])}`" for i in range(len(diff_list)-1)]
            recent_activity_text = "\n".join(recent_activity) 
            recent_activity_text += f"\n\nLast updated: {last_updated}"

            # get the status
            last_15m = diff_list[0]
            last_30m = diff_list[-1]
            last_online_date = None

            if last_15m == None or last_30m == None:
                status = "???"
                status_emoji = ""
            else:
                # online
                if last_15m != 0:
                    # if the amount placed in the last 15m is at least 95% of the 
                    # best possible, the status is 'online (fast)'
                    dt2 = user_row["datetime"]
                    dt1 = record_list[0]["datetime"]
                    best_possible,average_cooldown = await get_best_possible(dt1,dt2)
                    fast_amount = int(best_possible * 0.95)

                    if last_15m > best_possible:
                        status = "online (botting)"
                        status_emoji = STATUS_EMOJIS["bot"]
                    elif last_15m >= fast_amount:
                        status = "online (fast)"
                        status_emoji = STATUS_EMOJIS["fast"]
                    else:
                        status = "online"
                        status_emoji = STATUS_EMOJIS["online"]
                # idle
                elif last_30m != 0:
                    status = "idle"
                    status_emoji = STATUS_EMOJIS["idle"]

                else:
                    # search for the last online time
                    sql = """
                        SELECT datetime, canvas_code, pxls_user_stat.record_id
                        FROM pxls_user_stat
                        JOIN record on record.record_id = pxls_user_stat.record_id
                        JOIN pxls_name on pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
                        WHERE pxls_user_id = ?
                        AND {} = ?
                        ORDER BY datetime
                        LIMIT 1""".format("alltime_count" if alltime_count else "canvas_count")

                    last_online = await db_conn.sql_select(sql,(user_id,alltime_count or canvas_count))
                    if len(last_online) > 0:
                        last_online_date = last_online[0]["datetime"]
                        if last_online[0]["record_id"] == 1:
                            last_online_date = "over " + format_datetime(last_online_date,'R')
                        else:
                            last_online_date = format_datetime(last_online_date,'R')

                    # inactive
                    if canvas_count == 0 or canvas_count == None:
                        status = "inactive"
                        status_emoji = STATUS_EMOJIS["inactive"]
                    # offline
                    else:
                        status = "offline"
                        status_emoji = STATUS_EMOJIS["offline"]

            # get the profile page
            profile_url = "https://pxls.space/profile/{}".format(name)

            description = f"**Status**: {status_emoji} `{status}`\n"
            if last_online_date != None:
                description += f"*(Last pixel: {last_online_date})*\n"

            description += f"[Profile page]({profile_url})"

            # create and send the embed
            emb = discord.Embed(title=f"User Info for `{name}`",color=0x66c5cc,
                description = description)
            emb.add_field(name="**Canvas stats**",value=canvas_text,inline=True)
            emb.add_field(name="**All-time stats**",value=alltime_text,inline=True)
            emb.add_field(name="**Recent activity**",value=recent_activity_text,inline=False)
            await ctx.send(embed=emb)

    @commands.command(description="Get the current pxls board.",usage = "[-virgin|-initial]")
    async def board(self,ctx,*options):
        async with ctx.typing():
            if "-virginmap" in options or "-virgin" in options:
                array = stats.virginmap_array
            elif "-initial" in options:
                array = await stats.fetch_initial_canvas()
                array = stats.palettize_array(array)
            else:
                array = stats.board_array
                array = stats.palettize_array(array)

            board_img = Image.fromarray(array)
            file = image_to_file(board_img,"board.png")
            await ctx.send(file=file)

    @commands.command(description="Show the canvas colors.",aliases=["cc"],usage = "[-placed|-p]")
    async def canvascolors(self,ctx,*options):
        """Show the canvas colors."""
        async with ctx.typing():
        # get the board with the placeable pixels only
            placeable_board = await stats.get_placable_board()

            if "-placed" in options or "-p" in options:
            # use the virgin map as a mask to get the board with placed pixels
                virgin_array = stats.virginmap_array
                placed_board = placeable_board.copy()
                placed_board[virgin_array != 0] = 255
                placed_board[virgin_array == 0] = placeable_board[virgin_array == 0]
                img = Image.fromarray(stats.palettize_array(placed_board))
                title = "Canvas colors breakdown (non-virgin pixels only)"
            else:
                img = Image.fromarray(stats.palettize_array(placeable_board))
                title = "Canvas color breakdown"

            await _colors(self.client,ctx,img,title)

    @commands.command(
        description="Highlight the selected colors on the canvas.",
        aliases = ["chl","canvashl"],
        usage="<colors> [-bgcolor|-bg <color>]",
        help = """\t- `<colors>`: list of pxls colors separated by a comma
            \t- `[-bgcolor|bg <color>]`: the color to display behind the\
             selected colors (`none` = transparent)""")
    async def canvashighlight(self,ctx,*args):
        " Highlight the selected colors on the canvas"
        # parse the arguemnts
        parser  = MyParser(add_help=False)
        parser.add_argument('colors', type=str, nargs='+')
        parser.add_argument('-bgcolor',"-bg",nargs="*", type=str,
            action='store', required=False)
        try:
            parsed_args= parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        async with ctx.typing():
            # get the board with the placeable pixels only
            canvas_array_idx = await stats.get_placable_board()
            canvas_array = stats.palettize_array(canvas_array_idx)
            await _highlight(ctx,canvas_array,parsed_args)

def make_progress_bar(percentage,nb_char=20):
    full = "​█"
    empty = " "
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
