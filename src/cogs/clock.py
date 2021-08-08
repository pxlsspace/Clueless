import discord
import traceback
from sys import stderr
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from utils.setup import stats, db_stats_manager as db_stats, db_servers_manager as db_servers, db_users_manager as db_users
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
            await self._update_stats_data()

    @update_stats.error
    async def update_stats_error(self, error):
        formatted = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        print("Unexpected exception in task 'update_stats':")
        print(formatted,file=stderr)

    # wait for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()
        try:
            await self._update_stats_data()
        except Exception as error:
            formatted = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            print("Unexpected before starting task 'update_stats':")
            print(formatted,file=stderr)

    async def _update_stats_data(self):

            # refreshing stats json
            await stats.refresh()
            if stats.stats_json == None:
                now = datetime.now().strftime("[%H:%M:%S]")
                print(now + ": stats page unreachable")
                return

            # updating database with the new data
            await self.save_stats()

            await self.check_milestones()
            now = datetime.now().strftime("[%H:%M:%S]")
            print(now +": stats updated")
            # wait for the time to be a round value
            round_minute = datetime.now(timezone.utc) + timedelta(minutes=1)
            round_minute = round_minute.replace(second=0,microsecond=0)
            await discord.utils.sleep_until(round_minute)

    @tasks.loop(minutes=5)
    async def update_online_count(self):
        await self.save_online_count()

    @update_online_count.before_loop
    async def before_update_online_count(self):
        # wait for the bot to be ready
        await self.client.wait_until_ready()
        # wait that the time is a round value
        now = datetime.now(timezone.utc)
        next_run = now.replace(minute=int(now.minute / 5) * 5, second=0, microsecond=0) + timedelta(minutes=5)
        await discord.utils.sleep_until(next_run)

    async def check_milestones(self):
        ''' Send alerts in all the servers following a user if they hit a milestone. '''

        users_servers = await db_users.get_all_tracked_users()

        for user_id in users_servers.keys():
            values = await db_stats.get_last_alltime_counts(user_id)
            if values == None:
                continue
            username = values[0]
            old_count = values[1]
            new_count = values[2]

            if new_count%1000 < old_count%1000:
                servers = users_servers[user_id]
                for server_id in servers:
                    channel_id = await db_servers.get_alert_channel(server_id)
                    try:
                        channel = self.client.get_channel(int(channel_id))
                        await channel.send("New milestone for **"+username+"**! New count: "+str(new_count))
                    except Exception:
                        pass

    async def save_stats(self):
        ''' Update the database with the new /stats data. '''
        
        # get the 'last updated' datetime and its timezone
        lastupdated_string = stats.get_last_updated()
        lastupdated = stats.last_updated_to_date(lastupdated_string)
        # Convert /stats to a naive datetime in UTC
        lastupdated = local_to_utc(lastupdated)
        lastupdated = lastupdated.replace(tzinfo=None) #timezone naive as UTC

        # get all the stats
        alltime_stats = stats.get_all_alltime_stats()
        canvas_stats = stats.get_all_canvas_stats()

        # get the current canvas code
        canvas_code = await stats.get_canvas_code()
        await db_stats.update_all_pxls_stats(alltime_stats,canvas_stats,lastupdated,canvas_code)

    async def save_online_count(self):
        ''' save the current 'online count' in the database '''
        online = await stats.get_online_count()
        canvas_code = await stats.get_canvas_code()
        dt = datetime.utcnow().replace(microsecond=0)
        await db_stats.add_general_stat("online_count",online,canvas_code,dt)

def setup(client):
    client.add_cog(Clock(client))
