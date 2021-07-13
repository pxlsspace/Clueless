from discord.ext import commands
import discord
import requests
import json
from utils.cooldown import get_cds, time_convert

class PxlsCooldown(commands.Cog):

    def __init__(self,client):
        self.client = client

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

        i = 0
        total = 0
        cooldowns = get_cds(online)

        cd_table = []
        desc = "```\n"
        for cd in cooldowns:
            i+=1
            total += cd
            cd_table.append([f'• {i}/6',time_convert(cd),time_convert(total)])
        
        desc += self.format_cooldown(cd_table,["stack","cd","total"])
        desc += "```"
        embed = discord.Embed(title=f"Pxls cooldown for `{online}` users",description=desc)
        #embed.add_field(name=dash,value=text)
        await ctx.send(embed=embed)

    @staticmethod
    def format_cooldown(table,column_names,name=None):
        ''' Format the cooldown values in a string to be printed '''
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
        title_format = "  "+" ".join(["{:^" + str(longest_col) + "}" for longest_col in longest_cols])
        str_table = f'{title_format.format(*table[0])}\n{LINE}\n'

        # format the body
        row_format = " ".join(["{:>" + str(longest_col) + "}" for longest_col in longest_cols])
        for row in table[1:]:
            str_table += ("+" if row[1] == name else " ") + row_format.format(*row) + "\n"

        return str_table
def setup(client):
    client.add_cog(PxlsCooldown(client))