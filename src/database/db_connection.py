import os

import asqlite

DB_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "database.db")


class DbConnection:
    def __init__(self) -> None:
        self.db_file: str = DB_FILE
        self.conn = None

    async def create_connection(self):
        self.conn = await asqlite.connect(DB_FILE, detect_types=asqlite.PARSE_DECLTYPES)

    async def close_connection(self):
        await self.conn.close()

    async def sql_select(self, query, param: tuple = None):
        """Execute the query with the given parameters and return all the rows selected."""
        async with asqlite.connect(DB_FILE, detect_types=asqlite.PARSE_DECLTYPES) as conn:
            async with conn.cursor() as cursor:
                if param:
                    await cursor.execute(query, param)
                else:
                    await cursor.execute(query)
                res = await cursor.fetchall()
            return res

    async def sql_update(self, query, param: tuple = None):
        """Execute the query with the given parameter, commit the connection and return the number of lines changed."""
        async with asqlite.connect(DB_FILE, detect_types=asqlite.PARSE_DECLTYPES) as conn:
            async with conn.cursor() as cursor:
                if param:
                    await cursor.execute(query, param)
                else:
                    await cursor.execute(query)
                await conn.commit()
                return cursor.get_cursor().rowcount

    async def sql_insert(self, query, param: tuple = None) -> int:
        """Same as `sql_update()` but returns the rowid of the last element inserted"""
        async with asqlite.connect(DB_FILE, detect_types=asqlite.PARSE_DECLTYPES) as conn:
            async with conn.cursor() as cursor:
                if param:
                    await cursor.execute(query, param)
                else:
                    await cursor.execute(query)
                await conn.commit()
                return cursor.get_cursor().lastrowid
