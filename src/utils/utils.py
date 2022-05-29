from __future__ import annotations

import asyncio
import base64
import functools
import re
import timeit
from typing import Awaitable, Callable, Optional, TypeVar

import aiohttp
import numpy as np
from aiohttp.client_exceptions import ClientConnectionError, InvalidURL
from typing_extensions import ParamSpec

T = TypeVar("T")
P = ParamSpec("P")
_MaybeEventLoop = Optional[asyncio.AbstractEventLoop]


class BadResponseError(Exception):
    """Raised when response code isn't 200."""


async def get_content(url: str, content_type, **kwargs):
    """Send a GET request to the url and return the response as json or bytes.
    Raise BadResponseError or ValueError."""
    # check if the URL is a data URL
    data = check_data_url(url)
    if data:
        return data
    timeout = aiohttp.ClientTimeout(
        sock_connect=10.0, sock_read=10.0
    )  # set a timeout of 10 seconds
    async with aiohttp.ClientSession(timeout=timeout, **kwargs) as session:
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    if content_type == "json":
                        return await r.json()
                    if content_type == "bytes":
                        return await r.read()
                    if content_type == "image":
                        content_type = r.headers["content-type"]
                        if "image" not in content_type:
                            raise ValueError("The URL doesn't contain any image.")
                        else:
                            return await r.read()
                else:
                    raise BadResponseError(f"The URL leads to an error {r.status}")
        except InvalidURL:
            raise ValueError("The URL provided is invalid.")
        except asyncio.TimeoutError:
            raise ValueError("Couldn't connect to URL. (Timeout)")
        except ClientConnectionError:
            raise ValueError("Couldn't connect to URL.")


def check_data_url(url):
    """Check if the URL is a data URL (format: 'data:[<mediatype>][;base64],<data>')
    return:
    - the URL converted to bytes if it is data URL
    - `None` if it isn't a data URL"""
    data_url_regex = r"^data:([\w\/\+-]*)(;charset=[\w-]+)?(;base64)?,(.*)"
    match = re.match(data_url_regex, url)
    if not match:
        return None
    groups = match.groups()
    mime_type = groups[0]
    encoding = groups[2]
    data = groups[3]
    if "image" not in mime_type:
        raise ValueError("Only images are supported with data URLs.")

    if "base64" in encoding:
        data_bytes = base64.b64decode(data)
    else:
        data_bytes = data
    return data_bytes


def make_progress_bar(percentage, nb_char=20):
    full = "​█"
    empty = " "
    res_bar = ""
    bar_idx = int((percentage / 100) * nb_char)
    for i in range(nb_char):
        if i < bar_idx:
            res_bar += full
        else:
            res_bar += empty
    return res_bar


def ordinal(n):
    """Get a rank suffix (1 -> 1st, 2 -> 2nd, ...)"""
    return "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4])


def chunk(a, n):
    """Divide an array `a` into `n` sub arrays"""
    k, m = divmod(len(a), n)
    return [a[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)] for i in range(n)]


def shorten_list(input_list: list, nb_element: int) -> list:
    """Shorten a list by keeping evenly spaced elements"""
    idx = np.round(np.linspace(0, len(input_list) - 1, nb_element)).astype(int)
    return np.array(input_list)[idx].tolist()


# from https://github.com/InterStella0/stella_bot/blob/6f273318c06e86fe3ba9cad35bc62e899653f031/utils/decorators.py#L108-L117
def in_executor(
    loop: _MaybeEventLoop = None,
) -> Callable[[Callable[P, T]], Callable[P, Awaitable[T]]]:
    """Make a sync blocking function unblocking and async"""
    loop_ = loop or asyncio.get_event_loop()

    def inner_function(func: Callable[P, T]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        def function(*args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
            partial = functools.partial(func, *args, **kwargs)
            return loop_.run_in_executor(None, partial)

        return function

    return inner_function


class CodeTimer:
    """Class used for debug to time blocks of code.

    Example
    >>> with CodeTimer("func1"):
    >>>     func1()
    prints: 'func1' took: 102.01 ms"""

    def __init__(self, name=None, unit="ms"):
        assert unit in ["ms", "s"]
        self.name = f"'{name}'" if name else "Code block"
        self.unit = unit

    def __enter__(self):
        print(f"Starting {self.name}...", end="")
        self.start = timeit.default_timer()

    def __exit__(self, exc_type, exc_value, traceback):
        self.took = (timeit.default_timer() - self.start) * (
            1000.0 if self.unit == "ms" else 1.0
        )
        print(f"done! (took: {round(self.took, 4)} {self.unit})")


# mapping of languages (ISO 639-1) to country codes (ISO 3166-1) as emojis
# see https://wiki.openstreetmap.org/wiki/Nominatim/Country_Codes
LANG2FLAG = {
    "af": "🇿🇦",
    "sq": "🇦🇱",
    "am": "🇪🇹",
    "ar": "🇩🇯",
    "hy": "🇦🇲",
    "az": "🇦🇿",
    "eu": "🇪🇸",
    "be": "🇧🇾",
    "bn": "🇧🇩",
    "bs": "🇧🇦",
    "bg": "🇧🇬",
    "ca": "🇦🇩",
    "ceb": "🇵🇭",
    "ny": "🇲🇼",
    "zh-cn": "🇨🇳",
    "zh-tw": "🇨🇳",
    "co": "🇫🇷",
    "hr": "🇭🇷",
    "cs": "🇨🇿",
    "da": "🇩🇰",
    "nl": "🇳🇱",
    "en": "🇬🇧",
    "eo": None,
    "et": "🇪🇪",
    "tl": "🇵🇭",
    "fi": "🇫🇮",
    "fr": "🇫🇷",
    "fy": None,
    "gl": None,
    "ka": "🇬🇪",
    "de": "🇩🇪",
    "el": "🇬🇷",
    "gu": "🇮🇳",
    "ht": "🇭🇹",
    "ha": "🇭🇦",
    "haw": None,
    "iw": "🇮🇱",
    "he": "🇮🇱",
    "hi": "🇮🇳",
    "hmn": None,
    "hu": "🇭🇺",
    "is": "🇮🇸",
    "ig": "🇳🇬",
    "id": "🇮🇩",
    "ga": "🇮🇪",
    "it": "🇮🇹",
    "ja": "🇯🇵",
    "jw": None,
    "kn": None,
    "kk": "🇰🇿",
    "km": "🇰🇭",
    "ko": "🇰🇷",
    "ku": "🇮🇶",
    "ky": "🇰🇬",
    "lo": "🇱🇦",
    "la": "🇻🇦",
    "lv": "🇱🇻",
    "lt": "🇱🇹",
    "lb": "🇱🇺",
    "mk": "🇲🇰",
    "mg": "🇲🇬",
    "ms": "🇲🇾",
    "ml": None,
    "mt": "🇲🇹",
    "mi": "🇳🇿",
    "mr": None,
    "mn": "🇲🇳",
    "my": "🇲🇲",
    "ne": "🇳🇵",
    "no": "🇳🇴",
    "or": None,
    "ps": "🇦🇫",
    "fa": "🇮🇷",
    "pl": "🇵🇱",
    "pt": "🇵🇹",
    "pa": "🇮🇳",
    "ro": "🇷🇴",
    "ru": "🇷🇺",
    "sm": None,
    "gd": None,
    "sr": "🇷🇸",
    "st": "🇱🇸",
    "sn": "🇿🇼",
    "sd": None,
    "si": "🇱🇰",
    "sk": "🇸🇰",
    "sl": "🇸🇮",
    "so": "🇸🇴",
    "es": "🇪🇸",
    "su": None,
    "sw": "🇸🇼",
    "sv": "🇸🇪",
    "tg": "🇹🇯",
    "ta": "🇱🇰",
    "te": "🇮🇳",
    "th": "🇹🇭",
    "tr": "🇹🇷",
    "uk": "🇺🇦",
    "ur": "🇵🇰",
    "ug": None,
    "uz": "🇺🇿",
    "vi": "🇻🇳",
    "cy": "🇬🇧",
    "xh": "🇿🇦",
    "yi": None,
    "yo": "🇾🇴",
    "zu": "🇿🇦",
}


def get_lang_emoji(lang):
    """Get a country emoji from a language ISO 639-1 code."""
    return LANG2FLAG.get(lang)
