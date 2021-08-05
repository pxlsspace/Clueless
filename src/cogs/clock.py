from discord.ext import commands, tasks
from datetime import datetime
from utils.setup import stats, db_stats_manager as db_stats, db_servers_manager as db_servers
from utils.time_converter import local_to_utc

class Clock(commands.Cog):
    """ A class used to manage background periodic tasks.

    It is used to update the stats object periodically. """


    def __init__(self,client):
        self.client = client
        self.update_stats.start()
        self.update_online_count.start()

    def cog_unload(self):
        self.update_stats.cancel()
        self.update_online_count.cancel()

    @tasks.loop(seconds=60)
    async def update_stats(self):
        now = datetime.now()
        min = now.strftime("%M")

        if min in ['01','16','31','46']:
            now = now.strftime("[%H:%M:%S]")
            print(now +": updating stats data.",end='',flush=True)

            # refreshing stats json
            await stats.refresh()
            if stats.stats_json == None:
                print(now + ": stats page unreachable")
                return
            print(".",end='',flush=True)

            # updating database with the new data
            await self.save_stats()
            print(".",end='',flush=True)

            await self.check_milestones()
            print(" done!")

    # wait for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()
        # update the stats on start
        await stats.refresh()
        await self.save_stats()
        await self.check_milestones()

    @tasks.loop(minutes=5)
    async def update_online_count(self):
        await self.save_online_count()

    @update_online_count.before_loop
    async def before_update_online_count(self):
        await self.client.wait_until_ready()

    async def check_milestones(self):
        ''' Send alerts in all the servers following a user if they hit a milestone. '''
        users = await db_servers.get_all_users()
        for user in users:
            name = user[0]
            old_count = user[1]
            new_count = stats.get_alltime_stat(name)
            if new_count%1000 < old_count%1000:
                # send alert in all the servers tracking user
                channels = await db_servers.get_all_channels(name)
                for c in channels:
                    if c != None:
                        channel = self.client.get_channel(c)
                        await channel.send("New milestone for **"+name+"**! New count: "+str(new_count))
            if new_count != old_count:
                # update the new count in the db
                await db_servers.update_pixel_count(name,new_count)

    async def save_stats(self):
        ''' Update the database with the new /stats data. '''
        # get the 'last updated' datetime and its timezone
        lastupdated_string = stats.get_last_updated()
        lastupdated = stats.last_updated_to_date(lastupdated_string)
        # Convert /stats to a naive datetime in UTC
        lastupdated = local_to_utc(lastupdated)
        lastupdated = lastupdated.replace(tzinfo=None) #timezone naive as UTC

        alltime_stats = stats.get_all_alltime_stats()
        canvas_stats = stats.get_all_canvas_stats()

        await db_stats.update_all_pxls_stats(alltime_stats,canvas_stats,lastupdated)
    
    async def save_online_count(self):
        ''' save the current 'online count' in the database '''
        online = await stats.get_online_count()
        await db_stats.add_general_stat("online_count",online,None,datetime.utcnow())

def setup(client):
    client.add_cog(Clock(client))
