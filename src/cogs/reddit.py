import discord
from discord.ext import commands
from discord.ext.commands.core import command
from praw.reddit import Submission
import requests
import praw
import time
import os
from dotenv import load_dotenv
import random

class Reddit(commands.Cog,name = "Image"):
    ''' Class to get images from reddit'''

    def __init__(self, client):
        load_dotenv()
        self.client = client
        self.reddit = praw.Reddit(
            client_id = os.environ.get("REDDIT_CLIENT_ID"),
            client_secret = os.environ.get("REDDIT_CLIENT_SECRET"),
            user_agent = os.environ.get("REDDIT_USER_AGENT"),
            check_for_async=False
        )
        self.reddit.read_only = True

    def get_image_url(self,submission):
        '''Get the image link from a reddit subimission
        return the url of the image or `None` if no image found'''
        url = submission.url # this line takes too much time for some reason

        if url[-4:] in [".jpg",".png",".gif"]:
            return url
        else:
            return None

    def get_random_image_post(self,subreddit):
        ''' get a random submission containing an image from the parameter subreddit  
        return `None` if the subreddit doesnt support `.random()`'''

        #random_submission = subreddit.random()
        submissions = list(subreddit.hot(limit=100)) # this line can take long sometimes
        random_submission = random.choice(submissions)

        #random_submission = self.reddit.submission(id="o4h0m8")
        if random_submission == None:
            return None

        while self.get_image_url(random_submission) == None:
            random_submission = random.choice(submissions)
        return random_submission
        
    def format_embed(self,submission,title,subreddit,time):
        '''
        Format a reddit submission into a discord embed.

        :param submission: the submission to format
        :return embed: The embed containing the submission'''
    
        reddit_link = "https://www.reddit.com"+submission.permalink

        e = discord.Embed(title=title,url=reddit_link,color=0xffd1ec)
        e.set_image(url=self.get_image_url(submission))
        
        #e.add_field(name='\u200b',value=f"[reddit post link]({reddit_link})")
        e.set_footer(text="Image from r/"+subreddit+"\t (found in "+str(time)+" seconds)")

        return e

    async def send_random_image(self,ctx,subreddit_name,title):
        """Send a random image from the given subreddit_name 
        in the ctx channel as a discord embed
        
        :param ctx: the discord context to send the message
        :param subreddit_name: the subreddit to get the image from
        :param title: the text to show with the image"""
        sub = self.reddit.subreddit(subreddit_name)

        start_time = time.time()
        submission = self.get_random_image_post(sub)
        end_time = time.time()
        time_diff = round(end_time - start_time,2)

        if not submission:
            return await ctx.send(f"❌ The subreddit {subreddit_name} doesn't support random.")

        embed = self.format_embed(submission,title,subreddit_name,time_diff)
        await ctx.send(embed=embed)

    @commands.cooldown(1,2)
    @commands.command(
        aliases=["kitty","cat"],
        description = "Sends a random kitten image.",
        ratelimit=1)
    async def kitten(self,ctx):
        subreddit = random.choice(["tuckedinkitties","kitten"])
        await self.send_random_image(ctx,subreddit,"Here, have a kitten!")

    @commands.cooldown(1,2)
    @commands.command(description = "Sends a random duck image.")
    async def duck(self,ctx):
        subreddit = "duck"
        await self.send_random_image(ctx,subreddit,"quack quack")            

    @commands.cooldown(1,2)
    @commands.command(description = "Sends a random bird image.")
    async def bird(self,ctx):
        subreddit = random.choice(["birding","birdpics"])
        await self.send_random_image(ctx,subreddit,"Here, have a bird!")    

    @commands.cooldown(1,2)
    @commands.command(description = "Sends a random snek image.")
    async def snek(self,ctx):
        subreddit = "Sneks"
        await self.send_random_image(ctx,subreddit,"s  n  e  k") 

    @commands.cooldown(1,2)
    @commands.command(description = "Sends a random doggo image.")
    async def doggo(self,ctx):
        subreddit = random.choice(["dogs","dogpictures","puppies","PuppySmiles"])
        await self.send_random_image(ctx,subreddit,"Here, have a doggo!") 

def setup(client):
    client.add_cog(Reddit(client))
