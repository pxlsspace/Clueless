import discord
from discord.ext import commands
from discord.ext import tasks
from discord.ext.commands.core import command, cooldown
from datetime import datetime, timedelta
import time
from cogs.utils.database import *
from cogs.utils.cooldown import *
from cogs.utils.pxls_stats import *


class PxlsMilestones(commands.Cog, name="Pxls.space"):

    def __init__(self, client):
        self.client = client
        self.update_stats.start()
        self.stats = PxlsStats()
        
    def cog_unload(self):
        self.update_stats.cancel()

    ### Loop tasks ###
    @tasks.loop(seconds=60)
    async def update_stats(self):
        now = datetime.now()
        min = now.strftime("%M")

        if min in ['01','16','31','46']:
            # refresh the stats data
            time = now.strftime("[%H:%M:%S]")
            self.stats.refresh()
            if self.stats.stats_json == None:
                print(time + ": stats page unreachable")
                return
            print(time +": STATS SOURCE PAGE UPDATED")

            # save the stats data in the database
            lastupdated_string = self.stats.get_last_updated()
            lastupdated = PxlsStats.last_updated_to_date(lastupdated_string)
            for user in self.stats.get_all_alltime_stats():
                name = user["username"]
                alltime_count = user["pixels"]
                update_pxls_stats(name,lastupdated,alltime_count,None)
            for user in self.stats.get_all_canvas_stats():
                name = user["username"]
                canvas_count = user["pixels"]
                update_pxls_stats(name,lastupdated,None,canvas_count)

            # check milestones
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
    
    # wait for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()

    ### Discord commands ###
    @commands.command(
        usage = " <pxls user> [-c]",
        description = "Shows the pixel count for a pxls user, all-time by default, canvas with `-c`.")
    async def stats(self,ctx,name,option=None):

        if option == "-c":
            number = self.stats.get_canvas_stat(name)
            text = "Canvas"
        else:
            number = self.stats.get_alltime_stat(name)
            text = "All-time"

        if not number:
            return await ctx.send ("❌ User not found.")
        else:
            msg = f'**{text} stats for {name}**: {number} pixels.'
            return await ctx.send(msg)

    @commands.command(usage=" <name> <time>[h|d]",
    description = "Show the average speed of a user in the last x hours or days")
    async def speed(self,ctx,name,time):
        if not time[:-1].isdigit():
            return await ctx.send(f"❌ Invalid `time` parameter, format must be `{ctx.prefix}speed <name> <time>[h|d]`.")
        now = datetime.now()

        if time.endswith("h"):
            time = int(time[:-1])
            query_time = now - timedelta(hours=time)
        elif time.endswith("d"):
            time = int(time[:-1])
            query_time = now - timedelta(days=time)
        else:
            return await ctx.send(f"❌ Invalid `time` parameter, format must be `{ctx.prefix}speed <name> <time>[h|d]`.")

        (now_count , now_time) = get_alltime_pxls_count(name,now)
        (past_count, past_time) = get_alltime_pxls_count(name,query_time)

        if now_count == None:
            return await ctx.send("❌ User not found.")
        if past_count == None:
            return await ctx.send("❌ No database entry for this time.")

        nb_hours = (now_time-past_time)/timedelta(hours=1)
        nb_days = (now_time-past_time)/timedelta(days=1)

        diff_pixel = now_count-past_count
        speed_px_h = round(diff_pixel/nb_hours,2)
        speed_px_d = round(diff_pixel/nb_days,2)

        if nb_days < 1:
            await ctx.send(f'{name} placed `{diff_pixel}` pixels in the last {round(nb_hours)} hour(s).\n (Average of `{speed_px_h}` px/h)')
        else:
            await ctx.send(f'{name} placed `{diff_pixel}` pixels in the last {round(nb_days)} day(s)\n (average of `{speed_px_h}` px/h or `{speed_px_d}` px/day)')

    @commands.command(
        description = "Shows the current general stats from pxls.space/stats."
    )
    async def generalstats(self,ctx):
        gen_stats = self.stats.get_general_stats()
        text = ""
        for element in gen_stats:
             # formating the number (123456 -> 123 456)
            num = f'{int(gen_stats[element]):,}'
            num = num.replace(","," ")
            text += f"**{element.replace('_',' ').title()}**: {num}\n"
        text += f'*Last updated: {self.stats.get_last_updated()}*'
        await ctx.send(text)

    @commands.command(
        usage =" [nb user]",
        description = "Shows the current pxls cooldown.",
        aliases = ["cd","timer"])
    async def cooldown(self,ctx,number=None):
        if number:
            online = int(number)
        else:
            r = requests.get('https://pxls.space/users')
            online = json.loads(r.text)["count"]

        text = ""
        i = 0
        total = 0
        cooldowns = get_cds(online)
        dash = '-' * 40
        text = dash + "\n"
        text = ""
        for cd in cooldowns:
            i+=1
            total += cd
            text+=f'• **{i}/6** -> `{time_convert(cd)}`    (total: `{time_convert(total)}`)\n'
            #text += '{:<5s}{:>10s}{:>10s}\n'.format(f'{i}/6',time_convert(cd),time_convert(total))
        embed = discord.Embed(title=f"Pxls cooldown for `{online}` users")
        embed.add_field(name=dash,value=text)
        await ctx.send(embed=embed)
        

    @commands.group(
        usage = " [add|remove|list|channel|setchannel]",
        description = "Tracks pxls users stats and sends an alert in a chosen channel when a new milestone is hit.",
        aliases = ["ms"],
        invoke_without_command = True)
    async def milestones(self,ctx,args):
        return
    
    @milestones.command(
        usage = " <name>",
        description = "Add the user <name> to the tracker."
    )
    async def add(self,ctx,name=None):
        # checking valid paramter
        if name == None:
            return await ctx.send("❌ You need to specify a username.")

        # checking if the user exists
        count = self.stats.get_alltime_stat(name)
        if count == None:
            await ctx.send("❌ User not found.")
            return

        if (add_user(ctx.guild.id,name,count)) == -1:
            await ctx.send("❌ This user is already being tracked.")
            return
        await ctx.send ("✅ Tracking "+name+"'s all-time counter.")

    @milestones.command(
        usage = " <name>",
        description = "Removes the user <name> from the tracker.",
        aliases=["delete"]
        )
    async def remove(self,ctx,name=None):
        if name == None:
            return await ctx.send("❌ You need to specify a username.")
        if(remove_user(ctx.guild.id,name) != -1):
            return await ctx.send ("✅ "+name+" isn't being tracked anymore.")
        else:
            return await ctx.send("❌ User not found.")

    @milestones.command(
        description="Shows the list of users being tracked.",
        aliases=["ls"])
    async def list(self,ctx):
        users = get_all_server_users(ctx.guild.id)
        if len(users) == 0:
            await ctx.send("❌ No user added yet.\n*(use `"+ctx.prefix+"milestones add <username>` to add a new user.*)")
            return
        text="**List of users tracked:**\n"
        for u in users:
            text+="\t- **"+u[0]+":** "+str(u[1])+" pixels\n"
        await ctx.send(text)

    @milestones.command(
        usage = " [#channel|here|none]",
        description = "Sets the milestone alerts to be sent in a channe, shows the current alert channel if no parameter is given.",
        aliases=["setchannel"])
    @commands.has_permissions(manage_channels=True)
    async def channel(self,ctx,channel=None):
        if channel == None:
            # displays the current channel if no argument specified
            channel_id = get_alert_channel(ctx.guild.id)
            if channel_id == None:
                return await ctx.send(f"❌ No alert channel set\n (use `{ctx.prefix}milestones setchannel <#channel|here|none>`)")
            else:
                return await ctx.send("Milestones alerts are set to <#"+str(channel_id)+">")
            #return await ctx.send("you need to give a valid channel")
        channel_id = 0
        if len(ctx.message.channel_mentions) == 0:
            if channel == "here":
                channel_id = ctx.message.channel.id
            elif channel == "none":
                update_alert_channel(None,ctx.guild.id)
                await ctx.send("✅ Miletone alerts won't be sent anymore.")
                return
            else:
                return await ctx.send("❌ You need to give a valid channel.")
        else: 
            channel_id = ctx.message.channel_mentions[0].id

        # checks if the bot has write perms in the alert channel
        channel = self.client.get_channel(channel_id)
        if not ctx.message.guild.me.permissions_in(channel).send_messages:
            await ctx.send(f"❌ I don't not have permissions to send mesages in <#{channel_id}>")
        else:
            # saves the new channel id in the db
            update_alert_channel(channel_id,ctx.guild.id)
            await ctx.send("✅ Milestones alerts successfully set to <#"+str(channel_id)+">")
        
def setup(client):
    client.add_cog(PxlsMilestones(client))