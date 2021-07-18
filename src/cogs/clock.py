from discord.ext import commands, tasks
from utils.database import *
from datetime import datetime
from utils.setup import stats
from utils.time_converter import local_to_utc

class Clock(commands.Cog):
    """ A class used to manage background periodic tasks.

    It is used to update the stats object periodically. """


    def __init__(self,client):
        self.client = client
        self.update_stats.start()
        self.stats = stats

    def cog_unload(self):
        self.update_stats.cancel()

    @tasks.loop(seconds=60)
    async def update_stats(self):
        now = datetime.now()
        min = now.strftime("%M")

        if min in ['01','16','31','46']:
            now = now.strftime("[%H:%M:%S]")
            print(now +": updating stats data.",end='',flush=True)

            # refreshing stats json
            self.stats.refresh()
            if self.stats.stats_json == None:
                print(time + ": stats page unreachable")
                return
            print(".",end='',flush=True)

            # updating database with the new data
            self.update_database()
            print(".",end='',flush=True)

            await self.check_milestones()
            print(" done!")


    # wait for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()
        # update the stats on start
        self.stats.refresh()
        self.update_database()
        await self.check_milestones()

    async def check_milestones(self):
        ''' Send alerts in all the servers following a user if they hit a milestone. '''
        users = get_all_users()
        for user in users:
            name = user[0]
            old_count = user[1]
            new_count = self.stats.get_alltime_stat(name)
            if new_count%1000 < old_count%1000:
                # send alert in all the servers tracking user
                channels = get_all_channels(name)
                for c in channels:
                    if c != None:
                        channel = self.client.get_channel(c)
                        await channel.send("New milestone for **"+name+"**! New count: "+str(new_count))
            if new_count != old_count:
                # update the new count in the db
                update_pixel_count(name,new_count)

    def update_database(self):
        ''' Update the database with the new /stats data. '''
        # get the 'last updated' datetime and its timezone
        lastupdated_string = self.stats.get_last_updated()
        lastupdated = self.stats.last_updated_to_date(lastupdated_string)
        # Convert /stats to a naive datetime in UTC
        lastupdated = local_to_utc(lastupdated)
        lastupdated = lastupdated.replace(tzinfo=None) #timezone naive as UTC

        alltime_stats = self.stats.get_all_alltime_stats()
        canvas_stats = self.stats.get_all_canvas_stats()

        update_all_pxls_stats(alltime_stats,canvas_stats,lastupdated)
    

def setup(client):
    client.add_cog(Clock(client))
