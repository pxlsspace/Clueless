import random
import time

import disnake
from disnake.ext import commands

from utils.utils import get_content


class Reddit(commands.Cog, name="Image"):
    """Class to get images from reddit"""

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    def get_image_url(self, subm):
        """Get the image URL from the json of a reddit submission,
        return None if no URL was found (for video posts, image posts, ...)"""
        try:
            url = subm["url"]
            if url[-4:] in [".jpg", ".png", ".gif"]:
                return url
            elif "gallery" in url:
                medias = subm["media_metadata"]
                for media_id in medias:
                    media = subm["media_metadata"][media_id]
                    url = media["p"][-1]["u"]
                    url = url.split("?")[0].replace("preview", "i")
                    if url[-4:] in [".jpg", ".png", ".gif"]:
                        return url
            return None
        except Exception:
            return None

    async def get_random_submission(self, subreddit_name):
        """get a random submission containing an image from 'subreddit_name'.

        return a tuple with 2 items: (image_url,reddit_post_url)"""

        request_url = (
            f"https://www.reddit.com/r/{subreddit_name}/top.json?limit=100&t=week"
        )
        submissions_json = await get_content(request_url, "json")
        submissions = submissions_json["data"]["children"]

        submissions_with_image = []
        for subm in submissions:
            subm_data = subm["data"]
            # filter out spoiler, pinned and nsfw posts
            if (
                not subm_data["spoiler"]
                and not subm_data["pinned"]
                and not subm_data["over_18"]
            ):
                subm_image_url = self.get_image_url(subm_data)
                if subm_image_url is not None:
                    subm_url = "https://www.reddit.com" + subm_data["permalink"]
                    submissions_with_image.append((subm_image_url, subm_url))
        if len(submissions_with_image) == 0:
            return (None, None)
        random_submission = random.choice(submissions_with_image)
        return random_submission

    def format_embed(self, submission_link, image_link, title, subreddit, time):
        """
        Format a reddit submission into a discord embed.

        :param submission: the submission to format
        :return embed: The embed containing the submission"""

        e = disnake.Embed(title=title, url=submission_link, color=0x66C5CC)
        e.set_image(url=image_link)
        e.set_footer(
            text="Image from r/{} - Found in {} second{}".format(
                subreddit, round(time, 2), "s" if time > 2 else ""
            )
        )

        return e

    async def send_random_image(self, ctx, subreddit_name, title):
        """Send a random image from the given subreddit_name
        in the ctx channel as a discord embed

        :param ctx: the discord context to send the message
        :param subreddit_name: the subreddit to get the image from
        :param title: the text to show with the image"""
        try:
            start = time.time()
            image_url, submission_url = await self.get_random_submission(subreddit_name)
            if submission_url is None:
                return await ctx.send("❌ No image found :(")
            ex_time = time.time() - start
            embed = self.format_embed(
                submission_url, image_url, title, subreddit_name, ex_time
            )
            await ctx.send(embed=embed)
        except Exception: 
            await ctx.send("❌ Failed to query reddit for an image. We're possibly being blocked :-()")

    @commands.cooldown(1, 2)
    @commands.command(
        aliases=["kitty", "cat"], description="Send a random kitten image.", ratelimit=1
    )
    async def kitten(self, ctx):
        subreddit = random.choice(["tuckedinkitties", "kitten"])
        await self.send_random_image(ctx, subreddit, "Here, have a kitten!")

    @commands.cooldown(1, 2)
    @commands.command(description="Send a random duck image.")
    async def duck(self, ctx):
        subreddit = "duck"
        await self.send_random_image(ctx, subreddit, "quack quack")

    @commands.cooldown(1, 2)
    @commands.command(description="Send a random bird image.")
    async def bird(self, ctx):
        subreddit = random.choice(["birding", "birdpics"])
        await self.send_random_image(ctx, subreddit, "Here, have a bird!")

    @commands.cooldown(1, 2)
    @commands.command(description="Send a random snek image.")
    async def snek(self, ctx):
        subreddit = "Sneks"
        await self.send_random_image(ctx, subreddit, "s  n  e  k")

    @commands.cooldown(1, 2)
    @commands.command(description="Send a random doggo image.")
    async def doggo(self, ctx):
        subreddit = random.choice(["dog", "dogpictures", "puppies", "PuppySmiles"])
        await self.send_random_image(ctx, subreddit, "Here, have a doggo!")


def setup(bot: commands.Bot):
    bot.add_cog(Reddit(bot))
