import requests
import json
from datetime import datetime

class PxlsStats():
    ''' A helper to get data from pxls.space/stats'''

    def __init__(self):
        self.stats_url = "http://pxls.space/stats/stats.json"
        self.stats_json = {}
        self.refresh()

    def refresh(self):
        r = requests.get(self.stats_url)
        if 200 > r.status_code or r.status_code > 299:
            print(str(r.status_code))
            self.stats_json = None

        self.stats_json = json.loads(r.text)
    
    def get_general_stats(self):
        general = self.stats_json["general"]
        general.pop("nth_list")
        return general

    def get_last_updated(self):
        return self.stats_json["generatedAt"]

    @staticmethod
    def last_updated_to_date(lastupdated):
        lastupdated = lastupdated[:21]
        date_time_obj = datetime.strptime(lastupdated, '%Y/%m/%d - %H:%M:%S')
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

if __name__ == "__main__":
    ''' test/debug code'''
    p = PxlsStats()
    for user in p.get_all_canvas_stats():
        name = user["username"]
        alltime_count = user["pixels"]
        print(f'{name}: {alltime_count} pixels')

        

    
