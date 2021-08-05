from utils.pxls_stats_manager import PxlsStatsManager
from database.db_connection import DbConnection
from database.db_servers_manager import DbServersManager
from database.db_stats_manager import DbStatsManager

stats =  PxlsStatsManager()
DEFAULT_PREFIX = ">"

db_connection = DbConnection()
db_stats_manager = DbStatsManager(db_connection)
db_servers_manager = DbServersManager(db_connection,DEFAULT_PREFIX)
