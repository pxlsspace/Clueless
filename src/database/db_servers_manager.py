from database.db_connection import DbConnection
from sqlite3 import OperationalError, IntegrityError


class DbServersManager():
    """A class to manage a discord server/guild in the database"""

    def __init__(self, db_conn: DbConnection, default_prefix) -> None:
        self.db = db_conn
        self.default_prefix = default_prefix

    async def create_tables(self):
        """create database tables"""
        create_server_table = """
            CREATE TABLE IF NOT EXISTS server(
                server_id TEXT PRIMARY KEY,
                prefix TEXT,
                alert_channel_id INTEGER,
                blacklist_role_id TEXT
            );
        """
        add_server_snapshots_channel = (
            "ALTER TABLE server ADD COLUMN snapshots_channel_id TEXT"
        )

        create_command_usage_table = """
            CREATE TABLE IF NOT EXISTS command_usage(
                command_name TEXT,
                is_dm BOOLEAN,
                server_name TEXT,
                channel_id TEXT,
                author_id TEXT,
                datetime TIMESTAMP,
                args TEXT,
                is_slash BOOLEAN
            );
        """

        await self.db.sql_update(create_server_table)
        try:
            await self.db.sql_update(add_server_snapshots_channel)
        except OperationalError:
            pass
        await self.db.sql_update(create_command_usage_table)

    async def create_server(self, server_id, prefix):
        """add a 'server' to the database"""
        sql = """ INSERT INTO server(server_id,prefix)
                VALUES(?,?) """
        try:
            return await self.db.sql_update(sql, (server_id, prefix))
        except IntegrityError:
            return 0

    async def delete_server(self, server_id):
        """remove a server from the database"""
        sql = """ DELETE FROM server WHERE server_id = ? """
        return await self.db.sql_update(sql, server_id)

    async def update_prefix(self, prefix, server_id):
        """change the prefix of a server"""
        sql = """ UPDATE server
                SET prefix = ?
                WHERE server_id = ?"""
        await self.db.sql_update(sql, (prefix, server_id))

    async def get_prefix(self, client, message):
        """get the prefix of the context of a discord message"""
        if message.guild is None:
            return ">"
        sql = """SELECT prefix
                    FROM server
                    WHERE server_id = ?"""
        rows = await self.db.sql_select(sql, (message.guild.id,))
        if len(rows) == 0:
            return self.default_prefix
        return rows[0][0]

    async def update_blacklist_role(self, server_id, role_id):
        sql = """ UPDATE server
                SET blacklist_role_id = ?
                WHERE server_id = ?"""
        await self.db.sql_update(sql, (role_id, server_id))

    async def get_blacklist_role(self, server_id):
        sql = """ SELECT blacklist_role_id
                FROM server
                WHERE server_id = ?"""
        res = await self.db.sql_select(sql, (server_id,))
        return res[0][0]

    # functions useful for the milestones command #
    async def update_alert_channel(self, server_id, channel_id):
        sql = """ UPDATE server
                SET alert_channel_id = ?
                WHERE server_id = ?"""
        await self.db.sql_update(sql, (channel_id, server_id))

    async def get_alert_channel(self, server_id):
        """get the ID of the alert channel in a server"""
        sql = """SELECT alert_channel_id
                    FROM server
                    WHERE server_id = ?"""
        res = await self.db.sql_select(sql, server_id)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_all_channels(self, name):
        '''return a list of channels_id for the servers tracking the user "name"'''
        sql = """SELECT alert_channel_id
                FROM server
                INNER JOIN server_pxls_users
                ON server.server_id = server_pxls_users.server_id
                WHERE name = ?"""

        rows = await self.db.sql_select(sql, name)
        res = []
        for row in rows:
            res.append(row[0])
        return res

    # functions useful for the snapshots #
    async def update_snapshots_channel(self, server_id, channel_id):
        sql = """
            UPDATE server
            SET snapshots_channel_id = ?
            WHERE server_id = ?"""
        await self.db.sql_update(sql, (channel_id, server_id))

    async def get_snapshots_channel(self, server_id):
        """get the ID of the snapshots channel in a server"""
        sql = """
            SELECT snapshots_channel_id
            FROM server
            WHERE server_id = ?"""
        res = await self.db.sql_select(sql, server_id)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_all_snapshots_channels(self):
        """return a list of channels_id for the servers using snapshots"""
        sql = """
            SELECT snapshots_channel_id
            FROM server
            WHERE snapshots_channel_id IS NOT NULL"""
        rows = await self.db.sql_select(sql)
        res = []
        for row in rows:
            res.append(row[0])
        return res

    async def get_all_servers(self):
        """get a list of all the server IDs"""
        sql = "SELECT server_id from server"
        rows = await self.db.sql_select(sql)
        res = []
        for row in rows:
            res.append(row[0])
        return res

    async def get_server(self, server_id):
        sql = "SELECT * FROM server WHERE server_id = ?"
        rows = await self.db.sql_select(sql, server_id)
        if len(rows) == 0:
            return None
        else:
            return rows[0][0]

    async def create_command_usage(self, command_name, is_dm, server_name,
                                   channel_id, author_id, datetime, args, is_slash):
        sql = """
            INSERT INTO command_usage(
                command_name,
                is_dm,
                server_name,
                channel_id,
                author_id,
                datetime,
                args,
                is_slash
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?) """

        return await self.db.sql_update(
            sql,
            (
                command_name,
                is_dm,
                server_name,
                channel_id,
                author_id,
                datetime,
                args,
                is_slash,
            ),
        )
