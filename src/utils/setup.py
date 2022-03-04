from dotenv import load_dotenv
import os
import sys

from database.db_user_manager import DbUserManager
from database.db_connection import DbConnection
from database.db_servers_manager import DbServersManager
from database.db_stats_manager import DbStatsManager
from database.db_template_manager import DbTemplateManager
from utils.pxls.websocket_client import WebsocketClient
from utils.pxls.pxls_stats_manager import PxlsStatsManager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
load_dotenv()

VERSION = "2.1.0"
BOT_INVITE = os.getenv("BOT_INVITE")
SERVER_INVITE = os.getenv("SERVER_INVITE")

# database connection
db_conn = DbConnection()

# connection with the pxls API
stats = PxlsStatsManager(db_conn)

# default prefix
DEFAULT_PREFIX = ">"

# database managers
db_stats = DbStatsManager(db_conn, stats)
db_servers = DbServersManager(db_conn, DEFAULT_PREFIX)
db_users = DbUserManager(db_conn)
db_templates = DbTemplateManager(db_conn)

# websocket
uri = "wss://pxls.space/ws"
ws_client = WebsocketClient(uri, stats)

# guild IDs
test_server_id = os.getenv("TEST_SERVER_ID")
if test_server_id:
    # add the commands only to the testing server
    GUILD_IDS = [int(test_server_id)]
else:
    # add the commands globally
    GUILD_IDS = None
