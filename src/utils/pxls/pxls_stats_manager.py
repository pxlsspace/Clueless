import math
import uuid
from datetime import datetime

import numpy as np
import pytz
from PIL import ImageColor

from utils.log import get_logger
from utils.utils import get_content

logger = get_logger(__name__)


class PxlsStatsManager:
    """A helper to get data from pxls.space/stats"""

    def __init__(self, db_conn, pxls_url_api):
        self.base_url = pxls_url_api + "/"
        self.stats_json = {}
        self.board_info = {}
        self.current_canvas_code = None
        self.online_count = None
        self.db_conn = db_conn

        self.board_array = None
        self.virginmap_array = None
        self.placemap_array = None
        self.palette = None

    async def refresh(self):

        status = False
        try:
            self.board_info = await self.query("info", "json")
        except ValueError as e:
            logger.error(f"Couldn't update board info: {e}")
        except Exception:
            logger.exception("Couldn't update board info:")

        try:
            count = await self.fetch_online_count()
            self.online_count = count
        except ValueError as e:
            logger.error(f"Couldn't fetch online count: {e}")
            self.online_count = None
        except Exception:
            logger.exception("Couldn't fetch online count:")

        try:
            self.stats_json = await self.query("stats/stats.json", "json")
            status = True
        except ValueError as e:
            logger.error(f"Couldn't update stats.json: {e}")
        except Exception:
            logger.exception("Couldn't update stats.json:")

        try:
            await self.update_palette()
        except Exception:
            logger.exception("Couldn't update the palette:")
        return status

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

    def get_palette(self, restricted=False):
        """Get the current palette, set restricted to True to get unplaceable colors too"""
        if restricted:
            return self.palette
        else:
            # get the palette without the restricted colors
            palette = []
            for color in self.palette:
                if "usable" in color:
                    if color["usable"]:
                        palette.append(color)
                elif "restricted" in color:
                    if not color["restricted"]:
                        palette.append(color)
                else:
                    palette.append(color)
            return palette

    async def update_palette(self):
        self.palette = None
        try:
            self.palette = self.board_info["palette"]
        except Exception:
            try:
                self.palette = self.stats_json["board_info"]["palette"]
            except Exception:
                pass
        if self.palette is None:
            # couldn't get the palette from the board info or stats info
            # so we get the last palette saved in the database
            self.palette = await self.get_db_palette()
        return self.palette

    async def get_db_palette(self):
        """Get the last palette saved in the database"""
        canvas_code = await self.get_canvas_code()
        sql = """
            SELECT color_id,color_name,color_hex
            FROM palette_color
            WHERE canvas_code = ?
            ORDER BY color_id
        """
        db_palette = await self.db_conn.sql_select(sql, canvas_code)
        res_palette = []
        for color in db_palette:
            res_palette.append(dict(name=color["color_name"], value=color["color_hex"]))
        return res_palette

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
            palette = [f"#{c['value']}" for c in self.get_palette(restricted=True)]
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

        pxls_validate = str(uuid.uuid4())
        cookies = {"pxls-validate": pxls_validate}
        return await get_content(url, content_type, cookies=cookies)

    def get_cd(self, online_count: int, multiplier: float = None):
        """Get the cooldown for a given amount of online users"""
        try:
            # Try to get the cooldown info from the board info
            cd_info = self.board_info["cooldownInfo"]
            if cd_info["type"] == "activity":
                activity_cd = cd_info["activityCooldown"]
                steepness = activity_cd["steepness"]
                _multiplier = activity_cd["multiplier"]
                global_offset = activity_cd["globalOffset"]
                user_offset = activity_cd["userOffset"]
            else:
                return cd_info["staticCooldownSeconds"]
        except Exception:
            # use the default values in case of error
            steepness = 2.5
            _multiplier = 1.0
            global_offset = 6.5
            user_offset = 11.96

        if multiplier is None:
            multiplier = _multiplier

        cooldown = (
            steepness * math.sqrt(online_count + user_offset) + global_offset
        ) * multiplier
        return cooldown

    def get_cd_multiplier(self):
        try:
            return self.board_info["cooldownInfo"]["activityCooldown"]["multiplier"]
        except Exception:
            return 1.0
