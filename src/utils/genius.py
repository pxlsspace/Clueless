import re
import urllib
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from utils.utils import get_content

""" Functions and Classes used to communicate with the genius.com API"""

load_dotenv()
TOKEN = os.environ.get("GENIUS_ACCESS_TOKEN")
BASE_URL = "https://api.genius.com/"
HEADERS = {'Authorization': 'Bearer '+ TOKEN}

class Song():
    """ object used to store the informations about a song """
    def __init__(self,title,full_title,artists,genius_url,image_url,lyrics) -> None:
        self.title = title
        self.full_title = full_title
        self.artists = artists
        self.genius_url=genius_url
        self.image_url = image_url
        self.lyrics = lyrics

async def get_response(query):
    url = BASE_URL + query + "&access_token="+TOKEN
    json = await get_content(url,"json")
    return json

async def search_song(song_query):
    """ Search a song from a query using the"""
    query = "search?q=" + urllib.parse.quote(song_query)
    songs_json = await get_response(query)
    hits = songs_json["response"]["hits"]

    if len(hits) == 0:
        return None
    else:
        song_json = hits[0]["result"]
        title = song_json["title"]
        full_title = song_json["full_title"]
        artist = song_json["primary_artist"]["name"]
        song_url = song_json["url"]
        image_url = song_json["song_art_image_thumbnail_url"]
        lyrics = await get_lyrics(song_url)
        song = Song(title,full_title,artist,song_url,image_url,lyrics)
        return song


# copied from https://github.com/johnwmillr/LyricsGenius/blob/master/lyricsgenius/genius.py
# changed to be a lighter async version
async def get_lyrics(song_url):
    """Uses BeautifulSoup to scrape song info off of a Genius song URL."""

    # Scrape the song lyrics from the HTML
    #text = requests.get(song_url).text.replace('<br/>', '\n')
    text = await get_content(song_url,"bytes")
    text = text.decode('utf-8')
    text = text.replace('<br/>', '\n')
    html = BeautifulSoup(text, "html.parser" )

    # Determine the class of the div
    div = html.find("div", class_=re.compile("^lyrics$|Lyrics__Root"))
    if div is None:
        return None
    else:
        rem = div.find("div", class_=re.compile("Lyrics__Footer"))
        if rem:
            rem.replace_with("")

    lyrics = div.get_text()
    return lyrics.strip("\n")
