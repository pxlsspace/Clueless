from bs4 import BeautifulSoup
import urllib
import re
from difflib import SequenceMatcher
from utils.utils import get_content

headers = {
    "User-Agent": "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/530.4 (KHTML, like Gecko) Chrome/2.0.172.0 Safari/530.4"
}


async def search_song(query: str = None, title=None, artist=None, engine="google"):
    """return an azlyrics song url from the query or None"""

    assert engine in [
        "google",
        "azlyrics",
    ], "The user engine must be 'google' or 'azlyrics"
    assert query or title or artist, "No query, title or artist specified"

    if query:
        query = urllib.parse.quote(query)
    else:
        if title:
            title = remove_feat(title)
        query = urllib.parse.quote(f"{title or ''} {artist or ''}")

    if engine == "azlyrics":
        url = "https://search.azlyrics.com/search.php?q={}".format(query)
        response = await get_content(url, "bytes", headers=headers)
    elif engine == "google":
        url = "https://www.google.com/search?q={}+site%3Aazlyrics.com".format(query)
        cookies = {"CONSENT": "YES+1"}
        response = await get_content(url, "bytes", headers=headers, cookies=cookies)

    html_page = response.decode("utf-8")
    # Find all the URL matching the azlyrics format
    regex = r"(https:\/\/www\.azlyrics\.com\/lyrics\/(\w+)\/(\w+).html)"
    results = re.findall(regex, html_page)
    results = list(dict.fromkeys(results))  # remove duplicates
    if len(results) == 0:
        return None

    # if a specific title was given, we check that we found the correct one
    if title and not (is_similar(results[0][2], title)):
        return None
    if artist and not (is_similar(results[0][1], artist)):
        return None

    return results[0][0]


def is_similar(string1, string2):
    """Check if 2 strings are similar using SequenceMatcher"""
    string1 = string1.lower().replace(" ", "")
    string2 = string2.lower().replace(" ", "")

    # remove the 'feat' part from the titles that might make the comparison inaccurate
    string1 = remove_feat(string1)
    string2 = remove_feat(string2)

    return SequenceMatcher(None, string1, string2).ratio() > 0.8


async def get_lyrics(azlyrics_url):
    response = await get_content(azlyrics_url, "bytes", headers=headers)
    soup = BeautifulSoup(response.decode(), "html.parser")

    # get the title
    title = soup.title.string.split(" | ")[0]

    # get the lyrics
    lyrics = soup.find_all("div", {"class": None})
    lyrics = [lyric.text for lyric in lyrics]

    # clean up the lyrics
    lyrics = "\n".join(lyrics).replace("<br/>", "\n")
    lyrics = lyrics.replace("<br/>", "\n")
    lyrics = lyrics.strip("\n")
    return (title, lyrics)


def remove_feat(string):
    # remove the 'feat' part from the titles that might make the comparison inaccurate
    if "feat." in string:
        string = string.split("feat.")[0]
    if "ft." in string:
        string = string.split("ft.")[0]
    string = string.replace("(", "")
    string = string.replace(")", "")

    return string.strip(" ")
