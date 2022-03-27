import sqlite3
from database.db_connection import DbConnection


class DbUserManager:
    """A class to manage a discord and pxls user in the database"""

    def __init__(self, db_conn: DbConnection) -> None:
        self.db = db_conn

    async def create_tables(self):

        create_pxls_user_table = """
            CREATE TABLE IF NOT EXISTS pxls_user(
            pxls_user_id INTEGER PRIMARY KEY
        );"""

        create_pxls_name_table = """
            CREATE TABLE IF NOT EXISTS pxls_name(
            pxls_name_id INTEGER PRIMARY KEY,
            pxls_user_id INTEGER,
            name TEXT UNIQUE,
            FOREIGN KEY(pxls_user_id) REFERENCES pxls_user(pxls_user_id)
        );"""

        create_discord_user = """
            CREATE TABLE IF NOT EXISTS discord_user(
                discord_id TEXT PRIMARY KEY,
                pxls_user_id INTEGER,
                color TEXT,
                is_blacklisted BOOLEAN DEFAULT 0,
                FOREIGN KEY(pxls_user_id) REFERENCES pxls_user(pxls_user_id)
        );"""
        add_discord_user_timezone = "ALTER TABLE discord_user ADD COLUMN timezone TEXT"
        add_discord_user_font = "ALTER TABLE discord_user ADD COLUMN font TEXT"

        create_server_pxls_users_table = """
            CREATE TABLE IF NOT EXISTS server_pxls_user(
            pxls_user_id INTEGER,
            server_id TEXT,
            FOREIGN KEY(server_id) REFERENCES server(server_id),
            FOREIGN KEY(pxls_user_id) REFERENCES pxls_user(pxls_user_id),
            PRIMARY KEY(pxls_user_id,server_id)
        );"""

        create_user_keys_table = """
            CREATE TABLE IF NOT EXISTS log_key(
                discord_id TEXT,
                canvas_code TEXT,
                key TEXT,
                PRIMARY KEY(discord_id, canvas_code),
                FOREIGN KEY(discord_id) REFERENCES discord_user(discord_id)
            )
        """
        await self.db.sql_update(create_pxls_user_table)
        await self.db.sql_update(create_pxls_name_table)
        await self.db.sql_update(create_discord_user)
        try:
            await self.db.sql_update(add_discord_user_timezone)
        except sqlite3.OperationalError:
            pass
        try:
            await self.db.sql_update(add_discord_user_font)
        except sqlite3.OperationalError:
            pass
        await self.db.sql_update(create_server_pxls_users_table)
        await self.db.sql_update(create_user_keys_table)

    async def create_pxls_user(self, name):
        """create a 'pxls_user' and its associated 'pxls_name'"""
        # check if there is already a pxls_name with the given name
        sql = """SELECT * FROM pxls_name WHERE name = ? """
        db_pxls_name = await self.db.sql_select(sql, name)
        if len(db_pxls_name) != 0:
            raise ValueError("There is already a pxls_name with the name {}".format(name))

        # create the pxls_user
        sql = """INSERT INTO pxls_user (pxls_user_id) VALUES (NULL)"""
        pxls_user_id = await self.db.sql_insert(sql)

        # create the pxls_name
        sql = """INSERT INTO pxls_name(pxls_user_id,name)
                VALUES(?,?)"""
        await self.db.sql_insert(sql, (pxls_user_id, name))

    async def get_pxls_user_id(self, name):
        sql = """ SELECT pxls_user_id FROM pxls_name WHERE name = ?"""

        res = await self.db.sql_select(sql, name)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_pxls_user_name(self, pxls_id):
        sql = """ SELECT name FROM pxls_name WHERE pxls_user_id = ?"""
        res = await self.db.sql_select(sql, pxls_id)
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_discord_user(self, discord_id):
        """Get the informations of a discord user and create it if it doesn't exist in the DB"""
        await self.db.sql_insert(
            "INSERT OR IGNORE INTO discord_user(discord_id) VALUES(?)", discord_id
        )
        discord_user = await self.db.sql_select(
            "SELECT * FROM discord_user WHERE discord_id = ?", discord_id
        )
        return discord_user[0]

    async def set_user_blacklist(self, discord_id, blacklist_status: bool):
        """Update the 'is_blacklisted' attribute of a discord_user"""
        sql = "UPDATE discord_user SET is_blacklisted = ? WHERE discord_id = ? "
        await self.db.sql_update(sql, (int(blacklist_status), discord_id))

    async def set_pxls_user(self, discord_id, pxls_user_id):
        """Update the pxls_user_id of a discord_user"""
        sql = "UPDATE discord_user SET pxls_user_id = ? WHERE discord_id = ? "
        await self.db.sql_update(sql, (pxls_user_id, discord_id))

    async def set_user_theme(self, discord_id, theme):
        """Update the theme of a discord_user"""
        sql = "UPDATE discord_user SET color = ? WHERE discord_id = ? "
        await self.db.sql_update(sql, (theme, discord_id))

    async def set_user_timezone(self, discord_id, timezone):
        """Update the theme of a discord_user"""
        sql = "UPDATE discord_user SET timezone = ? WHERE discord_id = ? "
        await self.db.sql_update(sql, (timezone, discord_id))

    async def set_user_font(self, discord_id, font):
        """Update the theme of a discord_user"""
        sql = "UPDATE discord_user SET font = ? WHERE discord_id = ? "
        await self.db.sql_update(sql, (font, discord_id))

    async def get_all_blacklisted_users(self):
        """Get all the discord users blacklisted. Returns a list of discord ID"""
        sql = "SELECT discord_id FROM discord_user WHERE is_blacklisted = 1"
        rows = await self.db.sql_select(sql)
        if len(rows) == 0:
            return None
        else:
            res = [row[0] for row in rows]
            return res

    # functions useful for the milestones command #
    async def create_server_pxls_user(self, server_id, name):
        """Create a 'server_pxls_user'"""
        # get the pxls_user_id
        pxls_user_id = await self.get_pxls_user_id(name)
        if pxls_user_id is None:
            raise ValueError("User not found.")

        # insert the server_pxls_user
        sql = """INSERT INTO server_pxls_user(server_id, pxls_user_id)
                VALUES(?,?)"""
        await self.db.sql_insert(sql, (server_id, pxls_user_id))

    async def delete_server_pxls_user(self, server_id, name):
        # get the pxls_user id
        pxls_user_id = await self.get_pxls_user_id(name)
        if pxls_user_id is None:
            raise ValueError("User not found.")

        # remove the user from the server_pixel_users table
        sql = "DELETE from server_pxls_user WHERE server_id = ? AND pxls_user_id = ?"
        total_changes = await self.db.sql_update(sql, (server_id, pxls_user_id))
        # check if the user has been deleted
        if total_changes == 0:
            # no changes have been made
            raise ValueError("This user isn't tracked.")

    async def get_all_tracked_users(self):
        """Get all the pxls users (ID) tracked in a server and the list of those servers

        Return a dictionary:
        - key: pxls_user_id
        - value: list of server_id"""
        sql = """
            SELECT server_id, name, pxls_user.pxls_user_id
            FROM pxls_user
            INNER JOIN pxls_name
            ON pxls_user.pxls_user_id = pxls_name.pxls_user_id
            INNER JOIN server_pxls_user
            ON server_pxls_user.pxls_user_id = pxls_user.pxls_user_id
            """
        rows = await self.db.sql_select(sql)
        res = {}
        for row in rows:
            try:
                res[row["pxls_user_id"]].append(row["server_id"])
            except Exception:
                res[row["pxls_user_id"]] = [row["server_id"]]
        return res

    async def get_all_server_tracked_users(self, server_id: str):
        """get a list of all the users (name) tracked in a given server"""
        sql = """
            SELECT name, alltime_count
            FROM server_pxls_user
            INNER JOIN pxls_name ON pxls_name.pxls_user_id = server_pxls_user.pxls_user_id
            INNER JOIN pxls_user_stat ON pxls_user_stat.pxls_name_id = pxls_name.pxls_name_id
            WHERE server_id = ?
            AND record_id = (SELECT MAX(record_id) FROM record)
        """
        rows = await self.db.sql_select(sql, server_id)
        return rows

    async def create_log_key(self, discord_id, canvas_code, log_key):
        sql = """
            INSERT INTO log_key(discord_id, canvas_code, key)
            VALUES(?, ?, ?)
        """
        return await self.db.sql_update(sql, (discord_id, canvas_code, log_key))

    async def get_key(self, discord_id, canvas_code):
        sql = "SELECT key FROM log_key WHERE discord_id = ? AND canvas_code = ?"
        res = await self.db.sql_select(sql, (discord_id, canvas_code))
        if res:
            return res[0][0]
        else:
            return None

    async def delete_key(self, discord_id, canvas_code):
        sql = "DELETE FROM log_key WHERE discord_id = ? AND canvas_code = ?"
        return await self.db.sql_update(sql, (discord_id, canvas_code))

    async def update_key(self, discord_id, canvas_code, new_key):
        sql = "UPDATE log_key SET key = ? WHERE discord_id = ? AND canvas_code = ?"
        return await self.db.sql_update(sql, (new_key, discord_id, canvas_code))
