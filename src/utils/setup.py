import os
import sys

from dotenv import load_dotenv

from database.db_canvas_manager import DbCanvasManager
from database.db_connection import DbConnection
from database.db_servers_manager import DbServersManager
from database.db_stats_manager import DbStatsManager
from database.db_template_manager import DbTemplateManager
from database.db_user_manager import DbUserManager
from utils.image.imgur import Imgur
from utils.pxls.pxls_stats_manager import PxlsStatsManager
from utils.pxls.websocket_client import WebsocketClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
load_dotenv()

VERSION = "2.8.1"
BOT_INVITE = os.getenv("BOT_INVITE")
SERVER_INVITE = os.getenv("SERVER_INVITE")

# pxls URLs
PXLS_URL = os.getenv("PXLS_URL")
PXLS_URL_API = os.getenv("PXLS_URL_API")

# database connection
db_conn = DbConnection()

# connection with the pxls API
stats = PxlsStatsManager(db_conn, PXLS_URL_API)

# default prefix
DEFAULT_PREFIX = ">"

# database managers
db_stats = DbStatsManager(db_conn, stats)
db_servers = DbServersManager(db_conn, DEFAULT_PREFIX)
db_users = DbUserManager(db_conn)
db_templates = DbTemplateManager(db_conn)
db_canvas = DbCanvasManager(db_conn)

# websocket
ws_uri = os.getenv("PXLS_WEBSOCKET")
ws_client = WebsocketClient(ws_uri, stats)

# guild IDs
test_server_id = os.getenv("TEST_SERVER_ID")
if test_server_id:
    # add the commands only to the testing server
    GUILD_IDS = [int(test_server_id)]
else:
    # add the commands globally
    GUILD_IDS = None

guild_members_minimum = os.getenv("GUILD_MEMBER_MIN")
if guild_members_minimum:
    GUILD_MEMBER_MIN = int(guild_members_minimum)
else:
    GUILD_MEMBER_MIN = int(0)

# imgur app
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")
IMGUR_CLIENT_SECRET = os.getenv("IMGUR_CLIENT_SECRET")
IMGUR_ACCESS_TOKEN = os.getenv("IMGUR_ACCESS_TOKEN")
IMGUR_REFRESH_TOKEN = os.getenv("IMGUR_REFRESH_TOKEN")

imgur_app = Imgur(
    IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET, IMGUR_REFRESH_TOKEN, IMGUR_ACCESS_TOKEN
)
