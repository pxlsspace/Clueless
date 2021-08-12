from discord.ext import commands
from PIL import Image
from utils.setup import stats
from utils.discord_utils import image_to_file

class PxlsStats(commands.Cog):

    def __init__(self,client):
        self.client = client
        

    @commands.command(
        description = "Show some general pxls stats.",
        aliases = ["gstats","gs"]
    )
    async def generalstats(self,ctx):
        gen_stats = stats.get_general_stats()
        text = ""
        text += f"**Canvas Code**: {stats.get_canvas_code()}\n"
        for element in gen_stats:
             # formating the number (123456 -> 123 456)
            num = f'{int(gen_stats[element]):,}'
            num = num.replace(","," ")
            text += f"**{element.replace('_',' ').title()}**: {num}\n"
        text += f'*Last updated: {stats.get_last_updated()}*'
        await ctx.send(text)

    @commands.command(
    usage = "<username> [-c]",
    description = "Show the pixel count for a pxls user.",
    help = """- `<username>`: a pxls username
              - `[-c|-canvas]`: to see the canvas count.""")
    async def stats(self,ctx,name,option=None):

        if option == "-c" or option == "-canvas":
            number = stats.get_canvas_stat(name)
            text = "Canvas"
        else:
            number = stats.get_alltime_stat(name)
            text = "All-time"

        if not number:
            return await ctx.send ("❌ User not found.")
        else:
            msg = f'**{text} stats for {name}**: {number} pixels.'
            return await ctx.send(msg)

    @commands.command(description="Get the current pxls board.",usage = "[-virgin|-initial]")
    async def board(self,ctx,*options):
        async with ctx.typing():
            if "-virginmap" in options or "-virgin" in options:
                array = await stats.fetch_virginmap()
            elif "-initial" in options:
                array = await stats.fetch_initial_canvas()
                array = stats.palettize_array(array)
            else:
                array = stats.board_array
                array = stats.palettize_array(array)

            board_img = Image.fromarray(array)
            file = image_to_file(board_img,"board.png")
            await ctx.send(file=file)

def setup(client):
    client.add_cog(PxlsStats(client))
