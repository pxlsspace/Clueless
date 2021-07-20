import discord
from discord.ext import commands
import asyncio
from utils.img_to_gif import img_to_animated_gif
from PIL import Image
from io import BytesIO

from utils.discord_utils import get_image_from_message

class Emote(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.group(
        usage="[add|remove|list|number]",
        description ="Manage the server custom emotes.",
        aliases = ["emoji"],
        invoke_without_command = True)
    async def emote(self, ctx,subcommand): 
        return await ctx.send(f"❌ Sub-command {subcommand} is not found\nUsage: `{ctx.prefix}{ctx.command.name} {ctx.command.usage}`")
    @emote.command(
        usage = "<name> <url|image>",
        description = """Adds the image as a custom emoji.""",
        help = """\t- `<name>`: name of the emoji to add\n
                  \t- `<url|image>`: an image URL or an attached image"""
    )
    @commands.has_permissions(manage_emojis=True)
    async def add(self, ctx, name, url=None):

        # get the input image
        try:
            img_bytes, url = get_image_from_message(ctx,url)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # adding the emote to the server
        try:
            emoji = await asyncio.wait_for(ctx.guild.create_custom_emoji(name=name, image=img_bytes),timeout=10.0)
        except discord.InvalidArgument:
            return await ctx.send("❌ Invalid image type. Only PNG, JPEG and GIF are supported.")
        except discord.HTTPException as e:
            if (e.code == 50035):
                return await ctx.send(e.text)
            if (e.code == 30008):
                #return await ctx.send("❌ Error: Maximum number of emojis reached (50)")
                print("Maximum number of emojis reached (50), trying to add as animated")
                stream = BytesIO(img_bytes)
                img = Image.open(stream)
                animated_img = img_to_animated_gif(img)
                try:
                    emoji = await asyncio.wait_for(ctx.guild.create_custom_emoji(name=name, image=animated_img),timeout=10.0)
                except discord.InvalidArgument:
                    return await ctx.send("❌ Invalid image type. Only PNG, JPEG and GIF are supported.")
                except discord.HTTPException as e:
                    if (e.code == 50035):
                        return await ctx.send("❌ Error: File cannot be larger than 256.0 kb.")
                    if (e.code == 30008):
                        return await ctx.send("❌ Error: Maximum number of emojis reached (50)")
                    print(e)
                    return await ctx.send(e.text)
                except asyncio.TimeoutError:
                    return await ctx.send("❌ You're getting ratelimited by discord, retry again in 20/30 min")
            else:
                print(e)
                return await ctx.send(e.text)
        except asyncio.TimeoutError:
            return await ctx.send("❌ You're getting ratelimited by discord, retry again in 20/30 min")

        await ctx.send("✅ Successfully added the emoji {0.name} <{1}:{0.name}:{0.id}>".format(emoji, "a" if emoji.animated else ""))


    @emote.command(
        usage = "<name>",
        description="""Remove a custom emoji from the server.""",
        aliases=["delete","rm"])
    @commands.has_permissions(manage_emojis=True)
    async def remove(self, ctx, name):
        emotes = [x for x in ctx.guild.emojis if x.name == name]
        if len(emotes) == 0:
            return await ctx.send("❌ There is no emote with that name on this server.")
        nb_emote = len(emotes)
        for emote in emotes:
            await emote.delete()
        await ctx.send(f"✅ {nb_emote} emote(s) with the name :`{name}`: have been deleted")

    @emote.command(
        description="Show all of the server custom emojis and their names.",
        aliases=["show"]
    )
    async def list(self, ctx):
        emotes = ctx.guild.emojis
        if len(emotes) == 0:
            return await ctx.send("❌ There are no emotes in this server")
        res = [""]
        i = 0
        for emote in emotes:
            name = emote.name
            id = emote.id
            emote_text = f'<{"a" if emote.animated else ""}:{name}:{id}> `:{name}:`\n'
            if len(res[i]) + len(emote_text) > 2000:
                i+=1
                res.append("")
            res[i] += emote_text
            
        #print(len(res))
        for msg in res:
            await ctx.send(msg)

    @emote.command(
        description="Give the number of emojis and animated emojis on the server",
        aliases = ["nb"])
    async def number(self,ctx):
        emojis = await ctx.guild.fetch_emojis()
        nb_static = 0
        nb_anim = 0
        for e in emojis:
            if e.animated == True:
                nb_anim += 1
            else:
                nb_static += 1
        await ctx.send(f"There are {nb_anim+nb_static} emojis in this server:\n\t- {nb_static} emojis\n\t- {nb_anim} animated emojis")


def setup(client):
    client.add_cog(Emote(client))