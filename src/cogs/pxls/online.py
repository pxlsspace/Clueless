from datetime import datetime, timedelta, timezone

import disnake
import plotly.graph_objects as go
from disnake.ext import commands

from utils.arguments_parser import MyParser
from utils.discord_utils import format_number, image_to_file
from utils.image.image_utils import hex_str_to_int
from utils.plot_utils import add_glow, fig2img, get_theme, hex_to_rgba_string
from utils.pxls.archives import check_canvas_code
from utils.setup import db_stats, db_users, stats
from utils.time_converter import (
    format_datetime,
    format_timezone,
    get_datetimes_from_input,
    td_format,
)
from utils.timezoneslib import get_timezone
from utils.utils import in_executor


class Online(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="online")
    async def _online(
        self,
        inter: disnake.AppCmdInter,
        last: str = None,
        cooldown: bool = False,
        canvas_code: str = commands.param(default=None, name="canvas-code"),
        groupby: str = commands.Param(
            default=None, choices=["hour", "day", "month", "canvas"]
        ),
        before: str = None,
        after: str = None,
    ):
        """
        Show the online count history.

        Parameters
        ----------
        last: A time duration in the format ?y?mo?w?d?h?m?s.
        cooldown: To show the cooldown instead of the online count.
        canvas_code: To show the count during a selected canvas. (default: current)
        groupby: To show a bar graph with the average of each hour, day, month or canvas.
        before: To show the online count before a specific date. (format: YYYY-mm-dd HH:MM)
        after: To show the online count after a specific date. (format: YYYY-mm-dd HH:MM)
        """
        await inter.response.defer()
        await self.online(inter, last, cooldown, canvas_code, groupby, before, after)

    @commands.command(
        name="online",
        description="Show the online count history.",
        usage="[-last ?y?mo?w?d?h?m?s] [-cooldown] [-canvas <canvas code>] [-groupby hour|day|month|canvas] [-before <date time>] [-after <date time>]",
        help="""- `[-last|-l ?y?mo?w?d?h?m?s]` Show the count in the last x years/months/weeks/days/hours/minutes/seconds
                - `[-cooldown|-cd]`: show the cooldown instead of online count
                - `[-canvas|-c <canvas code>]`: show the count during a selected canvas (default: current)
                - `[-groupby|-g]`: show a bar graph with the average of each `hour`, `day`, `month` or `canvas`
                - `[-before <date time>]`: show the online count after a specific date (format YYYY-mm-dd HH:MM)
                - `[-after <date time>]`: show the online count after a specific date (format YYYY-mm-dd HH:MM)
            """,
    )
    async def p_online(self, ctx, *args):
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("-last", "-l", nargs="+", default=None)
        parser.add_argument("-cooldown", "-cd", action="store_true", default=False)
        parser.add_argument("-canvas", "-c", action="store", nargs="*", default=None)
        parser.add_argument(
            "-groupby",
            "-g",
            type=str.lower,
            choices=["hour", "day", "month", "canvas"],
            required=False,
        )
        parser.add_argument("-after", dest="after", nargs="+", default=None)
        parser.add_argument("-before", dest="before", nargs="+", default=None)
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.online(
                ctx,
                parsed_args.last,
                parsed_args.cooldown,
                parsed_args.canvas[0] if parsed_args.canvas else None,
                parsed_args.groupby,
                parsed_args.before,
                parsed_args.after,
            )

    async def online(
        self,
        ctx,
        last=None,
        cooldown=False,
        canvas_input=None,
        groupby=None,
        before=None,
        after=None,
    ):

        # get the user theme and timezone
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = discord_user["timezone"]
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        # check on time inputs
        if groupby in ["month", "canvas"] and not any([last, before, after]):
            dt1 = datetime.min.replace(tzinfo=timezone.utc)
            dt2 = datetime.now(timezone.utc)
        else:
            try:
                dt1, dt2 = get_datetimes_from_input(
                    get_timezone(user_timezone), last, before, after, 5
                )
            except ValueError as e:
                return await ctx.send(f":x: {e}")
        if datetime.now(timezone.utc) - dt2 < timedelta(minutes=5):
            last_bar_darker = True
        else:
            last_bar_darker = False

        # check on canvas code input
        current_canvas = await stats.get_canvas_code()
        if canvas_input is None:
            if not any([last, before, after]) and groupby not in ["month", "canvas"]:
                canvas = current_canvas
            else:
                canvas = None
        else:
            canvas = check_canvas_code(canvas_input)
            if canvas is None:
                return await ctx.send(
                    f":x: The given canvas code `{canvas_input}` is invalid."
                )
            if canvas != current_canvas:
                last_bar_darker = False

        data = await db_stats.get_general_stat(
            "online_count",
            dt1,
            dt2,
            canvas,
        )
        if not data:
            return await ctx.send(":x: No data found for this canvas.")
        t0 = data[0]["datetime"]
        t1 = data[-1]["datetime"]

        if groupby:
            if groupby == "month":
                format = "%Y-%m"
                user_timezone = None
            if groupby == "day":
                format = "%Y-%m-%d"
                user_timezone = None
            elif groupby == "hour":
                format = "%Y-%m-%d %H"

            # group by the format
            data_dict = {}
            for d in data:
                if d[0] is not None:
                    if groupby == "canvas":
                        key = "C" + d["canvas_code"]
                    else:
                        date_str = d["datetime"].strftime(format)
                        key = datetime.strptime(date_str, format)
                    if key in data_dict:
                        data_dict[key].append(int(d["value"]))
                    else:
                        data_dict[key] = [int(d["value"])]

            # get the average for each date
            dates = []
            online_counts = []
            for key, counts in data_dict.items():
                average = sum(counts) / len(counts)
                average = round(average, 2)
                dates.append(key)
                online_counts.append(average)
            if len(dates) <= 1:
                return await ctx.send("❌ The time frame given is too short.")
            dates = dates[1:]
            t0 = dates[0]
            if groupby == "canvas":
                t1 = dates[-1]

            online_counts = online_counts[1:]
            online_counts_without_none = online_counts
            # remove the last bar if it's the current one
            if (
                len(online_counts_without_none) > 1
                and online_counts[0] is not None
                and last_bar_darker
            ):
                online_counts_without_none = online_counts_without_none[:-1]
        else:
            online_counts = [
                (int(e["value"]) if e["value"] is not None else 0) for e in data
            ]
            dates = [e["datetime"] for e in data if e["datetime"]]
            online_counts_without_none = [
                int(e["value"]) for e in data if e["value"] is not None
            ]

        # make graph title
        if cooldown:
            title = "Pxls Cooldown"
        else:
            title = "Online Count"

        # get the cooldown for each online value if we have the cooldown arg
        if cooldown:
            online_counts = [stats.get_cd(count) for count in online_counts]
            online_counts_without_none = [
                stats.get_cd(count) for count in online_counts_without_none
            ]

        # make graph
        if groupby:
            # check that we arent plotting too many bars (limit: 10000 bars)
            nb_bars = len(online_counts)
            if nb_bars > 10000:
                return await ctx.send(
                    f":x: That's too many bars too show (**{nb_bars}**). <:bruhkitty:943594789532737586>"
                )
            online_counts_formatted = [
                round(o, 2) if o is not None else None for o in online_counts
            ]
            fig = await make_grouped_graph(
                dates, online_counts_formatted, theme, user_timezone, last_bar_darker
            )
        else:
            fig = await make_graph(dates, online_counts, theme, user_timezone)
        fig.update_layout(
            title="<span style='color:{};'>{}</span>".format(
                theme.get_palette(1)[0],
                title + (f" (average per {groupby})" if groupby else ""),
            )
        )
        img = await fig2img(fig)

        # make embed
        if groupby == "canvas":
            diff = ""
            t0 = f"`{t0}`"
            t1 = f"`{t1}`"

        else:
            if t1 == t0:
                diff = "\n• Time `0m`"
            else:
                diff = f"\n• Time `{td_format(t1 - t0, hide_seconds=True)}`"
            t0 = format_datetime(t0)
            t1 = format_datetime(t1)

        if len(online_counts_without_none) != 0:
            min_online = min(online_counts_without_none)
            max_online = max(online_counts_without_none)
            avg_online = sum(online_counts_without_none) / len(online_counts_without_none)
        else:
            min_online = max_online = avg_online = "N/A"
        description = "• Between {} and {}{}\n• Current {}: `{}`\n• Average: `{}`\n• Min: `{}` • Max: `{}`".format(
            t0,
            t1,
            diff,
            title,
            format_number(stats.online_count),
            format_number(avg_online),
            format_number(min_online),
            format_number(max_online),
        )
        emb = disnake.Embed(
            title=title,
            color=hex_str_to_int(theme.get_palette(1)[0]),
            description=description,
        )

        file = await image_to_file(img, "online_count.png", emb)
        await ctx.send(embed=emb, file=file)


@in_executor()
def make_graph(dates, values, theme, user_timezone=None):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc), tz) for d in dates]

    # create the graph
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_layout(showlegend=False)

    # trace the data
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines",
            name="Online Count",
            line=dict(width=2),
            marker=dict(color=theme.get_palette(1)[0], size=6),
        )
    )

    if theme.has_glow and len(values) < 1000:
        add_glow(fig, nb_glow_lines=3, alpha_lines=0.3, diff_linewidth=4)
    if theme.has_underglow:
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[min(values)] * len(values),
                mode="lines",
                marker=dict(color="rgba(0,0,0,0)", size=0),
                fill="tonexty",
                fillcolor=hex_to_rgba_string(theme.get_palette(1)[0], 0.06),
            )
        )
    return fig


@in_executor()
def make_grouped_graph(dates, values, theme, user_timezone=None, last_bar_darker=True):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    # dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc), tz) for d in dates]

    # create the graph and style
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_yaxes(rangemode="tozero")

    # add an outline of the bg color to the text above the bars
    nb_bars = len(values)
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
            theme.background_color, v, 2
        )
        if nb_bars <= 200
        else None
        for v in values
    ]

    color = theme.get_palette(1)[0]
    bar_colors = [color for _ in values]
    if last_bar_darker:
        bar_colors[-1] = theme.off_color

    # trace the user data
    if theme.has_underglow:
        # different style if the theme has underglow
        fig.add_trace(
            go.Bar(
                name="Online Count",
                x=dates,
                y=values,
                text=text,
                textposition="outside",
                marker_color=[hex_to_rgba_string(c, 0.15) for c in bar_colors],
                marker_line_color=bar_colors,
                marker_line_width=2.5,
                textfont=dict(color=bar_colors, size=40),
                cliponaxis=False,
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                name="Online Count",
                x=dates,
                y=values,
                text=text,
                textposition="outside",
                marker=dict(color=bar_colors, opacity=0.9),
                textfont=dict(color=bar_colors, size=40),
                cliponaxis=False,
                marker_line_width=0,
            )
        )
    return fig


def setup(bot: commands.Bot):
    bot.add_cog(Online(bot))
