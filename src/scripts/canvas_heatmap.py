import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.plot_utils import get_gradient_palette, matplotlib_to_plotly  # noqa: E402
from utils.pxls.archives import (  # noqa: E402
    check_canvas_code,
    get_canvas_image,
    get_log_file,
)
from utils.setup import stats  # noqa: E402


def get_top_N(heatmap_array, N=10):
    """Print a leaderboard of the N most replaced pixels"""
    part = np.argpartition(heatmap_array.ravel(), -N)[-N:]
    y_coords = part // heatmap_array.shape[1]
    x_coords = part % heatmap_array.shape[1]
    tops = heatmap_array[y_coords, x_coords]

    top_list = [(x_coords[i], y_coords[i], tops[i]) for i in range(N)]
    top_list.sort(key=lambda i: i[-1], reverse=True)

    for i in range(N):
        x, y, placed = top_list[i]
        print(f"{i+1}.) coords: ({x}, {y}), placed: {placed}")


def canvas_heatmap(canvas_code):
    """Make a heatmap of replaced pixels."""
    log_file = get_log_file(canvas_code)
    canvas_image = get_canvas_image(canvas_code)
    heatmap_array = np.full((canvas_image.height, canvas_image.width), 0)

    with open(log_file) as logfile:
        for line in logfile:
            [date, random_hash, x, y, color_index, action] = line.split("\t")
            action = action.strip()
            x = int(x)
            y = int(y)
            if action == "user place":
                heatmap_array[y, x] += 1
            if action == "user undo":
                heatmap_array[y, x] -= 1

    # from 1 to 20: plasma palette (dark blue -> yellow)
    heatmap_palette = matplotlib_to_plotly("plasma", 20)
    # from 21 to 500: yellow to white gradient
    heatmap_palette += get_gradient_palette(["#EFF821", "#FFFFFF"], 500)
    # 500+: white
    heatmap_palette += [heatmap_palette[-1]] * 10000
    # untouched pixels: black
    heatmap_palette.insert(0, "#000000")

    get_top_N(heatmap_array)

    heatmap = stats.palettize_array(heatmap_array, heatmap_palette)
    heatmap_image = Image.fromarray(heatmap)
    heatmap_image.show()
    heatmap_image.save("heatmap.png", "PNG")
    print("Heatmap saved as 'heatmap.png'")


if __name__ == "__main__":
    canvas_code = input("Canvas code? (ex: '57'):\n")
    canvas_code = check_canvas_code(canvas_code)
    if not canvas_code or not get_log_file(canvas_code):
        print("Invalid canvas code.")
    else:
        print("Making the heatmap...")
        canvas_heatmap(canvas_code)
