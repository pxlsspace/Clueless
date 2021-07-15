import plotly.graph_objects as go
import plotly.express as px
from utils.database import sql_select
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta,timezone
from discord.ext import commands
import discord

class StatsGraph(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command()
    async def statsgraph(self,ctx,*users):

        graph = get_stats_graph(users,True,datetime.now(timezone.utc)-timedelta(days=1))
        img = fig2img(graph)
        # create and send the embed with the color table, the pie chart and the image sent as thumbnail
        emb = discord.Embed(title="Stats Graph")
        with BytesIO() as image_binary:
            img.save(image_binary, 'PNG')
            image_binary.seek(0)
            image = discord.File(image_binary, filename='piechart.png')
            emb.set_image(url=f'attachment://piechart.png')
            await ctx.send(file=image,embed=emb)

def setup(client):
    client.add_cog(StatsGraph(client))

def fig2img(fig):
    buf = BytesIO()
    fig.write_image(buf,format="png",width=1600,height=900,scale=1.5)
    img = Image.open(buf)
    return img

def get_stats_graph(user_list,canvas,date1,date2=datetime.now(timezone.utc)):

    # create the graph layout and style
    layout = go.Layout(
        paper_bgcolor='RGBA(0,0,0,255)',
        plot_bgcolor='#00172D',
        font_color="#bfe6ff",
        font_size=25,
        font=dict(family="Courier New")
    )
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#bfe6ff')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#bfe6ff')
    colors = px.colors.qualitative.Pastel

    for i,user in enumerate(user_list):
        # get the data
        stats = sql_select("""SELECT * FROM pxls_user_stats
                            WHERE name = ?
                            AND date > ?
                            AND date < ?""",(user,date1,date2))
        if not stats:
            continue

        dates = [stat[3] for stat in stats]
        if canvas:
            pixels = [stat[2] for stat in stats]
        else:
            pixels = [stat[1] for stat in stats]

        # tracer the user data
        fig.add_trace(go.Scatter(
            x=dates,
            y=pixels,
            mode='lines+markers' if i != len(user_list)-1 else 'lines+markers',
            name=user,
            line=dict(width=3),
            marker=dict(color= colors[i],size=3)
            )
        )
        # add the name at the end of the line
        fig.add_annotation(
            xanchor='left',
            yanchor='middle',
            xshift=10,
            x = dates[-1],
            y = pixels[-1],
            text = user,
            showarrow = False,
            font = dict(color= colors[i],size=30)
        )
    return fig