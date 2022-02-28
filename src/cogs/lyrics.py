import disnake
from disnake.ext import commands
from disnake import Spotify
from difflib import SequenceMatcher

from utils.genius import search_song
from utils import azlyrics


class Lyrics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    # slash command
    @commands.slash_command(name="lyrics")
    async def _lyrics(self, inter: disnake.AppCmdInter, song: str = None):
        """Get the lyrics of the song you're listening on Spotify.

        Parameters
        ----------
        song: The song to search.
        """
        await inter.response.defer()
        await self.lyrics(inter, query=song)

    # prefix command
    @commands.command(
        name="lyrics",
        description="Get the lyrics of the song you're listening on Spotify.",
        usage="[song]"
    )
    async def p_lyrics(self, ctx, *, song=None):
        async with ctx.typing():
            await self.lyrics(ctx, query=song)

    async def lyrics(self, ctx, *, query=None):
        spotify_title = None
        spotify_artists = None
        if query is None:
            # if no query is given, we get the song from the discord activity
            user = ctx.author
            for activity in user.activities:
                if isinstance(activity, Spotify):
                    spotify_title = activity.title
                    spotify_artists = activity.artists
            if spotify_title is None and spotify_artists is None:
                return await ctx.send("❌ You are not playing any song on Spotify.")
            else:
                title_to_search = spotify_title
                artists_to_search = spotify_artists
        else:
            # if a query is given, we search lyrics for it
            title_to_search = query
            artists_to_search = None

        # search the song in azlyrics
        try:
            if artists_to_search:
                azlyrics_url = await azlyrics.search_song(
                    title=title_to_search, artist=artists_to_search[0]
                )
            else:
                azlyrics_url = await azlyrics.search_song(query=title_to_search)
            if azlyrics_url is not None:
                title, lyrics = await azlyrics.get_lyrics(azlyrics_url)
                lyrics = format_lyrics(lyrics)
                if len(lyrics) > 4096:
                    lyrics = "**The lyrics are too long to be displayed\nClick on the title to see them on the site**"
                embed = disnake.Embed(
                    title=title, url=azlyrics_url, description=lyrics, color=0x9999CC
                )
                embed.set_footer(
                    text="source: azlyrics.com",
                    icon_url="http://images.azlyrics.com/az_logo_tr.png",
                )
                return await ctx.send(embed=embed)
        except Exception:
            pass
        # search the song in genius
        if artists_to_search:
            song = await search_song(
                f'{azlyrics.remove_feat(title_to_search)} {artists_to_search[0] or ""}'
            )
            artists_to_search = " ".join(artists_to_search)
        else:
            song = await search_song(title_to_search)
        # check that we found a song and that it's the correct song
        if song is None or (
            spotify_title and not is_similar(spotify_title, song.title)
        ):
            return await ctx.send(
                f"❌ Can't find any lyrics for **{title_to_search}**"
                + ((f" by **{artists_to_search}**") if artists_to_search else "")
            )

        # get the song information and lyrics
        song_cover_url = song.image_url
        lyrics = song.lyrics
        song_url = song.genius_url
        if lyrics is None:
            lyrics = "[**Link to the lyrics**]({})".format(song_url)
        else:
            lyrics = format_lyrics(lyrics)
        if len(lyrics) > 4096:
            lyrics = "**The lyrics are too long to be displayed\nClick on the title to see them on the site**"

        # send the embed with the information
        embed = disnake.Embed(
            color=0xFFFF64, title=f"Lyrics for {song.full_title}", description=lyrics
        )
        embed.set_thumbnail(url=song_cover_url)
        embed.set_footer(
            text="source: genius.com",
            icon_url="https://images.genius.com/8ed669cadd956443e29c70361ec4f372.1000x1000x1.png",
        )
        return await ctx.send(embed=embed)


def format_lyrics(lyrics):
    """format lyrics to be printed in discord"""
    res = ""
    for line in lyrics.split("\n"):
        # put the paragraphs names in bold ([Chorus], [Verse], ...)
        if line.startswith("[") and line.endswith("]"):
            res += f"**{line}**\n"
        else:
            res += line + "\n"
    return res


def is_similar(string1, string2):
    """Check if 2 strings are similar using SequenceMatcher"""
    string1 = string1.lower()
    string2 = string2.lower()

    # remove the 'feat' part from the titles that might make the comparison inaccurate
    string1 = azlyrics.remove_feat(string1)
    string2 = azlyrics.remove_feat(string2)

    return SequenceMatcher(None, string1, string2).ratio() > 0.8


def setup(bot: commands.Bot):
    bot.add_cog(Lyrics(bot))
