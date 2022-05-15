import disnake
from datetime import datetime
from disnake.ext import commands
import plotly.graph_objects as go
from datetime import timezone

from utils.arguments_parser import MyParser
from utils.image.image_utils import hex_str_to_int
from utils.time_converter import format_datetime, str_to_td, format_timezone
from utils.discord_utils import format_number, image_to_file
from utils.plot_utils import add_glow, get_theme, fig2img, hex_to_rgba_string
from utils.setup import stats, db_stats, db_users
from utils.timezoneslib import get_timezone
from utils.utils import in_executor


class Online(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="online")
    async def _online(
        self,
        inter: disnake.AppCmdInter,
        cooldown: bool = False,
        last: str = None,
        canvas: bool = False,
        groupby: str = commands.Param(default=None, choices=["day", "hour"]),
    ):
        """
        Show the online count history.

        Parameters
        ----------
        cooldown: To show the cooldown instead of the online count.
        last: A time duration in the format ?y?mo?w?d?h?m?s.
        canvas: To show the count during the whole current canvas.
        groupby: To show a bar graph with the average of each day or hour.
        """
        await inter.response.defer()
        args = ()
        if cooldown:
            args += ("-cooldown",)
        if last:
            args += ("-last", last)
        if canvas:
            args += ("-canvas",)
        if groupby:
            args += ("-groupby", groupby)
        await self.online(inter, *args)

    @commands.command(
        name="online",
        description="Show the online count history.",
        usage="[-cooldown] [-canvas] [-groupby day/hour] [-last ?y?mo?w?d?h?m?s]",
        help="""- `[-cooldown|-cd]`: show the cooldown instead of online count
                - `[-canvas|-c]`: show the count during the whole canvas
                - `[-groupby|-g]`: show a bar graph with the average of each `day` or `hour`
                - `[-last|-l ?y?mo?w?d?h?m?s]` Show the count in the last x years/months/weeks/days/hours/minutes/seconds (default: 1d)""",
    )
    async def p_online(self, ctx, *args):
        async with ctx.typing():
            await self.online(ctx, *args)

    async def online(self, ctx, *args):
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("-last", "-l", nargs="+", default=None)
        parser.add_argument("-cooldown", "-cd", action="store_true", default=False)
        parser.add_argument("-canvas", "-c", action="store_true", default=False)
        parser.add_argument("-groupby", "-g", choices=["day", "hour"], required=False)
        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        if parsed_args.last is None and parsed_args.canvas:
            last = "10000d"
        elif parsed_args.last is None:
            last = "1d"
        else:
            last = parsed_args.last

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = discord_user["timezone"]
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        input_time = str_to_td(last)
        if not input_time:
            return await ctx.send(
                "❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
            )

        data = await db_stats.get_general_stat(
            "online_count",
            datetime.utcnow() - input_time,
            datetime.utcnow(),
            parsed_args.canvas,
        )
        current_count = stats.online_count

        if parsed_args.groupby:
            groupby = parsed_args.groupby
            if groupby == "day":
                format = "%Y-%m-%d"
                user_timezone = None
            elif groupby == "hour":
                format = "%Y-%m-%d %H"

            # group by the format
            data_dict = {}
            for d in data:
                if d[0] is not None:
                    date_str = d["datetime"].strftime(format)
                    key = datetime.strptime(date_str, format)
                    if key in data_dict:
                        data_dict[key].append(int(d[0]))
                    else:
                        data_dict[key] = [int(d[0])]

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
            dates = dates[:-1]
            online_counts = online_counts[:-1]
            online_counts_without_none = online_counts
        else:
            online_counts = [(int(e[0]) if e[0] is not None else 0) for e in data]
            dates = [e[1] for e in data if e[0]]
            online_counts_without_none = [int(e[0]) for e in data if e[0] is not None]
            if current_count:
                online_counts.insert(0, int(current_count))
                dates.insert(0, datetime.utcnow())

        # make graph title
        if parsed_args.cooldown:
            title = "Pxls Cooldown"
        else:
            title = "Online Count"

        # get the cooldown for each online value if we have the cooldown arg
        if parsed_args.cooldown:
            online_counts = [stats.get_cd(count) for count in online_counts]
            online_counts_without_none = [
                stats.get_cd(count) for count in online_counts_without_none
            ]

            if current_count:
                current_count = round(stats.get_cd(current_count), 2)

        # make graph
        if parsed_args.groupby:
            # check that we arent plotting too many bars (limit: 10000 bars)
            nb_bars = len(online_counts)
            if nb_bars > 10000:
                return await ctx.send(
                    f":x: That's too many bars too show (**{nb_bars}**). <:bruhkitty:943594789532737586>"
                )
            fig = await make_grouped_graph(dates, online_counts, theme, user_timezone)
        else:
            fig = await make_graph(dates, online_counts, theme, user_timezone)
        fig.update_layout(
            title="<span style='color:{};'>{}</span>".format(
                theme.get_palette(1)[0],
                title + (f" (average per {groupby})" if parsed_args.groupby else ""),
            )
        )
        img = await fig2img(fig)

        # make embed
        description = "• Between {} and {}\n• Current {}: `{}`\n• Average: `{}`\n• Min: `{}` • Max: `{}`".format(
            format_datetime(dates[-1]),
            format_datetime(dates[0]),
            title,
            format_number(current_count),
            format_number(
                sum(online_counts_without_none) / len(online_counts_without_none)
            ),
            format_number(min(online_counts_without_none)),
            format_number(max(online_counts_without_none)),
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
def make_grouped_graph(dates, values, theme, user_timezone=None):

    # get the timezone information
    tz = get_timezone(user_timezone)
    if tz is None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc), tz) for d in dates]

    # create the graph and style
    color = theme.get_palette(1)[0]
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
                marker_color=hex_to_rgba_string(color, 0.15),
                marker_line_color=color,
                marker_line_width=2.5,
                textfont=dict(color=color, size=40),
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
                marker=dict(color=color, opacity=0.9),
                textfont=dict(color=color, size=40),
                cliponaxis=False,
            )
        )
    return fig


def setup(bot: commands.Bot):
    bot.add_cog(Online(bot))
