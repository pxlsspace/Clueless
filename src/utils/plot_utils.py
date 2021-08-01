import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
from PIL import Image

""" General layout and styles for the plots """

BACKGROUND_COLOR = "#202225"
GRID_COLOR = "#b9bbbe"
COLORS = px.colors.qualitative.Pastel


layout = go.Layout(
    paper_bgcolor=BACKGROUND_COLOR,
    plot_bgcolor=BACKGROUND_COLOR,
    font_color=GRID_COLOR,
    font_size=35,
    yaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR,tickformat=',d'),
    xaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR),
    margin=dict(b=150),
    annotations=[
         go.layout.Annotation(
            x = 1,
            y = -0.1,
            text = "All the dates and times displayed are in the UTC timezone.", 
            showarrow = False,
            xref='paper',
            yref='paper', 
            xanchor='right',
            yanchor='auto',
            xshift=0,
            yshift=-80,
            font=dict(color="#777f8c")
        )
    ]
)

layout_without_annotation = go.Layout(
    paper_bgcolor=BACKGROUND_COLOR,
    plot_bgcolor=BACKGROUND_COLOR,
    font_color=GRID_COLOR,
    font_size=35,
    yaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR,tickformat=',d'),
    xaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR),
)

def fig2img(fig,width=2000,height=900,scale=1):
    buf = BytesIO()
    fig.write_image(buf,format="png",width=width,height=height,scale=scale)
    img = Image.open(buf)
    return img
