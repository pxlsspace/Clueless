import aiohttp
from aiohttp.client_exceptions import InvalidURL, ClientConnectionError


class BadResponseError(Exception):
    """ Raised when response code isn't 200."""

async def get_content(url:str,content_type,**kwargs):
    """ Send a GET request to the url and return the response as json or bytes.
    Raise BadResponseError or ValueError."""
    async with aiohttp.ClientSession(**kwargs) as session:
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    if content_type == "json":
                        return await r.json()
                    if content_type == "bytes":
                        return await r.read()
                    if content_type == "image":
                        content_type = r.headers['content-type']
                        if not 'image' in content_type:
                            raise ValueError("The URL doesn't contain any image.")
                        else:
                            return await r.read()
                else:
                    raise BadResponseError(f"The URL leads to an error {r.status}")
        except (InvalidURL, ClientConnectionError):
            raise ValueError ("The URL provided is invalid.")

def make_progress_bar(percentage,nb_char=20):
    full = "​█"
    empty = " "
    res_bar = ""
    bar_idx = int((percentage/100)*nb_char)
    for i in range(nb_char):
        if i < bar_idx:
            res_bar += full
        else:
            res_bar += empty
    return res_bar
