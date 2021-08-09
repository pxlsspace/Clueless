from datetime import datetime
import pytz
from utils.utils import get_content

class PxlsStatsManager():
    ''' A helper to get data from pxls.space/stats'''

    def __init__(self):
        self.base_url = "http://pxls.space/"
        self.stats_json = {}
        self.current_canvas_code = None

    async def refresh(self):
        response_json = await self.query("stats/stats.json","json")
        self.stats_json = response_json
        self.current_canvas_code = await self.refresh_canvas_code()
    
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
        return self.stats_json["board_info"]["palette"]

    async def refresh_canvas_code(self):
        response_json = await self.query('info','json')
        return response_json["canvasCode"]
    
    def get_canvas_code(self):
        return self.current_canvas_code

    async def get_online_count(self):
        response_json = await self.query('users','json')
        return response_json["count"]

    async def query(self,endpoint,content_type):
        url = self.base_url + endpoint
        return await get_content(url,content_type) 

if __name__ == "__main__":
    ''' test/debug code'''
    p = PxlsStatsManager()
    for user in p.get_all_canvas_stats():
        name = user["username"]
        alltime_count = user["pixels"]
        print(f'{name}: {alltime_count} pixels')

        

    
