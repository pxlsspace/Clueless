from database.db_user_manager import DbUserManager
from utils.pxls.pxls_stats_manager import PxlsStatsManager
from database.db_connection import DbConnection
from database.db_servers_manager import DbServersManager
from database.db_stats_manager import DbStatsManager
from utils.pxls.websocket_client import WebsocketClient
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# database connection
db_conn = DbConnection()

# connection with the pxls API
stats =  PxlsStatsManager(db_conn)

# default prefix
DEFAULT_PREFIX = ">"

# database managers
db_stats = DbStatsManager(db_conn,stats)
db_servers = DbServersManager(db_conn,DEFAULT_PREFIX)
db_users = DbUserManager(db_conn)

# websocket
uri = "wss://pxls.space/ws"
ws_client = WebsocketClient(uri,stats)
