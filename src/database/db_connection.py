import asqlite
import os

DB_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "database.db")

class DbConnection():
    def __init__(self) -> None:
        self.db_file:str = DB_FILE
        self.conn = None

    async def create_connection(self):
        self.conn = await asqlite.connect(DB_FILE,detect_types=asqlite.PARSE_DECLTYPES)

    async def sql_select(self,query,param:tuple=None):
        async with self.conn.cursor() as cursor:
            if param:
                await cursor.execute(query,param)
            else:
                await cursor.execute(query)
            res = await cursor.fetchall()
        return res

    async def sql_update(self,query,param:tuple=None):
        async with self.conn.cursor() as cursor:
            if param:
                await cursor.execute(query,param)
            else:
                await cursor.execute(query)
            await self.conn.commit()
            return cursor.get_cursor().rowcount
