import disnake
from disnake.ext import commands
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from utils.image.image_utils import hex_str_to_int

from utils.setup import db_stats, db_users
from utils.time_converter import (
    str_to_td,
    round_minutes_down,
    td_format,
    format_datetime,
)
from utils.arguments_parser import (
    check_ranks,
    parse_leaderboard_args,
    valid_datetime_type,
)
from utils.discord_utils import format_number, image_to_file
from utils.table_to_image import table_to_image
from utils.plot_utils import fig2img, get_theme, hex_to_rgba_string
from utils.pxls.cooldown import get_best_possible
from cogs.pxls.speed import get_stats_graph
from utils.timezoneslib import get_timezone


class PxlsLeaderboard(commands.Cog, name="Pxls Leaderboard"):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="leaderboard")
    async def _leaderboard(
        self,
        inter: disnake.AppCmdInter,
        username: str = [],
        canvas: bool = False,
        last: str = None,
        lines: int = commands.Param(default=15, ge=1, le=40),
        graph: bool = None,
        bars: bool = False,
        ranks: str = None,
        eta: bool = None,
        before: str = None,
        after: str = None,
    ):
        """Show the all-time or canvas leaderboard.

        Parameters
        ----------
        username: Center the leaderboard on this user. ('!' = your set username)
        last: Show the leaderboard in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)
        canvas: To get the canvas leaderboard.
        lines: The number of lines to show. (default: 15)
        graph: To show a progress graph for each user in the leaderboard.
        bars: To show a bar graph of the current leaderboard.
        ranks: Show the leaderboard between 2 ranks. (format: <rank 1>-<rank 2>)
        eta: Add an ETA column showing the estimated time to pass the user above.
        before: To show the leaderboard before a specific date. (format: YYYY-mm-dd HH:MM)
        after: To show the leaderboard after a specific date. (format: YYYY-mm-dd HH:MM)
        """
        await inter.response.defer()
        if username:
            username = username.split(" ")
        if before:
            before = before.split(" ")
        if after:
            after = after.split(" ")
        if ranks:
            try:
                ranks = check_ranks(ranks)
            except Exception as e:
                return await inter.send(f":x: {e}")
        await self.leaderboard(
            inter, username, canvas, last, lines, graph, bars, ranks, eta, before, after
        )

    @commands.command(
        name="leaderboard",
        usage="[username] [-canvas] [-last ?y?m?w?d?h?m?s] [-lines <number>] [-graph] [-bars] [-ranks ?-?] [-before <date time>] [-after <date time>]",
        description="Show the all-time or canvas leaderboard.",
        aliases=["ldb"],
        help="""- `[username]`: center the leaderboard on this user (`!` = your set username)
                  - `[-canvas|-c]`: to get the canvas leaderboard
                  - `[-last ?y?mo?w?d?h?m?s]` Show the leaderboard in the last x years/months/weeks/days/hour/min/s
                  - `[-lines <number>]`: number of lines to show, must be less than 40 (default 15)
                  - `[-graph|-g]`: show a progress graph for each user in the leaderboard
                  - `[-bars|-b]`: show a bar graph of the leaderboard
                  - `[-ranks ?-?]`: show the leaderboard between 2 ranks
                  - `[-eta]`: add an ETA column showing the estimated time to pass the user above
                  - `[-before <date time>]`: show the speed before a date and time (format YYYY-mm-dd HH:MM)
                  - `[-after <date time>]`: show the speed after a date and time (format YYYY-mm-dd HH:MM)
                  """,
    )
    async def p_leaderboard(self, ctx, *args):
        try:
            param = parse_leaderboard_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.leaderboard(
                ctx,
                param["names"],
                param["canvas"],
                param["last"],
                param["lines"],
                param["graph"],
                param["bars"],
                param["ranks"],
                param["eta"],
                param["before"],
                param["after"],
            )

    async def leaderboard(
        self,
        ctx,
        username=[],
        canvas=False,
        last=None,
        nb_line=15,
        graph=False,
        bars=False,
        ranks=None,
        eta=None,
        before=None,
        after=None,
    ):
        """Shows the pxls.space leaderboard"""

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)
        font = discord_user["font"]
        user_timezone = discord_user["timezone"]

        speed_opt = False
        sort_opt = None

        # get the linked username if "!" is in the names list
        if "!" in username:
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id is None:
                is_slash = not isinstance(ctx, commands.Context)
                cmd_name = "user setname" if is_slash else "setname"
                prefix = "/" if is_slash else ctx.prefix
                usage_text = f"(You can set your default username with `{prefix}{cmd_name} <username>`)"
                return await ctx.send(
                    "❌ You need to have a set username to use `!`.\n" + usage_text
                )
            name = await db_users.get_pxls_user_name(pxls_user_id)
            username = [name if u == "!" else u for u in username]

        # if a time value is given, we will show the leaderboard during this time
        if before or after or last:
            speed_opt = True
            sort_opt = "speed"
            if before is None and after is None:
                input_time = str_to_td(last)
                if not input_time:
                    return await ctx.send(
                        "❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
                    )
                input_time = input_time + timedelta(minutes=1)
                date2 = datetime.now(timezone.utc)
                date1 = round_minutes_down(datetime.now(timezone.utc) - input_time)
            else:
                last = None
                try:
                    # Convert the dates to datetime object and check if they are valid
                    if after:
                        after = valid_datetime_type(after, get_timezone(user_timezone))
                    if before:
                        before = valid_datetime_type(before, get_timezone(user_timezone))
                except ValueError as e:
                    return await ctx.send(f"❌ {e}")

                if after and before and before < after:
                    return await ctx.send(
                        ":x: The 'before' date can't be earlier than the 'after' date."
                    )

                date1 = after or datetime.min
                date2 = before or datetime.max
        else:
            date1 = datetime.now(timezone.utc)
            date2 = datetime.now(timezone.utc)

        # check on sort arg
        if not sort_opt:
            sort = "canvas" if canvas else "alltime"
        else:
            sort = sort_opt
            # canvas_opt = "canvas" # only get the canvas stats when sorting by speed

        # fetch the leaderboard from the database
        # + change the canvas opt if sort by speed on time frame on the current canvas
        (
            canvas,
            last_date,
            datetime1,
            datetime2,
            ldb,
        ) = await db_stats.get_leaderboard_between(date1, date2, canvas, sort)

        # check that we can actually calculate the speed
        if speed_opt and datetime1 == datetime2:
            return await ctx.send("❌ The time frame given is too short.")

        # trim the leaderboard to only get the lines asked
        if ranks:
            (rank_low, rank_high) = ranks
            username = []
            try:
                ldb = ldb[rank_low - 1 : rank_high]
            except IndexError:
                return await ctx.send(
                    "❌ Can't find values between these ranks in the leaderboard."
                )

        elif username:
            # looking for the index and pixel count of the given user
            name_index = None
            for index, line in enumerate(ldb):
                name = list(line)[1]
                if speed_opt:
                    pixels = list(line)[3]
                else:
                    pixels = list(line)[2]
                if name == username[0]:
                    name_index = index
                    user_pixels = pixels
                    break
            if name_index is None:
                return await ctx.send("❌ User not found")

            if len(username) == 1:
                # calucluate the indexes around the user
                min_idx = max(0, (name_index - round(nb_line / 2)))
                max_idx = min(len(ldb), name_index + round(nb_line / 2) + 1)
                # if one of the idx hits the limit, we change the other idx to show more lines
                if min_idx == 0:
                    max_idx = min_idx + nb_line
                if max_idx == len(ldb):
                    min_idx = max_idx - nb_line
                ldb = ldb[min_idx:max_idx]
            else:
                # only keep the users in the "username" list
                trimmed_ldb = []
                for line in ldb:
                    if line[1] in username:
                        trimmed_ldb.append(line)
                ldb = trimmed_ldb
        else:
            ldb = ldb[0:nb_line]

        # build the header of the leaderboard
        column_names = ["Rank", "Username", "Pixels"]
        alignments2 = ["center", "center", "right"]
        if username:
            column_names.append("Diff")
            alignments2.append("left")
        if speed_opt:
            column_names.append("Speed")
            alignments2.append("right")
        elif eta:
            column_names.append("Speed (px/d)")
            alignments2.append("center")
            column_names.append("ETA")
            alignments2.append("center")

        # build the content of the leaderboard
        res_ldb = []
        for i in range(len(ldb)):
            res_ldb.append([])
            # add the rank
            rank = ldb[i][0]
            if rank > 1000:
                rank = ">1000"
            res_ldb[i].append(rank)

            # add the name
            res_ldb[i].append(ldb[i][1])

            # add the pixel count
            if speed_opt:
                res_ldb[i].append(ldb[i][3])
            else:
                res_ldb[i].append(ldb[i][2])

            # add the diff values
            if username:
                try:
                    if speed_opt:
                        diff = user_pixels - ldb[i][3]
                    else:
                        diff = user_pixels - ldb[i][2]
                    res_ldb[i].append(diff)
                except Exception:
                    res_ldb[i].append("???")

            if speed_opt:
                # add the speed
                diff_pixels = ldb[i][3] or 0
                diff_time = datetime2 - datetime1
                nb_hours = diff_time / timedelta(hours=1)
                speed = diff_pixels / nb_hours
                # show the speed in pixel/day if the time frame is more than a day
                if nb_hours > 24:
                    speed = speed * 24
                    res_ldb[i].append(f"{round(speed,1)} px/d")
                else:
                    res_ldb[i].append(f"{round(speed,1)} px/h")
            elif eta:
                # add the ETA
                # get the speed in the last 1 day
                eta_time = datetime2 - timedelta(days=1)
                eta_record_time, eta_record = await db_stats.get_pixels_at(
                    eta_time, ldb[i][1], canvas
                )
                if eta_record:
                    diff_time = (datetime2 - eta_record_time) / timedelta(days=1)
                    if ldb[i][2] is not None:
                        if canvas:
                            eta_pixels = ldb[i][2] - eta_record["canvas_count"]
                        else:
                            eta_pixels = ldb[i][2] - eta_record["alltime_count"]

                        eta_speed = eta_pixels / diff_time  # in px/d
                    else:
                        eta_speed = None
                else:
                    eta_speed = None

                # add the eta time
                if i == 0:
                    eta = "N/A (first)"
                else:
                    eta_speed_above = res_ldb[i - 1][-2]
                    if eta_speed_above is not None and eta_speed is not None:
                        diff_speed = eta_speed - eta_speed_above
                        if diff_speed == 0:
                            eta = "Never."
                        elif diff_speed < 0:
                            eta = "N/A (slower)"
                        else:
                            goal = ldb[i - 1][2] - ldb[i][2]
                            if goal == 0:
                                eta = "N/A (same count)"
                            else:
                                eta_time = goal / diff_speed  # in days
                                eta = td_format(
                                    timedelta(days=eta_time), short_format=True
                                )
                    else:
                        eta = None
                res_ldb[i].append(eta_speed)
                res_ldb[i].append(eta)

        # create the image with the leaderboard data
        colors = None
        if graph:
            colors = theme.get_palette(len(res_ldb))
        elif username:
            colors = []
            for e in res_ldb:
                if e[1] == username[0]:
                    colors.append(theme.get_palette(1)[0])
                else:
                    colors.append(None)

        # format the numbers correctly
        res_ldb = [[format_number(line) for line in r] for r in res_ldb]

        img = await table_to_image(
            res_ldb,
            column_names,
            alignments=alignments2,
            colors=colors,
            theme=theme,
            font=font,
        )

        # make title and embed header
        text = ""
        if speed_opt:
            past_time = datetime1
            recent_time = datetime2
            diff_time = round_minutes_down(recent_time) - round_minutes_down(past_time)
            diff_time_str = td_format(diff_time)
            if last:
                title = "Leaderboard of the last {}".format(
                    diff_time_str[2:]
                    if (diff_time_str.startswith("1 ") and "," not in diff_time_str)
                    else diff_time_str
                )
            else:
                title = "Leaderboard"
                text += "• Between {} and {}\n({})\n".format(
                    format_datetime(past_time),
                    format_datetime(recent_time),
                    td_format(diff_time),
                )
            # calculate the best possbile amount in the time frame
            best_possible, average_cooldown = await get_best_possible(
                datetime1, datetime2
            )
            text += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
            text += f"• Best possible (without stack): ~`{format_number(best_possible)}` pixels.\n"

        elif canvas:
            title = "Canvas Leaderboard"
        else:
            title = "All-time Leaderboard"

        if not (before or after):
            text += f"• Last updated: {format_datetime(last_date,'R')}"

        # make the progress graph
        if graph:
            name_list = [u[1] for u in res_ldb]
            if last is None:
                dt1 = datetime(1900, 1, 1)
                dt2 = datetime.utcnow()
            else:
                dt1 = datetime1
                dt2 = datetime2
            stats_dt1, stats_dt2, stats_history = await db_stats.get_stats_history(
                name_list, dt1, dt2, canvas
            )
            stats = []
            for user in stats_history:
                name = user[0]
                data = user[1]
                data_dates = [stat["datetime"] for stat in data]
                if last is not None:
                    # substract the first value to each value so they start at 0
                    data_without_none = [
                        d["pixels"] for d in data if d["pixels"] is not None
                    ]
                    if not data_without_none:
                        continue
                    lowest_pixels = data_without_none[0]
                    data_pixels = [
                        (
                            (stat["pixels"] - lowest_pixels)
                            if (stat["pixels"] is not None and lowest_pixels is not None)
                            else None
                        )
                        for stat in data
                    ]
                else:
                    data_pixels = [stat["pixels"] for stat in data]
                stats.append([name, data_dates, data_pixels])
            stats.sort(key=lambda x: x[2][-1], reverse=True)
            graph_fig = await get_stats_graph(stats, "", theme, user_timezone)
            graph_img = await fig2img(graph_fig)

        # make the bars graph
        if bars:
            data = [
                int(user[2].replace(" ", "")) if user[2] != "???" else None
                for user in res_ldb
            ]
            theme_colors = theme.get_palette(1)
            if username:
                names = [
                    (
                        f"<span style='color:{theme_colors[0]};'>{user[1]}</span>"
                        if user[1] == username[0]
                        else user[1]
                    )
                    for user in res_ldb
                ]
                colors = [
                    (theme_colors[0] if user[1] == username[0] else theme.off_color)
                    for user in res_ldb
                ]
            else:
                names = [user[1] for user in res_ldb]
                colors = [theme_colors[0]] * len(res_ldb)

            if speed_opt and diff_time.total_seconds() < 3600 * 18:
                bars_best_possible = best_possible
            else:
                bars_best_possible = None
            fig = self.make_bars(names, data, title, theme, colors, bars_best_possible)
            bars_img = await fig2img(fig)

        # create a discord embed
        emb = disnake.Embed(
            color=hex_str_to_int(theme.get_palette(1)[0]), title=title, description=text
        )
        file = await image_to_file(img, "leaderboard.png", emb)

        if eta and not speed_opt:
            emb.set_footer(
                text="The ETA values are calculated with the speed in the last 1 day.\n"
            )

        files = [file]
        embeds = [emb]
        # add the graphs if options enabled
        if graph:
            graph_embed = disnake.Embed(color=0x66C5CC)
            graph_file = await image_to_file(graph_img, "graph.png", graph_embed)
            files.append(graph_file)
            embeds.append(graph_embed)
        if bars:
            bars_embed = disnake.Embed(color=0x66C5CC)
            bars_file = await image_to_file(bars_img, "bar_chart.png", bars_embed)
            files.append(bars_file)
            embeds.append(bars_embed)

        await ctx.send(embeds=embeds, files=files)

    @staticmethod
    def make_bars(users, pixels, title, theme, colors=None, best_possible=None):
        if colors is None:
            colors = theme.get_palette(len(users))
        # create the graph and style
        fig = go.Figure(layout=theme.get_layout(with_annotation=False))
        fig.update_yaxes(rangemode="tozero")
        fig.update_xaxes(tickmode="linear")
        fig.update_layout(showlegend=False)
        fig.update_layout(
            title="<span style='color:{};'>{}</span>".format(
                theme.get_palette(1)[0], title
            )
        )

        text = [
            '<span style = "text-shadow:\
                        -{2}px -{2}px 0 {0},\
                        {2}px -{2}px 0 {0},\
                        -{2}px {2}px 0 {0},\
                        {2}px {2}px 0 {0},\
                        0px {2}px 0px {0},\
                        {2}px 0px 0px {0},\
                        -{2}px 0px 0px {0},\
                        0px -{2}px 0px {0};">{1}</span>'.format(
                theme.background_color, pixel, 2
            )
            for pixel in pixels
        ]

        # add a line with the "best possible"
        if best_possible:
            fig.add_hline(
                y=best_possible,
                line_dash="dash",
                annotation_text=f"Best Possible ({best_possible})",
                annotation_position="top right",
                annotation_font_color=theme.font_color,
                line=dict(color=theme.font_color, width=3),
            )

        # trace the user data
        if theme.has_underglow:
            # different style if the theme has underglow
            fig.add_trace(
                go.Bar(
                    x=users,
                    y=pixels,
                    text=text,
                    textposition="outside",
                    marker_color=[hex_to_rgba_string(color, 0.3) for color in colors],
                    marker_line_color=colors,
                    marker_line_width=2.5,
                    textfont=dict(color=colors, size=40),
                    cliponaxis=False,
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    x=users,
                    y=pixels,
                    # add an outline of the bg color to the text
                    text=text,
                    textposition="outside",
                    marker=dict(color=colors, opacity=0.95),
                    textfont=dict(color=colors, size=40),
                    cliponaxis=False,
                )
            )
        return fig


def setup(bot: commands.Bot):
    bot.add_cog(PxlsLeaderboard(bot))
