import discord
from datetime import datetime
from discord.ext import commands
import plotly.graph_objects as go

from utils.time_converter import format_datetime, str_to_td
from utils.discord_utils import image_to_file
from utils.cooldown import get_cd
from utils.plot_utils import layout, COLORS, fig2img
from utils.setup import stats, db_stats_manager as db_stats

class Online(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @commands.command(
        description = "Show the online count history.",
        usage = "[-cd] [-last ?d?h?m?s]")
    async def online(self,ctx,*args):
        last = "1d"
        if ("-last" in args):
            i = args.index("-last")
            if i+1 >= len(args):
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
            last = args[i+1]

        if "-cd" in args:
            title = "Pxls Cooldown"
        else:
            title = "Online Count"

        input_time = str_to_td(last)
        if not input_time:
            return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
        data = await db_stats.get_general_stat("online_count",datetime.utcnow()-input_time)

        online_counts = [int(e[0]) for e in data if e[0] != None]
        dates = [e[1] for e in data if e[0] != None]

        current_count = await stats.get_online_count()
        online_counts.insert(0,int(current_count))
        dates.insert(0,datetime.utcnow())

        if "-cd" in args:
            online_counts = [round(get_cd(count),2) for count in online_counts]
            current_count = round(get_cd(current_count),2)

        fig = make_graph(dates,online_counts)
        fig.update_layout(title=f"<span style='color:{COLORS[0]};'>{title}</span>")

        img = fig2img(fig)

        description = 'Values between {} and {}\nCurrent {}: `{}`\nAverage: `{}`\nMin: `{}`  Max: `{}`'.format(
                format_datetime(dates[-1]),
                format_datetime(dates[0]),
                title,
                current_count,
                round(sum(online_counts)/len(online_counts),2),
                min(online_counts),
                max(online_counts)
            )
        emb = discord.Embed(
            title = title + " History",
            color=0x66c5cc,
            description = description
        )

        file = image_to_file(img,"online_count.png",emb)
        await ctx.send(embed=emb,file=file)

def make_graph(dates,values):

    # create the graph
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)

    # trace the data
    fig.add_trace(go.Scatter(
        x=dates,
        y=values,
        mode='lines',
        name="Online Count",
        line=dict(width=4),
        marker=dict(color= COLORS[0],size=6)
        )
    )
    return fig

def setup(client):
    client.add_cog(Online(client))
    