import os
import numpy as np
from hashlib import sha256
from PIL import Image

from utils.utils import in_executor
from utils.setup import db_stats, stats

basepath = os.path.dirname(__file__)
CANVASES_FOLDER = os.path.abspath(
    os.path.join(basepath, "..", "..", "..", "resources", "canvases")
)


def get_log_file(input_canvas_code):
    for canvas_code in os.listdir(CANVASES_FOLDER):
        if canvas_code == input_canvas_code:
            for root, dirs, files in os.walk(os.path.join(CANVASES_FOLDER, canvas_code)):
                for file in files:
                    if file.endswith(".log"):
                        return os.path.join(root, file)
    return None


def get_canvas_image(input_canvas_code):
    for canvas_code in os.listdir(CANVASES_FOLDER):
        if canvas_code == input_canvas_code:
            for root, dirs, files in os.walk(os.path.join(CANVASES_FOLDER, canvas_code)):
                for file in files:
                    if file == os.path.join(f"final c{canvas_code}.png"):
                        return Image.open(os.path.join(root, file))
    return None


@in_executor()
def parse_log_file(log_file, user_key, res_array):
    nb_undo = 0
    nb_placed = 0
    nb_replaced_by_others = 0
    nb_replaced_by_you = 0
    survived_map = res_array.copy()
    with open(log_file) as logfile:
        for line in logfile:
            [date, random_hash, x, y, color_index, action] = line.split("\t")
            digest_format = ",".join([date, x, y, color_index, user_key])
            digested = sha256(digest_format.encode("utf-8")).hexdigest()

            action = action.strip()
            x = int(x)
            y = int(y)
            color_index = int(color_index)
            if digested == random_hash:
                # This is my pixel!
                if action == "user place":
                    nb_placed += 1
                    if survived_map[y, x] != 255:
                        nb_replaced_by_you += 1
                    res_array[y, x] = color_index
                    survived_map[y, x] = color_index
                elif action == "user undo":
                    nb_undo += 1
                    res_array[y, x] = 255
                    survived_map[y, x] = 255
            else:
                if survived_map[y, x] != 255:
                    nb_replaced_by_others += 1
                    survived_map[y, x] = 255
    return res_array, nb_undo, nb_placed, nb_replaced_by_others, nb_replaced_by_you


async def get_user_placemap(canvas_code, user_key):
    """Get the user placemap and some stats about it."""
    log_file = get_log_file(canvas_code)

    canvas_image = get_canvas_image(canvas_code)
    res_array = np.full((canvas_image.height, canvas_image.width), 255)

    palette = await db_stats.get_palette(canvas_code)
    if palette is None:
        raise ValueError(f"Palette not found for c{canvas_code}.")
    palette = [("#" + c["color_hex"]) for c in palette]

    (
        res_array,
        nb_undo,
        nb_placed,
        nb_replaced_by_others,
        nb_replaced_by_you,
    ) = await parse_log_file(log_file, user_key, res_array)
    res_array = stats.palettize_array(res_array, palette)
    res_image = Image.fromarray(res_array)
    return res_image, nb_undo, nb_placed, nb_replaced_by_others, nb_replaced_by_you
