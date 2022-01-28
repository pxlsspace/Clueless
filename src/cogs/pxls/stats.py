import discord
import numpy as np
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from PIL import Image, ImageEnhance
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from utils.pxls.cooldown import get_best_possible, get_cd
from utils.discord_utils import format_number, image_to_file, STATUS_EMOJIS
from utils.setup import stats, db_conn, db_users, db_stats, GUILD_IDS
from utils.time_converter import format_datetime, round_minutes_down, td_format
from utils.arguments_parser import MyParser
from utils.plot_utils import matplotlib_to_plotly
from utils.utils import make_progress_bar
from cogs.pixelart.color_breakdown import _colors
from cogs.pixelart.highlight import _highlight


class PxlsStats(commands.Cog):
    def __init__(self, client):
        self.client = client

    @cog_ext.cog_slash(
        name="generalstats",
        description="Show some general stats about the canvas.",
        guild_ids=GUILD_IDS,
    )
    async def _generalstats(self, ctx: SlashContext):
        await ctx.defer()
        await self.generalstats(ctx)

    @commands.command(
        name="generalstats",
        description="Show some general stats about the canvas.",
        aliases=["gstats", "gs", "canvasinfo"],
    )
    async def p_generalstats(self, ctx):
        async with ctx.typing():
            await self.generalstats(ctx)

    async def generalstats(self, ctx):
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
        total_amount = board.shape[0] * board.shape[1]
        total_placeable = np.sum(placemap != 255)
        total_non_virgin = np.sum(virginmap == 0)

        # get canvas info
        canvas_code = await stats.get_canvas_code()
        last_updated = stats.last_updated_to_date(stats.get_last_updated())
        # find the earliest datetime for the current canvas
        sql = "SELECT MIN(datetime),datetime FROM record WHERE canvas_code = ?"
        start_date = await db_conn.sql_select(sql, canvas_code)
        start_date = start_date[0]["datetime"]

        # get average cd/online
        data = await db_stats.get_general_stat(
            "online_count", datetime.min, datetime.max, canvas=True
        )
        online_counts = [int(e[0]) for e in data if e[0] is not None]
        cooldowns = [get_cd(count) for count in online_counts]
        average_online = sum(online_counts) / len(online_counts)
        min_online = min(online_counts)
        max_online = max(online_counts)
        average_cd = sum(cooldowns) / len(cooldowns)

        general_stats_text = "• Total Users: `{}`\n• Total Factions: `{}`".format(
            format_number(total_users), format_number(total_factions)
        )

        canvas_stats_text = """
        • Dimensions: `{} x {}`\n• Total Pixels: `{}`/`{}` (`{}%` placeable)\n• Total Placed: `{}`\n• Total Non-Virgin: `{}`\n• Percentage Non-Virgin:\n**|**{}**|** `{}%`""".format(
            board.shape[1],
            board.shape[0],
            format_number(int(total_placeable)),
            format_number(total_amount),
            format_number(total_placeable / total_amount * 100),
            format_number(total_placed),
            format_number(int(total_non_virgin)),
            f"`{make_progress_bar(total_non_virgin/total_placeable*100)}`",
            format_number(total_non_virgin / total_placeable * 100),
        )

        info_text = "• Canvas Code: `{}`\n• Start Date: {}\n• Time Elapsed: {}\n• Canvas Users: `{}`\n• Average online: `{}` users (min: `{}`, max: `{}`)\n• Average cooldown: `{}s`".format(
            canvas_code,
            format_datetime(start_date),
            td_format(
                datetime.utcnow() - start_date, hide_seconds=True, max_unit="day"
            ),
            active_users,
            round(average_online, 2),
            min_online,
            max_online,
            round(average_cd, 2),
        )

        # create an embed with all the infos
        emb = discord.Embed(title="Pxls.space Stats", color=0x66C5CC)
        emb.add_field(name="**General Stats**", value=general_stats_text, inline=False)
        emb.add_field(name="**Canvas Info**", value=info_text, inline=False)
        emb.add_field(name="**Canvas Stats**", value=canvas_stats_text, inline=False)
        emb.add_field(
            name="\u200b",
            value="Last updated: " + format_datetime(last_updated, "R"),
            inline=False,
        )

        # set the board image as thumbnail
        board_array = stats.palettize_array(board)
        board_img = Image.fromarray(board_array)
        f = image_to_file(board_img, "board.png")
        emb.set_thumbnail(url="attachment://board.png")

        await ctx.send(embed=emb, file=f)

    @cog_ext.cog_slash(
        name="userinfo",
        description="Show some informations about a pxls user.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="username",
                description="A pxls username.",
                option_type=3,
                required=False,
            )
        ],
    )
    async def _userinfo(self, ctx: SlashContext, username=None):
        await ctx.defer()
        await self.userinfo(ctx, username)

    @commands.command(
        name="userinfo",
        aliases=["uinfo", "status"],
        usage="<username>",
        description="Show some informations about a pxls user.",
        help=f"""
        -`<username>`: a pxls username (will use your set username if set)\n
        **Status explanation:**
        {STATUS_EMOJIS["bot"]} `online (botting)`: the user is placing more than the best possible
        {STATUS_EMOJIS["fast"]}`online (fast)`: the user is close to the best possible in the last 15 minutes
        {STATUS_EMOJIS["online"]}`online`: the user placed in the last 15 minutes
        {STATUS_EMOJIS["idle"]}`idle`: the user stopped placing 15/30 minutes ago
        {STATUS_EMOJIS["offline"]}`offline`: The user hasn't placed in the last 30 minutes
        {STATUS_EMOJIS["inactive"]}`inactive`: The user hasn't placed on the current canvas
        """,
    )
    async def p_userinfo(self, ctx, username=None):
        async with ctx.typing():
            await self.userinfo(ctx, username)

    async def userinfo(self, ctx, name=None):
        "Show some informations about a pxls user."
        if name is None:
            # select the discord user's pxls username if it has one linked
            discord_user = await db_users.get_discord_user(ctx.author.id)
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id is None:
                prefix = ctx.prefix if isinstance(ctx, commands.Context) else "/"
                return await ctx.send(
                    f"❌ You need to specify a pxls username.\n(You can set your default username with `{prefix}setname <username>`)"
                )
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                user_id = pxls_user_id
        else:
            user_id = await db_users.get_pxls_user_id(name)
            if user_id is None:
                return await ctx.send("❌ User not found.")

        # get current pixels and leaderboard place
        last_leaderboard = await db_stats.get_last_leaderboard()
        user_row = None
        for row in last_leaderboard:
            if row["name"] == name:
                user_row = row
                break

        if user_row is None:
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

            last_updated = format_datetime(user_row["datetime"], "R")

        alltime_text = "• Rank: `{}`\n• Pixels: `{}`".format(
            alltime_rank, format_number(alltime_count)
        )
        canvas_text = "• Rank: `{}`\n• Pixels: `{}`".format(
            canvas_rank, format_number(canvas_count)
        )

        # get the recent activity stats
        time_intervals = [0.25, 1, 24, 24 * 7]  # in hours
        time_intervals.append(0.5)
        interval_names = ["15 min", "hour", "day", "week"]
        record_id_list = []
        record_list = []
        now_time = datetime.now(timezone.utc)
        current_canvas_code = await stats.get_canvas_code()
        for time_interval in time_intervals:
            time = now_time - timedelta(hours=time_interval) - timedelta(minutes=1)
            time = round_minutes_down(time)
            record = await db_stats.find_record(time, current_canvas_code)
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
        """.format(
            ", ".join(["?"] * len(record_id_list))
        )
        rows = await db_conn.sql_select(sql, (user_id,) + tuple(record_id_list))

        diff_list = []
        for id in record_id_list:
            diff = None
            for row in rows:
                # calcluate the difference for each time if the value is not null
                # and compare the canvas count if the alltime count is null
                if row["record_id"] == id:
                    if alltime_count is not None and row["alltime_count"] is not None:
                        diff = alltime_count - row["alltime_count"]
                    elif canvas_count is not None and row["canvas_count"] is not None:
                        diff = canvas_count - row["canvas_count"]
            diff_list.append(diff)

        recent_activity = [
            f"• Last {interval_names[i]}: `{format_number(diff_list[i])}`"
            for i in range(len(diff_list) - 1)
        ]
        recent_activity_text = "\n".join(recent_activity)
        recent_activity_text += f"\n\nLast updated: {last_updated}"

        # get the status
        last_15m = diff_list[0]
        last_30m = diff_list[-1]
        last_online_date = None
        session_start_str = None

        if last_15m is None and last_30m is None:
            status = "???"
            status_emoji = ""
            embed_color = 0x747F8D
        else:
            # online
            if last_15m != 0:
                # get the session duration
                session_start = await db_stats.get_session_start_time(
                    user_id, not (bool(alltime_count))
                )
                if session_start is not None:
                    session_start_dt = session_start["datetime"]
                    session_start_str = format_datetime(session_start_dt, "R")

                # if the amount placed in the last 15m is at least 95% of the
                # best possible, the status is 'online (fast)'
                dt2 = user_row["datetime"]
                dt1 = record_list[0]["datetime"]
                best_possible, average_cooldown = await get_best_possible(dt1, dt2)
                fast_amount = int(best_possible * 0.95)

                if last_15m > best_possible:
                    status = "online (botting)"
                    status_emoji = STATUS_EMOJIS["bot"]
                    embed_color = 0x7CE1EC
                elif last_15m >= fast_amount:
                    status = "online (fast)"
                    status_emoji = STATUS_EMOJIS["fast"]
                    embed_color = 0x9676CB
                else:
                    status = "online"
                    status_emoji = STATUS_EMOJIS["online"]
                    embed_color = 0x43B581
            # idle
            elif last_30m != 0:
                status = "idle"
                status_emoji = STATUS_EMOJIS["idle"]
                embed_color = 0xFCC15E

            else:
                # search for the last online time
                last_online = await db_stats.get_last_online(
                    user_id, not (bool(alltime_count)), alltime_count or canvas_count
                )
                if last_online is not None:
                    last_online_date = last_online["datetime"]
                    if last_online["record_id"] == 1:
                        last_online_date = "over " + format_datetime(
                            last_online_date, "R"
                        )
                    else:
                        last_online_date = format_datetime(last_online_date, "R")

                # inactive
                if canvas_count == 0 or canvas_count is None:
                    status = "inactive"
                    status_emoji = STATUS_EMOJIS["inactive"]
                    embed_color = 0x484848
                # offline
                else:
                    status = "offline"
                    status_emoji = STATUS_EMOJIS["offline"]
                    embed_color = 0x747F8D

        # get the profile page
        profile_url = "https://pxls.space/profile/{}".format(name)

        description = f"**Status**: {status_emoji} `{status}`\n"
        if session_start_str is not None:
            description += f"*(Started placing: {session_start_str})*\n"
        if last_online_date is not None:
            description += f"*(Last pixel: {last_online_date})*\n"

        description += f"[Profile page]({profile_url})"

        # create and send the embed
        emb = discord.Embed(
            title=f"User Info for `{name}`", color=embed_color, description=description
        )
        emb.add_field(name="**Canvas stats**", value=canvas_text, inline=True)
        emb.add_field(name="**All-time stats**", value=alltime_text, inline=True)
        emb.add_field(name="**Recent activity**", value=recent_activity_text, inline=False)
        await ctx.send(embed=emb)

    choices = ["heatmap", "virginmap", "nonvirgin", "initial"]

    @cog_ext.cog_slash(
        name="board",
        description="Get the current pxls board.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="display",
                description="How to display the canvas.",
                option_type=3,
                required=False,
                choices=[create_choice(name=c, value=c) for c in choices],
            ),
            create_option(
                name="opacity",
                description="The opacity of the background behind the heatmap between 0 and 100 (default: 20)",
                option_type=4,
                required=False,
            ),
        ],
    )
    async def _board(self, ctx: SlashContext, display=None, opacity=None):
        await ctx.defer()
        args = ()
        if display == "heatmap":
            args += ("-heatmap",)
            if opacity:
                args += (str(opacity),)
        elif display:
            args += ("-" + display,)
        await self.board(ctx, *args)

    @commands.command(
        name="board",
        description="Get the current pxls board.",
        usage="[-virginmap] [-nonvirgin] [-heatmap [opacity]]",
        help="""
        - `[-virginmap]`: show a map of the virgin pixels (white = virgin)
        - `[-nonvirgin]`: show the board without the virgin pixels
        - `[-heatmap [opacity]]`: show the heatmap on top of the canvas\
            (the opacity value should be between 0 and 100, the default value is 20)
        - `[-initial]`: show the initial state of the canvas""",
    )
    async def p_board(self, ctx, *options):
        async with ctx.typing():
            await self.board(ctx, *options)

    async def board(self, ctx, *args):
        # parse the args
        parser = MyParser(add_help=False)
        parser.add_argument("-heatmap", action="store", default=None, nargs="*", required=False)
        parser.add_argument("-nonvirgin", action="store_true", default=False, required=False)
        parser.add_argument("-virginmap", action="store_true", default=False, required=False)
        parser.add_argument("-initial", action="store_true", default=False, required=False)

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        heatmap_opacity = None
        if parsed_args.heatmap is not None:
            # check on the opacity argument
            if len(parsed_args.heatmap) == 0:
                heatmap_opacity = 20
            else:
                heatmap_opacity = parsed_args.heatmap[0]
                try:
                    heatmap_opacity = int(heatmap_opacity)
                except ValueError:
                    return await ctx.send("❌ The opacity value must be an integer.")
                if heatmap_opacity < 0 or heatmap_opacity > 100:
                    return await ctx.send(
                        "❌ The opacity value must be between 0 and 100."
                    )

        # virginmap
        if parsed_args.virginmap:
            array = stats.virginmap_array.copy()
            array[array == 255] = 1
            array[stats.placemap_array != 0] = 255
            array = stats.palettize_array(array, palette=["#000000", "#00DD00"])
            title = "Canvas Virginmap"
        # heatmap
        elif heatmap_opacity is not None:
            # get the heatmap
            array = await stats.fetch_heatmap()
            # invert the values to have the inactive pixels at 255 (which is the default transparent value)
            array = 255 - array
            heatmap_palette = matplotlib_to_plotly("plasma_r", 255)
            array = stats.palettize_array(array, heatmap_palette)
            # get the canvas board
            canvas_array = stats.board_array
            canvas_array = stats.palettize_array(canvas_array)
            title = "Canvas Heatmap"
        # non-virgin board
        elif parsed_args.nonvirgin:
            placeable_board = await stats.get_placable_board()
            virgin_array = stats.virginmap_array
            array = placeable_board.copy()
            array[virgin_array != 0] = 255
            array[virgin_array == 0] = placeable_board[virgin_array == 0]
            array = stats.palettize_array(array)
            title = "Current Board (non-virgin pixels)"
        # initial board
        elif parsed_args.initial:
            array = await stats.fetch_initial_canvas()
            array = stats.palettize_array(array)
            title = "Initial Board"
        # current board
        else:
            array = stats.board_array
            array = stats.palettize_array(array)
            title = "Current Board"

        if heatmap_opacity is not None:
            # paste the heatmap image on top of the darken board
            heatmap_img = Image.fromarray(array)
            board_img = Image.fromarray(canvas_array)
            enhancer = ImageEnhance.Brightness(board_img)
            board_img = enhancer.enhance(heatmap_opacity / 100)
            board_img.paste(heatmap_img, (0, 0), heatmap_img)
        else:
            board_img = Image.fromarray(array)
        embed = discord.Embed(title=title, color=0x66C5CC)
        embed.timestamp = datetime.now(timezone.utc)
        file = image_to_file(board_img, "board.png", embed)
        await ctx.send(file=file, embed=embed)

    @cog_ext.cog_slash(
        name="canvascolors",
        description="Show the amount for each color on the canvas.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="nonvirgin",
                description="To show the amount on the 'non-virgin' pixels only.",
                option_type=5,
                required=False,
            )
        ],
    )
    async def _canvascolors(self, ctx: SlashContext, nonvirgin=False):
        await ctx.defer()
        await self.canvascolors(ctx, "-placed" if nonvirgin else None)

    @commands.command(
        name="canvascolors",
        description="Show the amount for each color on the canvas.",
        aliases=["canvascolours", "cc"],
        usage="[-placed|-p]",
    )
    async def p_canvascolors(self, ctx, *options):
        async with ctx.typing():
            await self.canvascolors(ctx, *options)

    async def canvascolors(self, ctx, *options):
        """Show the canvas colors."""
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

        await _colors(self.client, ctx, img, title)

    @cog_ext.cog_slash(
        name="canvashighlight",
        description="Highlight the selected colors on the canvas.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="colors",
                description="List of pxls colors separated by a comma.",
                option_type=3,
                required=True,
            ),
            create_option(
                name="bgcolor",
                description="To display behind the selected colors (can be a color name, hex color, 'none', 'light' or 'dark')",
                option_type=3,
                required=False,
            ),
        ],
    )
    async def _canvashighlight(self, ctx: SlashContext, colors, bgcolor=None):
        await ctx.defer()
        args = (colors,)
        if bgcolor:
            args += ("-bgcolor", bgcolor)
        await self.canvashighlight(ctx, *args)

    @commands.command(
        name="canvashighlight",
        description="Highlight the selected colors on the canvas.",
        aliases=["chl", "canvashl"],
        usage="<colors> [-bgcolor|-bg <color>]",
        help="""
            - `<colors>`: list of pxls colors separated by a comma
            - `[-bgcolor|bg <color>]`: the color to display behind the higlighted colors, it can be:
                • a pxls name color (ex: "red")
                • a hex color (ex: "#ff000")
                • "none": to have a transparent background
                • "dark": to have the background darkened
                • "light": to have the background lightened""",
    )
    async def p_canvashighlight(self, ctx, *, args):
        args = args.split(" ")
        async with ctx.typing():
            await self.canvashighlight(ctx, *args)

    async def canvashighlight(self, ctx, *args):
        "Highlight the selected colors on the canvas"
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("colors", type=str, nargs="+")
        parser.add_argument(
            "-bgcolor", "-bg", nargs="*", type=str, action="store", required=False
        )
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        # get the board with the placeable pixels only
        canvas_array_idx = await stats.get_placable_board()
        canvas_array = stats.palettize_array(canvas_array_idx)
        await _highlight(ctx, canvas_array, parsed_args)


def setup(client):
    client.add_cog(PxlsStats(client))
