import aiohttp
from aiohttp.client_exceptions import InvalidURL, ClientConnectionError


class BadResponseError(Exception):
    """Raised when response code isn't 200."""


async def get_content(url: str, content_type, **kwargs):
    """Send a GET request to the url and return the response as json or bytes.
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
                        content_type = r.headers["content-type"]
                        if "image" not in content_type:
                            raise ValueError("The URL doesn't contain any image.")
                        else:
                            return await r.read()
                else:
                    raise BadResponseError(f"The URL leads to an error {r.status}")
        except (InvalidURL, ClientConnectionError):
            raise ValueError("The URL provided is invalid.")


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
