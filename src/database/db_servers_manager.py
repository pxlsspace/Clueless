from database.db_connection import DbConnection

class DbServersManager():
    ''' A class to manage a discord server/guild in the database '''
    def __init__(self,db_conn:DbConnection,default_prefix) -> None:
        self.db = db_conn
        self.default_prefix = default_prefix

    ### create database tables ###
    async def create_tables(self):
        create_servers_table = """CREATE TABLE IF NOT EXISTS servers(
                            server_id INTEGER PRIMARY KEY, 
                            prefix TEXT,
                            alert_channel_id INTEGER,
                            blacklist_role_id TEXTS
                        );"""

        create_server_pxls_users_table = """ CREATE TABLE IF NOT EXISTS server_pxls_users(
                        server_id INTEGER,
                        name TEXT,
                        FOREIGN KEY(server_id) REFERENCES servers(server_id),
                        FOREIGN KEY(name) REFERENCES pxls_users(name),
                        PRIMARY KEY(name,server_id)
                    );"""

        create_pxls_users_table = """ CREATE TABLE IF NOT EXISTS pxls_users(
                                    name TEXT PRIMARY KEY,
                                    pixel_count INTEGER
                                );"""

        await self.db.sql_update(create_servers_table)
        await self.db.sql_update(create_pxls_users_table)
        await self.db.sql_update(create_server_pxls_users_table)

    ### create an item in a table ###
    async def create_server(self,server_id,prefix):
        ''' create the 'servers' table '''
        sql = ''' INSERT INTO servers(server_id,prefix)
                VALUES(?,?) '''
        await self.db.sql_update(sql,(server_id,prefix))

    async def create_pxls_user(self, name, pxls_count):
        ''' create the 'pxls_users' table '''
        sql = ''' INSERT INTO pxls_users(name, pixel_count)
                VALUES(?,?) '''
        await self.db.sql_update(sql, (name,pxls_count))

    async def create_server_pxls_user(self, server_id,name):
        ''' create the 'server_pxls_users' table '''
        sql = ''' INSERT INTO server_pxls_users(server_id, name)
                VALUES(?,?) '''
        await self.db.sql_update(sql,(server_id,name))


    ### update or get server specific attributes ###
    async def update_prefix(self,prefix,server_id):
        ''' change the prefix of a server '''
        sql = ''' UPDATE servers
                SET prefix = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(prefix,server_id))

    async def get_prefix(self,client,message):
        ''' get the prefix of the context of a discord message'''
        if message.guild == None:
            return ">"
        sql = '''SELECT prefix 
                    FROM servers 
                    WHERE server_id = ?'''
        rows = await self.db.sql_select(sql,(message.guild.id,))
        if (len(rows))==0:
            return self.default_prefix
        return rows[0][0]

    async def update_blacklist_role(self,server_id,role_id):
        sql = ''' UPDATE servers
                SET blacklist_role_id = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(role_id,server_id))

    async def get_blacklist_role(self,server_id):
        sql = """ SELECT blacklist_role_id
                FROM servers
                WHERE server_id = ?"""
        res = await self.db.sql_select(sql,(server_id,))
        return res[0][0]


    ### functions useful for the milestones command ###

    # adds a user to the server_pxls_user table and pxls_user table if not added
    # returns -1 if the user was already added 
    async def add_user(self,server_id,name,pxls_count):

        # create pxls_user if it doesnt exist
        sql = "SELECT * FROM pxls_users WHERE name = ?"
        res = await self.db.sql_select(sql,name)
        if (len(res) == 0):
            await self.create_pxls_user(name,pxls_count)
        # create join table entry (server_pxls_users)
        await self.create_server_pxls_user(server_id,name)
        return name

    async def remove_user(self,server_id,name):
        # removing the user from the server_pixel_users table
        sql = "DELETE from server_pxls_users WHERE server_id = ? AND name = ?"

        total_changes = await self.db.sql_update(sql,(server_id,name))
        # check if the user has been deleted
        if (total_changes == 0):
            # no changes have been made
            return -1
        
        # check if the user is still in other servers
        sql = "SELECT COUNT(*) FROM server_pxls_users WHERE name=?"
        res = await self.db.sql_select(sql,(name,))
        nb_of_user_servers = res[0][0]

        # if not, remove it from the pxls_users table too
        if (nb_of_user_servers == 0):
            sql = "DELETE from pxls_users WHERE name = ?"
            await self.db.sql_update(sql,name)

    async def update_alert_channel(self,server_id,channel_id):
        sql = ''' UPDATE servers
                SET alert_channel_id = ?
                WHERE server_id = ?'''
        await self.db.sql_update(sql,(channel_id,server_id))

    async def get_alert_channel(self,server_id):
        ''' get the ID of the alert channel in a server '''
        sql = '''SELECT alert_channel_id 
                    FROM servers 
                    WHERE server_id = ?'''
        res = await self.db.sql_select(sql,server_id)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_all_channels(self,name):
        '''return a list of channels_id for the servers tracking the user "name"'''
        sql = '''SELECT alert_channel_id 
                FROM servers
                INNER JOIN server_pxls_users
                ON servers.server_id = server_pxls_users.server_id
                WHERE name = ?'''

        rows = await self.db.sql_select(sql,name)
        res=[]
        for row in rows:
            res.append(row[0])
        return res

    async def get_all_server_users(self,server_id):
        ''' returns a list of all the users tracked in a server '''
        sql = '''SELECT pxls_users.name, pxls_users.pixel_count 
                FROM pxls_users
                INNER JOIN server_pxls_users
                ON server_pxls_users.name = pxls_users.name
                WHERE server_pxls_users.server_id = ?'''
        rows = await self.db.sql_select(sql,server_id)
        return rows

    async def get_all_users(self):
        ''' Get all the users ([name,pixel count]) tracked in at least one server'''
        sql = "SELECT name, pixel_count from pxls_users"
        rows = await self.db.sql_select(sql)
        return rows

    async def get_all_servers(self):
        ''' get a list of all the server IDs '''
        sql = "SELECT server_id from servers"
        rows = await self.db.sql_select(sql)
        res = []
        for row in rows:
            res.append(row[0])
        return res

    async def update_pixel_count(self,name,new_count):
        ''' update the pixel count for a tracked user'''
        sql = ''' UPDATE pxls_users
                SET pixel_count = ?
                WHERE name = ?'''
        await self.db.sql_update(sql,(new_count,name))
