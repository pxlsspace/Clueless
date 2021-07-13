from discord.ext import commands
from handlers.setup import stats

class PxlsStats(commands.Cog):

    def __init__(self,client):
        self.client = client
        self.stats = stats
        

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

def setup(client):
    client.add_cog(PxlsStats(client))