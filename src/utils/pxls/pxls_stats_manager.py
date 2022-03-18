import numpy as np
import os
import pytz
from PIL import ImageColor
from dotenv import load_dotenv, set_key, find_dotenv
from datetime import datetime

from utils.utils import get_content


class PxlsStatsManager:
    """A helper to get data from pxls.space/stats"""

    def __init__(self, db_conn):
        self.base_url = "http://pxls.space/"
        self.stats_json = {}
        self.board_info = {}
        self.current_canvas_code = None
        self.online_count = None
        self.db_conn = db_conn

        self.board_array = None
        self.virginmap_array = None
        self.placemap_array = None
        load_dotenv()
        mult = os.environ.get("CD_MULTIPLIER")
        self.cd_multiplier = float(mult) if mult else 1

    async def refresh(self):
        try:
            self.board_info = await self.query("info", "json")
            count = await self.fetch_online_count()
            self.online_count = count
        except Exception:
            pass

        self.stats_json = await self.query("stats/stats.json", "json")

    def get_general_stats(self):
        general = self.stats_json["general"].copy()
        general.pop("nth_list")
        return general

    def get_last_updated(self):
        return self.stats_json["generatedAt"]

    @staticmethod
    def last_updated_to_date(lastupdated):
        tz_string = lastupdated[23:-1]
        tz = pytz.timezone(tz_string)

        lastupdated = lastupdated[:21]
        date_time_obj = datetime.strptime(lastupdated, "%Y/%m/%d - %H:%M:%S")
        date_time_obj = tz.localize(date_time_obj)
        return date_time_obj

    def get_alltime_stat(self, name):
        at_table = self.stats_json["toplist"]["alltime"]
        for user in at_table:
            if user["username"] == name:
                return user["pixels"]
        return None

    def get_canvas_stat(self, name):
        at_table = self.stats_json["toplist"]["canvas"]
        for user in at_table:
            if user["username"] == name:
                return user["pixels"]
        return None

    def get_all_alltime_stats(self):
        return self.stats_json["toplist"]["alltime"]

    def get_all_canvas_stats(self):
        return self.stats_json["toplist"]["canvas"]

    def get_palette(self):
        try:
            return self.board_info["palette"]
        except Exception:
            return self.stats_json["board_info"]["palette"]

    async def get_canvas_code(self):
        canvas_code = None
        try:
            # Try to get the canvas code from the board info
            canvas_code = self.board_info["canvasCode"]
        except Exception:
            try:
                # Try to get the canvas code from the stats.json
                canvas_code = self.stats_json["board_info"]["canvasCode"]
            except Exception:
                pass
        if canvas_code is None:
            # Use the last canvas code saved in the database
            rows = await self.db_conn.sql_select(
                "SELECT canvas_code, MAX(datetime) FROM record"
            )
            canvas_code = rows[0][0]
        return canvas_code

    async def fetch_online_count(self):
        response_json = await self.query("users", "json")
        count = response_json["count"]
        self.online_count = count
        return count

    async def update_online_count(self, count):
        """update the online count in the database"""
        canvas_code = await self.get_canvas_code()
        dt = datetime.utcnow().replace(microsecond=0)
        sql = """INSERT INTO pxls_general_stat(stat_name, value ,canvas_code, datetime)
                VALUES(?,?,?,?)"""
        await self.db_conn.sql_update(sql, ("online_count", count, canvas_code, dt))

    def palettize_array(self, array, palette=None):
        """Convert a numpy array of palette indexes to a color numpy array
        (RGBA). If a palette is given, it will be used to map the array, if not
        the current pxls palette will be used"""
        colors_list = []
        if not palette:
            palette = [f"#{c['value']}" for c in self.get_palette()]
        for color in palette:
            rgb = ImageColor.getcolor(color, "RGBA")
            colors_list.append(rgb)
        colors_dict = dict(enumerate(colors_list))
        colors_dict[255] = (0, 0, 0, 0)

        img = np.stack(np.vectorize(colors_dict.get)(array), axis=-1)
        return img.astype(np.uint8)

    async def fetch_board(self):
        "fetch the board with a get request"
        board_bytes = await self.query("boarddata", "bytes")
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"], self.board_info["width"]
        )
        self.board_array = board_array
        return board_array

    async def fetch_virginmap(self):
        "fetch the virgin map with a get request"
        board_bytes = await self.query("virginmap", "bytes")
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"], self.board_info["width"]
        )
        self.virginmap_array = board_array
        return board_array

    async def fetch_heatmap(self):
        "fetch the heatmap with a get request"
        board_bytes = await self.query("heatmap", "bytes")
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"], self.board_info["width"]
        )
        return board_array

    async def fetch_initial_canvas(self):
        "fetch the initial canvas with a get request"
        board_bytes = await self.query("initialboarddata", "bytes")
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"], self.board_info["width"]
        )
        return board_array

    async def fetch_placemap(self):
        "fetch the placemap with a get request"
        board_bytes = await self.query("placemap", "bytes")
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"], self.board_info["width"]
        )
        self.placemap_array = board_array
        return board_array

    async def get_placable_board(self):
        """fetch the board as an index array and use the placemap as a mask"""
        canvas_array = self.board_array
        placemap_array = self.placemap_array
        placeable_board = canvas_array.copy()
        placeable_board[placemap_array != 0] = 255
        placeable_board[placemap_array == 0] = canvas_array[placemap_array == 0]

        return placeable_board

    def update_board_pixel(self, x, y, color):
        self.board_array[y, x] = color

    def update_virginmap_pixel(self, x, y, color):
        self.virginmap_array[y, x] = 0

    async def query(self, endpoint, content_type):
        url = self.base_url + endpoint
        return await get_content(url, content_type)

    def set_cd_multiplier(self, new_multiplier: float):
        """Change the cooldown multiplier."""
        file = find_dotenv()
        set_key(file, "CD_MULTIPLIER", str(new_multiplier))
        self.cd_multiplier = new_multiplier
