from datetime import datetime
from PIL import ImageColor
import pytz
import numpy as np

from utils.utils import get_content

class PxlsStatsManager():
    ''' A helper to get data from pxls.space/stats'''

    def __init__(self,db_conn):
        self.base_url = "http://pxls.space/"
        self.stats_json = {}
        self.board_info = {}
        self.current_canvas_code = None
        self.board_array = None
        self.db_conn = db_conn

    async def refresh(self):
        try:
            self.board_info = await self.query("info","json")
            self.board_array = await self.fetch_board()
        except:
            pass

        self.stats_json = await self.query("stats/stats.json","json")


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
        date_time_obj = datetime.strptime(lastupdated, '%Y/%m/%d - %H:%M:%S')
        date_time_obj = tz.localize(date_time_obj)
        return date_time_obj

    def get_alltime_stat(self,name):
        at_table = self.stats_json["toplist"]["alltime"]
        for user in at_table:
            if user["username"] == name:
                return user["pixels"]
        return None

    def get_canvas_stat(self,name):
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
        except:
            return self.stats_json["board_info"]["palette"]
    
    async def get_canvas_code(self):
        try:
            return self.board_info["canvasCode"]
        except:
            rows= await self.db_conn.sql_select("SELECT canvas_code,MAX(datetime) FROM record")
            canvas_code = rows[0][0]
            return canvas_code
    async def get_online_count(self):
        response_json = await self.query('users','json')
        return response_json["count"]

    def palettize_array(self,array):
        """ Convert a numpy array of palette indexes to a color numpy array
        (RGBA) """
        colors_list = []
        for color in self.get_palette():
            rgb = ImageColor.getcolor("#" + color["value"],'RGBA')
            colors_list.append(rgb)
        colors_dict = dict(enumerate(colors_list))
        colors_dict[255] = (0, 0, 0, 0)

        img = np.stack(np.vectorize(colors_dict.get)(array),
             axis=-1)
        return img.astype(np.uint8)

    async def fetch_board(self):
        "fetch the board with a get request"
        board_bytes = await self.query('boarddata','bytes')
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"],self.board_info["width"])
        return board_array

    async def fetch_virginmap(self):
        "fetch the virgin map with a get request"
        board_bytes = await self.query('virginmap','bytes')
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"],self.board_info["width"])
        return board_array

    async def fetch_initial_canvas(self):
        "fetch the initial canvas with a get request"
        board_bytes = await self.query('initialboarddata','bytes')
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"],self.board_info["width"])
        return board_array

    async def fetch_placemap(self):
        "fetch the placemap with a get request"
        board_bytes = await self.query('placemap','bytes')
        board_array = np.asarray(list(board_bytes), dtype=np.uint8).reshape(
            self.board_info["height"],self.board_info["width"])
        return board_array

    async def query(self,endpoint,content_type):
        url = self.base_url + endpoint
        return await get_content(url,content_type) 
