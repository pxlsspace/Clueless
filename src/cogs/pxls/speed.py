import plotly.graph_objects as go
import disnake
from datetime import datetime, timedelta, timezone
from disnake.ext import commands

from utils.discord_utils import image_to_file, format_number
from utils.setup import db_stats, db_users, stats as stats_manager
from utils.arguments_parser import parse_speed_args, valid_datetime_type
from utils.table_to_image import table_to_image
from utils.time_converter import (
    format_datetime,
    format_timezone,
    round_minutes_down,
    str_to_td,
    td_format,
)
from utils.plot_utils import add_glow, get_theme, fig2img, hex_to_rgba_string
from utils.image.image_utils import hex_str_to_int, v_concatenate
from utils.pxls.cooldown import get_best_possible
from utils.timezoneslib import get_timezone
from utils.utils import in_executor, shorten_list


class PxlsSpeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="speed")
    async def _speed(
        self,
        inter: disnake.AppCmdInter,
        usernames: str = None,
        last: str = None,
        alltime: bool = False,
        groupby: str = commands.Param(
            default=None, choices=["hour", "day", "week", "month", "canvas"]
        ),
        progress: bool = False,
        before: str = None,
        after: str = None,
    ):
        """Show the speed of a pxls user with a graph.

        Parameters
        ----------
        usernames: A list pxls usernames separated by a space. ('!' = your set username.)
        last: Show the speed in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)
        alltime: To use the all-time data (default: False).
        groupby: Show a bar chart for each hour/day/week/month/canvas.
        progress: To compare the progress instead of alltime/canvas stats.
        before: To show the speed before a specific date (format: YYYY-mm-dd HH:MM)
        after: To show the speed after a specific date (format: YYYY-mm-dd HH:MM)
        """
        await inter.response.defer()
        if before:
            before = before.split(" ")
        if after:
            after = after.split(" ")
        await self.speed(
            inter, usernames, last, not (alltime), groupby, progress, before, after
        )

    @commands.command(
        name="speed",
        usage="<username> [-alltime] [-groupby [hour|day|week|month]] [-progress] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
        description="Show the speed of a pxls user with a graph.",
        help="""- `<usernames>`: list of pxls usernames separated by a space (`!` = your set username)
              - `[-alltime|-at]`: show the all-time stats
              - `[-groupby|-g]`: show a bar chart for each `hour`, `day`, `week`, `month` or `canvas`
              - `[-progress|-p]`: compare the progress between users
              - `[-last ?y?mo?w?d?h?m?s]` Show the progress in the last x years/months/weeks/days/hours/minutes/seconds (default: 1d)
              - `[-before <date time>]`: show the speed before a date and time (format YYYY-mm-dd HH:MM)
              - `[-after <date time>]`: show the speed after a date and time (format YYYY-mm-dd HH:MM)""",
    )
    async def p_speed(self, ctx, *args):
        try:
            params = parse_speed_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.speed(
                ctx,
                " ".join(params["usernames"]) if params["usernames"] else None,
                params["last"],
                not (params["alltime"]),
                params["groupby"],
                params["progress"],
                params["before"],
                params["after"],
            )

    async def speed(
        self,
        ctx,
        usernames=None,
        last=None,
        canvas=True,
        groupby=None,
        progress=False,
        before=None,
        after=None,
    ):
        """Show the average speed of a user in the last x min, hours or days"""

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = discord_user["timezone"]
        current_user_theme = discord_user["color"] or "default"
        font = discord_user["font"]
        theme = get_theme(current_user_theme)

        # select the discord user's pxls username if it has one linked
        pxls_user_id = discord_user["pxls_user_id"]
        is_slash = not isinstance(ctx, commands.Context)
        cmd_name = "user setname" if is_slash else "setname"
        prefix = "/" if is_slash else ctx.prefix
        usage_text = f"(Use {'`/speed usernames:<your name>`' if is_slash else f'`{prefix}speed <your name>`'} or you can set your default name with `{prefix}{cmd_name} <your name>`)"

        if usernames is None:
            usernames = []
        else:
            if "," in usernames:
                usernames = usernames.split(",")
            else:
                usernames = usernames.split(" ")

        if len(usernames) == 0:
            if pxls_user_id is None:
                return await ctx.send(
                    "❌ You need to specify at least one username.\n" + usage_text
                )
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                usernames.append(name)

        if "!" in usernames:
            if pxls_user_id is None:
                return await ctx.send(
                    "❌ You need to have a set username to use `!`.\n" + usage_text
                )
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                usernames = [name if u == "!" else u for u in usernames]

        # check on date arguments
        if before is None and after is None:
            # if no date argument and -canvas : show the whole canvas
            if last is None and canvas:
                old_time = datetime.min
                recent_time = datetime.now(timezone.utc)
            else:
                date = last or "1d"
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(
                        "❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
                    )
                input_time = input_time + timedelta(minutes=1)
                recent_time = datetime.now(timezone.utc)
                old_time = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
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

            old_time = after or datetime.min
            recent_time = before or datetime.max

        # get the data we need
        if groupby and groupby != "canvas":
            try:
                (past_time, now_time, stats) = await db_stats.get_grouped_stats_history(
                    usernames, old_time, recent_time, groupby, canvas
                )
            except ValueError as e:
                return await ctx.send(f":x: {e}")
        elif groupby == "canvas":
            (past_time, now_time, stats) = await db_stats.get_stats_per_canvas(usernames)
            canvas = False
        else:
            (past_time, now_time, stats) = await db_stats.get_stats_history(
                usernames, old_time, recent_time, canvas
            )

        # check that we found data
        if len(stats) == 0:
            msg = "❌ User{} not found.".format("s" if len(usernames) > 1 else "")
            return await ctx.send(msg)

        # check that we can calculate the speed
        if past_time == now_time:
            return await ctx.send("❌ The time frame given is too short.")
        diff_time = now_time - past_time
        nb_hour = diff_time / timedelta(hours=1)

        # format the data to be displayed
        formatted_data = []
        found_but_no_data = False
        min_data_idx = int(1e6)
        for user in stats:
            data = user[1]
            if groupby and groupby != "canvas":
                # truncate the first data if we're groupping by day/hour
                data = data[1:]
            elif groupby and groupby == "canvas":
                # find the minimum non-null index
                min_user_idx = 0
                for i, d in enumerate(data):
                    if d["placed"] is not None:
                        min_user_idx = i
                        break
                if min_user_idx < min_data_idx:
                    min_data_idx = min_user_idx

            if len(data) == 0:
                continue

            # last username
            name = data[-1]["name"]
            # current pixels
            current_pixels = data[-1]["pixels"]

            if groupby:
                if all([d["placed"] is None for d in data]):
                    # skip the user if all the values are None
                    continue
                diff_pixels = sum([(d["placed"] or 0) for d in data])
            else:
                # find first non-null value
                lowest_pixels = None
                for d in data:
                    if d["pixels"] is not None:
                        lowest_pixels = d["pixels"]
                        break
                if lowest_pixels is None or current_pixels is None:
                    # the user exists in the database but doesnt have data
                    # in the given time frame
                    found_but_no_data = True
                    continue
                diff_pixels = current_pixels - lowest_pixels

            # calculate the speed
            speed_px_h = diff_pixels / nb_hour
            speed_px_d = speed_px_h * 24

            # format data for the graph
            if groupby:
                if groupby == "month":
                    dates = [
                        datetime.strptime(
                            stat["first_datetime"], "%Y-%m-%d %H:%M:%S"
                        ).strftime("%b %Y")
                        for stat in data
                    ]
                    user_timezone = None

                elif groupby == "week":
                    dates = []
                    for stat in data:
                        first_dt = datetime.strptime(
                            stat["first_datetime"], "%Y-%m-%d %H:%M:%S"
                        )
                        last_dt = first_dt + timedelta(days=6)
                        week_dates = (
                            f"{first_dt.strftime('%d-%b')} - {last_dt.strftime('%d-%b')}"
                        )
                        dates.append(week_dates)
                    user_timezone = None

                elif groupby == "day":
                    dates = [stat["first_datetime"][:10] for stat in data]
                    user_timezone = None

                elif groupby == "hour":
                    dates = [stat["first_datetime"][:13] for stat in data]
                    # convert the dates to the user's timezone
                    dates = [datetime.strptime(d, "%Y-%m-%d %H") for d in dates]
                    tz = get_timezone(user_timezone) or timezone.utc
                    dates = [
                        datetime.astimezone(d.replace(tzinfo=timezone.utc), tz)
                        for d in dates
                    ]

                elif groupby == "canvas":
                    dates = ["C" + stat["canvas_code"] for stat in data]
                    user_timezone = None

                pixels = [stat["placed"] for stat in data]
                # remove the "None" values to calculate the min, max, avg
                pixels_int_only = [p for p in pixels if p is not None]
                if len(pixels_int_only) > 0:
                    min_pixels = min(pixels_int_only)
                    max_pixels = max(pixels_int_only)
                    average = sum(pixels_int_only) / len(pixels_int_only)
                else:
                    min_pixels = max_pixels = average = None
            else:
                dates = [stat["datetime"] for stat in data]
                if progress:
                    # substract the first value to each value so they start at 0
                    pixels = [
                        (
                            (stat["pixels"] - lowest_pixels)
                            if (stat["pixels"] is not None and lowest_pixels is not None)
                            else None
                        )
                        for stat in data
                    ]
                else:
                    pixels = [stat["pixels"] for stat in data]

            user_data = [name, current_pixels, diff_pixels]
            if groupby:
                user_data.append(average)
                user_data.append(min_pixels)
                user_data.append(max_pixels)
            else:
                user_data.append(speed_px_h)
                user_data.append(speed_px_d)
            user_data.append(dates)
            user_data.append(pixels)
            formatted_data.append(user_data)

        if len(formatted_data) == 0:
            if found_but_no_data and not canvas:
                if is_slash:
                    msg = f"❌ User{'s' if len(usernames) > 1 else ''} not found in the all-time leaderboard.\n(try using `/speed alltime:False` to use the canvas data instead.)"
                else:
                    msg = f"❌ User{'s' if len(usernames) > 1 else ''} not found in the all-time leaderboard.\n(try using `{prefix}speed` without `-alltime` to use the canvas data instead.)"
            else:
                msg = f"❌ User{'s' if len(usernames) > 1 else ''} not found."
            return await ctx.send(msg)

        # sort the data by the 3rd column (progress in the time frame)
        formatted_data.sort(key=lambda x: x[2], reverse=True)

        # remove all the first None values
        if groupby and groupby == "canvas":
            for dat in formatted_data:
                dat[-1] = dat[-1][min_data_idx:]
                dat[-2] = dat[-2][min_data_idx:]

            min_canvas_code = formatted_data[0][-2][0][1:]  # pain
            canvas_start_date = await db_stats.get_canvas_start_date(min_canvas_code)
            past_time = canvas_start_date
        # create the headers needed for the table
        table_colors = theme.get_palette(len(formatted_data))

        # make the title
        if canvas:
            title = "Canvas Speed"
        else:
            title = "All-time Speed"
        if groupby:
            title += f" (grouped by {groupby})"
        diff_time = round_minutes_down(now_time) - round_minutes_down(past_time)
        diff_time_str = td_format(diff_time)

        # get the image of the table
        if groupby:
            # add a "min" and "max" columns if groupby option
            alignments = ["center", "right", "right", "right", "right", "right"]
            titles = ["Name", "Pixels", "Progress", f"px/{groupby}", "Min", "Max"]

        else:
            alignments = ["center", "right", "right", "right", "right"]
            titles = ["Name", "Pixels", "Progress", "px/h", "px/d"]
        table_data = [d[:-2] for d in formatted_data]

        table_data = [[format_number(c) for c in row] for row in table_data]
        table_image = await table_to_image(
            table_data,
            titles,
            alignments=alignments,
            colors=table_colors,
            theme=theme,
            font=font,
        )

        # create the graph
        graph_data = [[d[0], d[-2], d[-1]] for d in formatted_data]
        if groupby:
            # check that we arent plotting too many bars (limit: 10000 bars)
            nb_bars = sum([len(d[2]) for d in graph_data])
            if nb_bars > 10000:
                return await ctx.send(
                    f":x: That's too many bars too show (**{nb_bars}**). <:bruhkitty:943594789532737586>"
                )
            graph_fig = await get_grouped_graph(graph_data, title, theme, user_timezone)
        else:
            graph_fig = await get_stats_graph(graph_data, title, theme, user_timezone)
        graph_image = await fig2img(graph_fig)
        # merge the table image and graph image
        res_image = await v_concatenate(table_image, graph_image, gap_height=20)

        # calculate the best possbile amount in the time frame
        best_possible, average_cooldown = await get_best_possible(past_time, now_time)

        # create the embed
        description = (
            f"• Between {format_datetime(past_time)} and {format_datetime(now_time)}\n"
        )
        description += f"• Time: `{diff_time_str}`\n"
        description += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
        description += (
            f"• Best possible (without stack): ~`{format_number(best_possible)}` pixels."
        )
        emb = disnake.Embed(color=hex_str_to_int(theme.get_palette(1)[0]))
        emb.add_field(name=title, value=description)

        if canvas:
            canvas_start = await db_stats.get_canvas_start_date(
                await stats_manager.get_canvas_code()
            )
            if (
                canvas_start
                and old_time != datetime.min
                and old_time < canvas_start.replace(tzinfo=timezone.utc)
            ):
                emb.set_footer(
                    text="⚠️ Warning: The time given is earlier than the canvas start, use {} to use the all-time data.".format(
                        "/speed alltime:True" if is_slash else f"{prefix}speed -alltime"
                    )
                )

        # send the embed with the graph image
        file = await image_to_file(res_image, "speed.png", emb)
        await ctx.send(file=file, embed=emb)


def setup(bot: commands.Bot):
    bot.add_cog(PxlsSpeed(bot))


@in_executor()
def get_stats_graph(stats_list: list, title, theme, user_timezone=None):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    glow = theme.has_glow
    if sum([len(d[2]) for d in stats_list]) > 1000:
        glow = False

    # create the graph
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_layout(showlegend=False)
    fig.update_layout(title=f"<span style='color:{colors[0]};'>{title}</span>")

    for i, user in enumerate(stats_list):
        # get the data
        name = user[0]
        dates = user[1]
        pixels = user[2]

        # remove some data if we have too much
        limit = 1000
        if len(pixels) > limit:
            pixels = shorten_list(pixels, limit)
            dates = shorten_list(dates, limit)

        # convert the dates to the user timezone
        dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc), tz) for d in dates]

        # trace the user data
        if theme.has_underglow and any([(p is not None and p <= 100) for p in pixels]):
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=pixels,
                    mode="lines",
                    name=name,
                    line=dict(width=4),
                    marker=dict(color=colors[i], size=6),
                    fill="tozeroy",
                    fillcolor=hex_to_rgba_string(colors[i], 0.04),
                )
            )

        else:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=pixels,
                    mode="lines",
                    name=name,
                    line=dict(width=4),
                    marker=dict(color=colors[i], size=6),
                )
            )

        # add a marge at the right to add the name
        longest_name = max([len(user[0]) for user in stats_list])
        fig.update_layout(margin=dict(r=(longest_name + 2) * 26))

        # add the name
        fig.add_annotation(
            xanchor="left",
            xref="paper",
            yref="y",
            x=1.01,
            y=pixels[-1],
            text=("<b>%s</b>" % name),
            showarrow=False,
            font=dict(color=colors[i], size=40),
        )

    if glow:
        add_glow(fig, nb_glow_lines=5, alpha_lines=0.5, diff_linewidth=4)

    return fig


@in_executor()
def get_grouped_graph(stats_list: list, title, theme, user_timezone=None):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    # create the graph and style
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_yaxes(rangemode="tozero")

    # the title displays the user if there is only 1 in the user_list
    fig.update_layout(title="<span style='color:{};'>{}</span>".format(colors[0], title))

    # get the total number of bars to see if it's worth adding text
    nb_bars = sum([len(d[2]) for d in stats_list])
    for i, user in enumerate(stats_list):
        # get the data
        dates = user[1]
        pixels = user[2]

        # add an outline of the bg color to the text above the bars
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
            if nb_bars <= 200
            else None
            for pixel in pixels
        ]

        name = '<span style="color:{};font-size:40;"><b>{}</b></span>'.format(
            colors[i], user[0]
        )
        # trace the user data
        if theme.has_underglow:
            # different style if the theme has underglow
            fig.add_trace(
                go.Bar(
                    name=name,
                    x=dates,
                    y=pixels,
                    text=text,
                    textposition="outside",
                    marker_color=hex_to_rgba_string(colors[i], 0.15),
                    marker_line_color=colors[i],
                    marker_line_width=2.5,
                    textfont=dict(color=colors[i], size=40),
                    cliponaxis=False,
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    name=name,
                    x=dates,
                    y=pixels,
                    text=text,
                    textposition="outside",
                    marker=dict(color=colors[i], opacity=0.9),
                    textfont=dict(color=colors[i], size=40),
                    cliponaxis=False,
                )
            )

    return fig
