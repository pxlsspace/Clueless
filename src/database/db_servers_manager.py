from database.db_connection import DbConnection
from database.db_user_manager import DbUserManager

class DbServersManager():
    ''' A class to manage a discord server/guild in the database '''
    def __init__(self,db_conn:DbConnection,default_prefix) -> None:
        self.db = db_conn
        self.default_prefix = default_prefix

    ### create database tables ###
    async def create_tables(self):
        create_server_table = """
            CREATE TABLE IF NOT EXISTS server(
            server_id TEXT PRIMARY KEY, 
            prefix TEXT,
            alert_channel_id INTEGER,
            blacklist_role_id TEXTS
        );"""

        await self.db.sql_update(create_server_table)

    ### create an item in a table ###
    async def create_server(self,server_id,prefix):
        ''' add a 'server' to the database '''
        sql = ''' INSERT INTO server(server_id,prefix)
                VALUES(?,?) '''
        await self.db.sql_update(sql,(server_id,prefix))

    ### update or get server specific attributes ###
    async def update_prefix(self,prefix,server_id):
        ''' change the prefix of a server '''
        sql = ''' UPDATE server
                SET prefix = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(prefix,server_id))

    async def get_prefix(self,client,message):
        ''' get the prefix of the context of a discord message'''
        if message.guild == None:
            return ">"
        sql = '''SELECT prefix 
                    FROM server 
                    WHERE server_id = ?'''
        rows = await self.db.sql_select(sql,(message.guild.id,))
        if (len(rows))==0:
            return self.default_prefix
        return rows[0][0]

    async def update_blacklist_role(self,server_id,role_id):
        sql = ''' UPDATE server
                SET blacklist_role_id = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(role_id,server_id))

    async def get_blacklist_role(self,server_id):
        sql = """ SELECT blacklist_role_id
                FROM server
                WHERE server_id = ?"""
        res = await self.db.sql_select(sql,(server_id,))
        return res[0][0]


    ### functions useful for the milestones command ###
    async def update_alert_channel(self,server_id,channel_id):
        sql = ''' UPDATE server
                SET alert_channel_id = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(channel_id,server_id))

    async def get_alert_channel(self,server_id):
        ''' get the ID of the alert channel in a server '''
        sql = '''SELECT alert_channel_id 
                    FROM server
                    WHERE server_id = ?'''
        res = await self.db.sql_select(sql,server_id)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_all_channels(self,name):
        '''return a list of channels_id for the servers tracking the user "name"'''
        sql = '''SELECT alert_channel_id 
                FROM server
                INNER JOIN server_pxls_users
                ON server.server_id = server_pxls_users.server_id
                WHERE name = ?'''

        rows = await self.db.sql_select(sql,name)
        res=[]
        for row in rows:
            res.append(row[0])
        return res

    async def get_all_servers(self):
        ''' get a list of all the server IDs '''
        sql = "SELECT server_id from server"
        rows = await self.db.sql_select(sql)
        res = []
        for row in rows:
            res.append(row[0])
        return res

    async def get_server(self,server_id):
        sql = 'SELECT * FROM server WHERE server_id = ?'
        rows = await self.db.sql_select(sql,server_id)
        if len(rows) == 0:
            return None
        else:
            return rows[0][0]
