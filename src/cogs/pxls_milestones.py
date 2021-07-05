import discord
from discord.ext import commands
from discord.ext import tasks
from discord.ext.commands.core import command
import selenium
from datetime import datetime
import time
from cogs.utils.database import *
from cogs.utils.scrapping import *

from cogs.utils.cooldown import *

class PxlsMilestones(commands.Cog, name="Pxls.space"):

    def __init__(self, client):
        self.client = client
        self.driver = init_driver()
        self.stats_source_page = get_page_source(self.driver)
        self.update_stats.start()
        
    def cog_unload(self):
        self.update_stats.cancel()
        driver.close()

    ### Loop tasks ###
    @tasks.loop(seconds=60)
    async def update_stats(self):
        now = datetime.now()
        min = now.strftime("%M")

        if min in ['01','16','31','46']:
            # updating the stats source page
            
            try:
                self.stats_source_page = get_page_source(self.driver)
            except selenium.TimeoutException as e:
                print(e)
                return

            print(now.strftime("[%H:%M:%S]")+": STATS SOURCE PAGE UPDATED")

            # checking miletones
            table=scrape_alltime_leaderboard(self.stats_source_page)
            # get all users from the db
            users = get_all_users()
            for user in users:
                name = user[0]
                old_count = user[1]
                new_count = get_stats(name,table)
                if new_count%1000 < old_count%1000:
                    # send alert in all the servers tracking user
                    channels = get_all_channels(name)
                    for c in channels:
                        if c != None:
                            channel = self.client.get_channel(c)
                            await channel.send("New milestone for **"+name+"**! New count: "+str(new_count))
                if new_count != old_count:
                    # updating the new count in the db
                    update_pixel_count(name,new_count)
    
    # waits for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()

    """
    ### Discord events ###
    @commands.Cog.listener()
    async def on_ready(self):
    """

    ### Discord commands ###
    @commands.command(
        usage = " <pxls user> [-c]",
        description = "Shows the pixel count for a pxls user, all-time by default, canvas with `-c`.")
    async def stats(self,ctx,*args):
        table = []
        text = ""
        if len(args)>1 and args[1] == "-c":
            table = scrape_canvas_leaderboard(self.stats_source_page)
            text = "Canvas"
        else:
            table = scrape_alltime_leaderboard(self.stats_source_page)
            text = "All-time"
        res = get_stats(args[0],table)
        if res != -1:
            await ctx.send("**"+text+" stats for "+args[0]+"**: "+str(res)+" pixels")
        else:
            await ctx.send ("❌ User not found.")

    @commands.command(
        description = "Shows the current general stats from pxls.space/stats."
    )
    async def generalstats(self,ctx):
        text= scrape_general_stats(self.stats_source_page)
        await ctx.send(text)

    @commands.command(
        usage =" [nb user]",
        description = "Shows the current pxls cooldown.")
    async def cd(self,ctx,*args):
        await ctx.send(get_cds(args))

    @commands.group(
        usage = " [add|remove|list|channel|setchannel]",
        description = "Tracks pxls users stats and sends an alert in a chosen channel when a new milestone is hit.",
        aliases = ["ms"],
        invoke_without_command = False)
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
        table = scrape_alltime_leaderboard(self.stats_source_page)
        count = get_stats(name,table)
        if count == -1:
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
            await ctx.send("❌ No user added yet.\n*(use `"+ctx.prefix+"miletones add <username>` to add a new user.*)")
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
                return await ctx.send("✅ Milestones alerts are set to <#"+str(channel_id)+">")
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
            await ctx.send(f"❌ I dont not have permissions to send mesages in <#{channel_id}>")
        else:
            # saves the new channel id in the db
            update_alert_channel(channel_id,ctx.guild.id)
            await ctx.send("✅ Milestones alerts successfully set to <#"+str(channel_id)+">")
        
def setup(client):
    client.add_cog(PxlsMilestones(client))