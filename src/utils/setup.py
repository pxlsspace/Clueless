from database.db_user_manager import DbUserManager
from utils.pxls.pxls_stats_manager import PxlsStatsManager
from database.db_connection import DbConnection
from database.db_servers_manager import DbServersManager
from database.db_stats_manager import DbStatsManager
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

db_conn = DbConnection()

stats =  PxlsStatsManager(db_conn)
DEFAULT_PREFIX = ">"

db_stats = DbStatsManager(db_conn,stats)
db_servers = DbServersManager(db_conn,DEFAULT_PREFIX)
db_users = DbUserManager(db_conn)