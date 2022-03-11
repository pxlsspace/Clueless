# by @netux

import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import pytz

GMT_TIMEZONE_REGEX = re.compile(
    r"^(?:GMT|UTC)(?P<offset_hours>[+-]?[0-2]?[0-9])(?::(?P<offset_minutes>[0-5][0-9]|60))?$",
    re.IGNORECASE,
)

timezones = {
    "ACDT": timedelta(hours=10, minutes=30),
    "ACST": timedelta(hours=9, minutes=30),
    "ACWST": timedelta(hours=8, minutes=45),
    "ADT": timedelta(hours=-3),
    "AEDT": timedelta(hours=11),
    "AEST": timedelta(hours=10),
    "AET": timedelta(hours=10),
    "AFT": timedelta(hours=4, minutes=30),
    "AKDT": timedelta(hours=-8),
    "AKST": timedelta(hours=-9),
    "ALMT": timedelta(hours=6),
    "AMST": timedelta(hours=-3),
    "AMT": timedelta(hours=-4),
    "ANAT": timedelta(hours=12),
    "AQTT": timedelta(hours=5),
    "ART": timedelta(hours=-3),
    "AST": timedelta(hours=-4),
    "AWST": timedelta(hours=8),
    "AZOST": timedelta(hours=0),
    "AZOT": timedelta(hours=-1),
    "AZT": timedelta(hours=4),
    "BDT": timedelta(hours=8),
    "BIOT": timedelta(hours=6),
    "BIT": timedelta(hours=-12),
    "BOT": timedelta(hours=-4),
    "BRST": timedelta(hours=-2),
    "BRT": timedelta(hours=-3),
    "BST": timedelta(hours=1),
    "BTT": timedelta(hours=6),
    "CAT": timedelta(hours=2),
    "CCT": timedelta(hours=6, minutes=30),
    "CDT": timedelta(hours=-5),
    "CEST": timedelta(hours=2),
    "CET": timedelta(hours=1),
    "CHADT": timedelta(hours=13, minutes=45),
    "CHAST": timedelta(hours=12, minutes=45),
    "CHOT": timedelta(hours=8),
    "CHOST": timedelta(hours=9),
    "CHST": timedelta(hours=10),
    "CHUT": timedelta(hours=10),
    "CIST": timedelta(hours=-8),
    "CIT": timedelta(hours=8),
    "CKT": timedelta(hours=-10),
    "CLST": timedelta(hours=-3),
    "CLT": timedelta(hours=-4),
    "COST": timedelta(hours=-4),
    "COT": timedelta(hours=-5),
    "CST": timedelta(hours=-6),
    "CT": timedelta(hours=8),
    "CVT": timedelta(hours=-1),
    "CWST": timedelta(hours=8, minutes=45),
    "CXT": timedelta(hours=7),
    "DAVT": timedelta(hours=7),
    "DDUT": timedelta(hours=10),
    "DFT": timedelta(hours=1),
    "EASST": timedelta(hours=-5),
    "EAST": timedelta(hours=-6),
    "EAT": timedelta(hours=3),
    "ECT": timedelta(hours=-5),
    "EDT": timedelta(hours=-4),
    "EEST": timedelta(hours=3),
    "EET": timedelta(hours=2),
    "EGST": timedelta(hours=0),
    "EGT": timedelta(hours=-1),
    "EIT": timedelta(hours=9),
    "EST": timedelta(hours=-5),
    "FET": timedelta(hours=3),
    "FJT": timedelta(hours=12),
    "FKST": timedelta(hours=-3),
    "FKT": timedelta(hours=-4),
    "FNT": timedelta(hours=-2),
    "GALT": timedelta(hours=-6),
    "GAMT": timedelta(hours=-9),
    "GET": timedelta(hours=4),
    "GFT": timedelta(hours=-3),
    "GILT": timedelta(hours=12),
    "GIT": timedelta(hours=-9),
    "GMT": timedelta(hours=0),
    "GST": timedelta(hours=4),
    "GYT": timedelta(hours=-4),
    "HDT": timedelta(hours=-9),
    "HAEC": timedelta(hours=2),
    "HST": timedelta(hours=-10),
    "HKT": timedelta(hours=8),
    "HMT": timedelta(hours=5),
    "HOVST": timedelta(hours=8),
    "HOVT": timedelta(hours=7),
    "ICT": timedelta(hours=7),
    "IDLW": timedelta(hours=-12),
    "IDT": timedelta(hours=3),
    "IOT": timedelta(hours=3),
    "IRDT": timedelta(hours=4, minutes=30),
    "IRKT": timedelta(hours=8),
    "IRST": timedelta(hours=3, minutes=30),
    "IST": timedelta(hours=5, minutes=30),
    "JST": timedelta(hours=9),
    "KALT": timedelta(hours=2),
    "KGT": timedelta(hours=6),
    "KOST": timedelta(hours=11),
    "KRAT": timedelta(hours=7),
    "KST": timedelta(hours=9),
    "LHST": timedelta(hours=10, minutes=30),
    "LINT": timedelta(hours=14),
    "MAGT": timedelta(hours=12),
    "MART": timedelta(hours=-9, minutes=30),
    "MAWT": timedelta(hours=5),
    "MDT": timedelta(hours=-6),
    "MET": timedelta(hours=1),
    "MEST": timedelta(hours=2),
    "MHT": timedelta(hours=12),
    "MIST": timedelta(hours=11),
    "MIT": timedelta(hours=-9, minutes=30),
    "MMT": timedelta(hours=6, minutes=30),
    "MSK": timedelta(hours=3),
    "MST": timedelta(hours=-7),
    "MUT": timedelta(hours=4),
    "MVT": timedelta(hours=5),
    "MYT": timedelta(hours=8),
    "NCT": timedelta(hours=11),
    "NDT": timedelta(hours=-2, minutes=30),
    "NFT": timedelta(hours=11),
    "NOVT": timedelta(hours=7),
    "NPT": timedelta(hours=5, minutes=45),
    "NST": timedelta(hours=-3, minutes=30),
    "NT": timedelta(hours=-3, minutes=30),
    "NUT": timedelta(hours=-11),
    "NZDT": timedelta(hours=13),
    "NZST": timedelta(hours=12),
    "OMST": timedelta(hours=6),
    "ORAT": timedelta(hours=5),
    "PDT": timedelta(hours=-7),
    "PET": timedelta(hours=-5),
    "PETT": timedelta(hours=12),
    "PGT": timedelta(hours=10),
    "PHOT": timedelta(hours=13),
    "PHT": timedelta(hours=8),
    "PKT": timedelta(hours=5),
    "PMDT": timedelta(hours=-2),
    "PMST": timedelta(hours=-3),
    "PONT": timedelta(hours=11),
    "PST": timedelta(hours=-8),
    "PYST": timedelta(hours=-3),
    "PYT": timedelta(hours=-4),
    "RET": timedelta(hours=4),
    "ROTT": timedelta(hours=-3),
    "SAKT": timedelta(hours=11),
    "SAMT": timedelta(hours=4),
    "SAST": timedelta(hours=2),
    "SBT": timedelta(hours=11),
    "SCT": timedelta(hours=4),
    "SDT": timedelta(hours=-10),
    "SGT": timedelta(hours=8),
    "SLST": timedelta(hours=5, minutes=30),
    "SRET": timedelta(hours=11),
    "SRT": timedelta(hours=-3),
    "SST": timedelta(hours=-11),
    "SYOT": timedelta(hours=3),
    "TAHT": timedelta(hours=-10),
    "THA": timedelta(hours=7),
    "TFT": timedelta(hours=5),
    "TJT": timedelta(hours=5),
    "TKT": timedelta(hours=13),
    "TLT": timedelta(hours=9),
    "TMT": timedelta(hours=5),
    "TRT": timedelta(hours=3),
    "TOT": timedelta(hours=13),
    "TVT": timedelta(hours=12),
    "ULAST": timedelta(hours=9),
    "ULAT": timedelta(hours=8),
    "UTC": timedelta(hours=0),
    "UYST": timedelta(hours=-2),
    "UYT": timedelta(hours=-3),
    "UZT": timedelta(hours=5),
    "VET": timedelta(hours=-4),
    "VLAT": timedelta(hours=10),
    "VOLT": timedelta(hours=4),
    "VOST": timedelta(hours=6),
    "VUT": timedelta(hours=11),
    "WAKT": timedelta(hours=12),
    "WAST": timedelta(hours=2),
    "WAT": timedelta(hours=1),
    "WEST": timedelta(hours=1),
    "WET": timedelta(hours=0),
    "WIT": timedelta(hours=7),
    "WGST": timedelta(hours=-2),
    "WGT": timedelta(hours=-3),
    "WST": timedelta(hours=8),
    "YAKT": timedelta(hours=9),
    "YEKT": timedelta(hours=5),
}


def get_timezone_utcoffset(s: str):
    if gmt_match := GMT_TIMEZONE_REGEX.match(s):
        offset_hours = int(gmt_match.group("offset_hours"))
        offset_minutes = int(gmt_match.group("offset_minutes") or "0")
        return timedelta(hours=offset_hours, minutes=offset_minutes)

    else:
        try:
            offset = ZoneInfo(s).utcoffset(datetime.now())
            return offset
        except ZoneInfoNotFoundError:
            for tz_name in timezones.keys():
                if s.upper() == tz_name:
                    return timezones[tz_name]

        try:
            offset = pytz.timezone(s).utcoffset(datetime.now())
            return offset
        except pytz.UnknownTimeZoneError:
            pass
    return None


def get_timezone(name: str):
    try:
        offset = get_timezone_utcoffset(name)
        return timezone(offset, name=name) if offset is not None else None
    except Exception:
        return None
