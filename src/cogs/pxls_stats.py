from os import stat
import discord
from discord.ext import commands
from discord.ext import tasks
from discord.ext.commands.core import command, cooldown
from datetime import datetime, timedelta, timezone
from cogs.utils.database import *
from cogs.utils.cooldown import *
from cogs.utils.pxls_stats import *
from cogs.utils.time_converter import *
from cogs.utils.arguments_parser import *
from handlers.setup import stats

# TODO: sperate milestones commands and leaderboard/speed commands

class PxlsMilestones(commands.Cog, name="Pxls.space"):

    def __init__(self, client):
        self.client = client
        self.update_stats.start()
        self.stats = stats
        
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
            print(time +": updating stats data.",end='',flush=True)
            self.stats.refresh()
            if self.stats.stats_json == None:
                print(time + ": stats page unreachable")
                return
            print(".",end='',flush=True)

            # save the stats data in the database
            lastupdated_string = self.stats.get_last_updated()
            lastupdated = PxlsStats.last_updated_to_date(lastupdated_string)
            lastupdated = local_to_utc(lastupdated) #save the time in UTC in the db
            lastupdated = lastupdated.replace(tzinfo=None)
            for user in self.stats.get_all_alltime_stats():
                name = user["username"]
                alltime_count = user["pixels"]
                update_pxls_stats(name,lastupdated,alltime_count,0)
            print(".",end='',flush=True)
            for user in self.stats.get_all_canvas_stats():
                name = user["username"]
                canvas_count = user["pixels"]
                update_pxls_stats(name,lastupdated,None,canvas_count)
            print(".",end='',flush=True)
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
            print(". done!")
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

    @staticmethod
    def get_speed(name:str,date1:datetime,date2:datetime):
        ''' Get the speed of a user between 2 dates (in pixels/hour)

        return:
         - speed: the average speed in pixels/hour between the 2 dates,
         - diff_pixels the number of pixels placed between the 2 dates,
         - past_time: the closest datetime to date1 in the database',
         - recent_time the closest datetime to date2 in the database'''

        if date1 > date2:
            raise ValueError("date1 must be smaller than date2")
        (past_count, past_time,diff) = get_alltime_pxls_count(name,date1)
        (recent_count, recent_time,diff) = get_alltime_pxls_count(name,date2)

        if recent_count == None:
            # try to compare canvas pixels if cant find alltime pixels
            (past_count, past_time,diff) = get_canvas_pxls_count(name,date1)
            (recent_count, recent_time,diff) = get_canvas_pxls_count(name,date2)
            if recent_count == None:
                raise ValueError(f'User **{name}** was not found.')
        if past_time == None:
            raise ValueError(f'No database entry for this time.')
        if past_time == recent_time:
            raise ValueError("The time given is too short.")

        diff_pixels = recent_count - past_count
        diff_time = recent_time - past_time
        nb_hours = diff_time/timedelta(hours=1)
        speed = diff_pixels/nb_hours
        return speed, diff_pixels, past_time, recent_time

    @commands.command(usage=" <name> [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
    description = "Show the average speed of a user in the last x min, hours or days")
    #async def speed(self,ctx,name,time="5h"):
    async def speed(self,ctx,name,*args):
        ''' Show the average speed of a user in the last x min, hours or days '''

        try:
            param = parse_speed_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        if param["before"] == None and param["after"] == None:
            date = param["last"]
            input_time = str_to_td(date)
            if not input_time:
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
            recent_time = datetime.now(timezone.utc)
            old_time = datetime.now(timezone.utc) - input_time
        else:
            old_time = param["after"] or datetime(2021,7,7,14,15,10) # To change to oldest database entry
            recent_time = param["before"] or datetime.now(timezone.utc)

        try:
            speed_px_h, diff_pixel, past_time,now_time = self.get_speed(name,old_time,recent_time)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        speed_px_d = round(speed_px_h*24,1)
        speed_px_h = round(speed_px_h,1)
        nb_days = (now_time - past_time)/timedelta(days=1)

        if round(nb_days,1) < 1:
            return await ctx.send(f'**{name}** placed `{diff_pixel}` pixels between {format_datetime(past_time)} and {format_datetime(now_time)}.\nAverage speed: `{speed_px_h}` px/h')
        else:
            return await ctx.send(f'**{name}** placed `{diff_pixel}` pixels between {format_datetime(past_time)} and {format_datetime(now_time)}.\nAverage speed: `{speed_px_h}` px/h or `{speed_px_d}` px/day')

    # TODO: option to sort by speed
    # TODO: option to show speed in px/day or amount
    # TODO: allow adding multiple users to compare
    # TODO: change of the help command to show parameters
    # TODO: align speed values on the right
    @commands.command(
        usage = " [name] [-canvas] [-lines <number>] [-speed [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]] ",
        description = "Shows the all-time or canvas leaderboard.",
        aliases=["ldb"]
        )
    async def leaderboard(self,ctx,*args):
        ''' Shows the pxls.space leaderboard '''

        try:
            param = parse_leaderboard_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')
        username = param["name"]
        nb_line = param["lines"]
        canvas_opt = param["canvas"]
        speed_opt = param["speed"]

        # check on params
        if speed_opt:
            if param["before"] == None and param["after"] == None:
                date = param["last"]
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
                date2 = datetime.now(timezone.utc)
                date1 = datetime.now(timezone.utc) - input_time
            else:
                date1 = param["after"] or datetime(2021,7,7,14,15,10) # To change to oldest database entry
                date2 = param["before"] or datetime.now(timezone.utc)

        nb_line = int(nb_line)
        if nb_line > 40:
            return await ctx.send("❌ Can't show more than 40 lines.")

        ldb = get_last_leaderboard(canvas_opt)
        column_names = ["Rank","Username","Pixels"]
        date = ldb[0][3]
        if username:
            column_names.append("Diff")
            # looking for the index and pixel count of the given user
            name_index = None
            for index,line in enumerate(ldb):
                name = list(line)[1]
                pixels = list(line)[2]
                if name == username:
                    name_index = index
                    user_pixels = pixels
                    break
            if name_index == None:
                return await ctx.send("❌ User not found")

            # calucluate the indexes around the user
            min_idx = max(0,(name_index-round(nb_line/2)))
            max_idx = min(len(ldb),name_index+round(nb_line/2)+1)
            # if one of the idx hits the limit, we change the other idx to show more lines
            if min_idx == 0:
                max_idx = min_idx + nb_line
            if max_idx == len(ldb):
                min_idx = max_idx - nb_line
            ldb = ldb[min_idx:max_idx]
        else:
            ldb = ldb[0:nb_line]

        if speed_opt:
            column_names.append("Speed")

        for i in range(len(ldb)):
            ldb[i] = list(ldb[i][0:3]) # convert tuples to list and only keep first 3 col
            if username:
                # add the diff values
                diff = user_pixels-ldb[i][2]
                diff = f'{int(diff):,}'.replace(","," ") # convert to string
                ldb[i].append(diff)
            if speed_opt:
                # add speed values
                try:
                    speed, diff_pixels, past_time, recent_time = self.get_speed(ldb[i][1],date1,date2)
                except ValueError as e:
                     return await ctx.send(f'❌ {e}')
                speed = f'{int(speed):,}'.replace(","," ") # convert to string
                ldb[i].append(speed+" px/h")
            ldb[i][2] = f'{int(ldb[i][2]):,}'.replace(","," ") # format the number of pixels in a string

        text = "```diff\n"
        text += self.format_leaderboard(ldb,column_names,username)
        text += "```"

        if canvas_opt:
            emb = discord.Embed(title="Canvas Leaderboard",description=text)
        else:
            emb = discord.Embed(title="All-time Leaderboard",description=text)

        footer_text = "Last updated: {} ({} ago).".format(
            format_datetime(date),
            td_format(datetime.utcnow()-date)
            )
        if speed_opt:
            footer_text += "\nSpeed values between {} and {} ({}).".format(
                format_datetime(past_time),
                format_datetime(recent_time),
                td_format(recent_time-past_time)
            )
        emb.set_footer(text=footer_text)
        await ctx.send(embed=emb)

    @staticmethod
    def format_leaderboard(table,column_names,name=None):
        ''' Format the leaderboard in a string to be printed '''
        if not table:
            return
        if len(table[0]) != len(column_names):
            raise ValueError("The number of column in table and column_names don't match.")

        # find the longest columns
        table.insert(0,column_names)
        longest_cols = [
            (max([len(str(row[i])) for row in table]) + 1)
            for i in range(len(table[0]))]

        # format the header
        LINE = "-"*(sum(longest_cols) + len(table[0]*2))
        row_format = "|".join([" {:<" + str(longest_col) + "}" for longest_col in longest_cols])
        str_table = f'{LINE}\n {row_format.format(*table[0])}\n{LINE}\n'

        # format the body
        for row in table[1:]:
            str_table += ("+" if row[1] == name else " ") + row_format.format(*row) + "\n"

        return str_table

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