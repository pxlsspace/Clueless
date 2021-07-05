import discord
from discord.ext import commands
import requests
import praw
import time
import os
from dotenv import load_dotenv

SUBREDDIT = "tuckedinkitties"

class Kitten(commands.Cog):
    ''' Class to get a random kitten image from reddit'''

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
        print("getting url..")
        url = submission.url
        print(url)

        r = requests.head(url,stream=True)

        try:
            content_type = r.headers['content-type']
        except KeyError as e:
            return None

        if content_type.startswith('image'):
            return url

        try:
            for i in submission.media_metadata.items():
                url = i[1]['p'][0]['u']
                url = url.split("?")[0].replace("preview", "i")
                return url

        except AttributeError:
            return None

    def get_random_image_post(self,subreddit):
        ''' get a random submission containing an image from the parameter subreddit  
        return `None` if the subreddit doesnt support `.random()`'''

        random_submission = subreddit.random()
        
        if random_submission == None:
            return None

        while self.get_image_url(random_submission) == None:
            random_submission = subreddit.random()
        return random_submission
    
    def get_kitten(self):
        
        sub = self.reddit.subreddit(SUBREDDIT)
        submission = self.get_random_image_post(sub)
        return submission
        
    def format_embed(self,submission):
        '''
        Format a reddit submission into a discord embed.

        :param submission: the submission to format
        :return embed: The embed containing the submission'''
    
        reddit_link = "https://www.reddit.com"+submission.permalink

        e = discord.Embed(title="Here, have a kitten!",url=reddit_link,color=0xffd1ec)
        e.set_image(url=self.get_image_url(submission))
        
        #e.add_field(name='\u200b',value=f"[reddit post link]({reddit_link})")
        e.set_footer(text="Image from r/"+SUBREDDIT)

        return e

    @commands.command(
        aliases=["kitty","cat"],
        description = "Sends a random kitten image.")
    async def kitten(self,ctx):
        start_time = int(round(time.time() * 1000))

        post = self.get_kitten()

        end_time = int(round(time.time() * 1000))
        time_diff = end_time - start_time

        embed = self.format_embed(post)
        embed.set_footer(text="Image from r/"+SUBREDDIT+"\t (found in "+str(time_diff/1000)+" seconds)")
        await ctx.send(embed=embed)


def setup(client):
    client.add_cog(Kitten(client))
