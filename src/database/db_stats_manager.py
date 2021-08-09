from sqlite3 import IntegrityError
from datetime import datetime

from database.db_connection import DbConnection
from utils.pxls_stats_manager import PxlsStatsManager

class DbStatsManager():
    ''' A class to manage the pxls stats in the database '''

    def __init__(self,db_conn:DbConnection,stats:PxlsStatsManager) -> None:
        self.db = db_conn
        self.stats_manager = stats

    async def create_tables(self):
        create_pxls_general_stats_table = """ 
            CREATE TABLE IF NOT EXISTS pxls_general_stat(
                stat_name TEXT,
                value TEXT,
                canvas_code TEXT,
                datetime TIMESTAMP,
                PRIMARY KEY (stat_name, datetime)
            );"""
        create_record_table = """
            CREATE TABLE IF NOT EXISTS record(
                record_id INTEGER PRIMARY KEY,
                datetime TIMESTAMP UNIQUE,
                canvas_code TEXT
            );"""
        create_pxls_user_stat_table = """
            CREATE TABLE IF NOT EXISTS pxls_user_stat(
                record_id INTEGER,
                pxls_name_id INTEGER,
                alltime_count INTEGER,
                canvas_count INTEGER,
                PRIMARY KEY (record_id, pxls_name_id),
                FOREIGN KEY(record_id) REFERENCES record(record_id),
                FOREIGN KEY(pxls_name_id) REFERENCES pxls_name(pxls_name_id)
            );"""
        await self.db.sql_update(create_pxls_general_stats_table)
        await self.db.sql_update(create_record_table)
        await self.db.sql_update(create_pxls_user_stat_table)

    ### pxls user stats functions ###
    async def update_all_pxls_stats(self,alltime_stats,canvas_stats,last_updated,canvas_code):
        ''' Create a new time record and insert all the pxls stats data in the database'''
        # create a time record
        sql = ''' INSERT INTO record (datetime, canvas_code) VALUES (?,?)'''
        try:
            record_id = await self.db.sql_insert(sql,(last_updated,canvas_code))
        except IntegrityError:
            # there is already a record for this time
            return

        await self.db.create_connection()
        async with self.db.conn.cursor() as cur:
            # make a dictionary of key: username, value: {alltime: ..., canvas: ...}
            users = {}
            for user in alltime_stats:
                username = user["username"]
                alltime_count = user["pixels"]
                users[username] = {"alltime":alltime_count,"canvas":0}

            for user in canvas_stats:
                username = user["username"]
                canvas_count = user["pixels"]
                try:
                    users[username]["canvas"] = canvas_count
                except KeyError:
                    users[username] = {"alltime":None,"canvas":canvas_count}

            # get all the pxls_name_id in a dictionary (pxls_name:pxls_name_id)
            pxls_names = await self.db.sql_select("SELECT pxls_name_id, name FROM pxls_name")
            names_dict = {}
            for name in pxls_names:
                names_dict[name["name"]] = name["pxls_name_id"]

            # get the values to insert for each user
            values_list = []
            for username in users.keys():
                alltime_count = users[username]['alltime']
                canvas_count = users[username]['canvas']
                try:
                    # get user id
                    pxls_name_id = names_dict[username]
                except KeyError:
                    # if user does not exist, create it
                    pxls_name_id = await self.create_pxls_user(username,cur)
                    names_dict[username] = pxls_name_id

                values = (record_id,pxls_name_id,alltime_count,canvas_count)
                values_list.append(values)

            sql = """ 
                    INSERT INTO pxls_user_stat (record_id, pxls_name_id, alltime_count, canvas_count)
                    VALUES (?,?,?,?)"""
            await cur.execute('BEGIN TRANSACTION;')
            await cur.executemany(sql,values_list)
            await cur.execute('COMMIT;')

        await self.db.conn.commit()
        await self.db.close_connection()

    async def create_pxls_user(self, username,cur):
        ''' create a 'pxls_user' and its associated 'pxls_name' '''
        sql = ''' INSERT INTO pxls_user (pxls_user_id) VALUES (NULL)'''
        await cur.execute(sql)
        pxls_user_id = cur.get_cursor().lastrowid

        # create the pxls_name
        sql = ''' INSERT INTO pxls_name(pxls_user_id,name) VALUES(?,?) '''
        await cur.execute(sql, (pxls_user_id,username))
        return cur.get_cursor().lastrowid


    async def get_pxls_name_id(self,username,cursor):
        sql = """ SELECT pxls_name_id FROM pxls_name WHERE name = ?"""
        await cursor.execute(sql,(username,))
        res = await cursor.fetchall()
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_last_alltime_counts(self,pxls_user_id:int) -> tuple:
        ''' get a tuple of the last 2 alltime pixel counts in the database for a given user 
            (useful for the milestones command) '''
        sql = """
        SELECT name, alltime_count FROM pxls_name
        INNER JOIN(pxls_user_stat) ON pxls_user_stat.pxls_name_id = pxls_name.pxls_name_id
        WHERE pxls_user_id = ?
        LIMIT 2"""

        res = await self.db.sql_select(sql,pxls_user_id)
        if len(res) == 0:
            raise ValueError(f"No use found with ID: '{pxls_user_id}'")
        else:
            return (res[0][0],res[0][1],res[1][1])

    async def get_stats_history(self,user,date1,date2,canvas_opt):
        """ get the stats between 2 dates """
        if canvas_opt:
            canvas_to_select = self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(date1,canvas_to_select)
        record2 = await self.find_record(date2,canvas_to_select)

        sql = """
            SELECT alltime_count, canvas_count, datetime
            FROM pxls_user_stat
            JOIN record ON record.record_id = pxls_user_stat.record_id
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name = ?
            AND datetime >= ?
            AND datetime <= ?"""
        return await self.db.sql_select(sql,(user,record1["datetime"],record2["datetime"]))

    async def get_grouped_stats_history(self,user,dt1,dt2,groupby_opt,canvas_opt):
        """ get the stats between 2 dates grouped by day or hour """

        # check on the groupby param
        if groupby_opt == "day":
            groupby = '%Y-%m-%d'
        elif groupby_opt == "hour":
            groupby = '%Y-%m-%d %H'
        else:
            return None

        # find the records closest to the dates
        if canvas_opt:
            canvas_to_select = self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(dt1,canvas_to_select)
        record2 = await self.find_record(dt2,canvas_to_select)

        sql = """
            SELECT name, {0}-(LAG({0}) OVER (ORDER BY datetime)) as placed,
            MAX(record.datetime) as last_datetime
            FROM pxls_user_stat
            JOIN record ON record.record_id = pxls_user_stat.record_id
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name = ?
                AND pxls_user_stat.record_id >= ?
                AND pxls_user_stat.record_id <= ?
            GROUP BY strftime(?,datetime)""".format("canvas_count" if canvas_opt else "alltime_count")

        return await self.db.sql_select(sql,(user,record1["record_id"],record2["record_id"],groupby))

    async def get_pixels_placed_between(self,dt1,dt2,canvas,orderby_opt):

            order_dict ={
                "speed": "b.{0}_count - a.{0}_count".format("canvas" if canvas else "alltime"),
                "canvas": "last.canvas_count",
                "alltime": "last.alltime_count"
            }
            assert orderby_opt in order_dict.keys(),"orderby paramater must be: 'placed', 'canvas' or 'alltime'"
            orderby = order_dict[orderby_opt]

            
            if canvas:
                canvas_to_select = self.stats_manager.get_canvas_code()
            else:
                canvas_to_select = None

            last_record = await self.find_record(datetime.utcnow(),canvas_to_select)
            record1 = await self.find_record(dt1,canvas_to_select)
            record2 = await self.find_record(dt2,canvas_to_select)

            sql = """SELECT
                    ROW_NUMBER() OVER(ORDER BY ({0}) DESC) AS rank,
                    pxls_name.name,
                    last.{1}_count,
                    b.{1}_count - a.{1}_count as placed
                FROM pxls_user_stat a, pxls_user_stat b, pxls_user_stat last
                INNER JOIN(pxls_name) ON pxls_name.pxls_name_id = a.pxls_name_id
                WHERE a.pxls_name_id = b.pxls_name_id AND a.pxls_name_id = last.pxls_name_id
                AND last.record_id = ?
                AND a.record_id =  ?
                AND b.record_id = ?
                ORDER BY {0} DESC""".format(
                    orderby,
                    "canvas" if canvas else "alltime")

            return (
                last_record["datetime"],
                record1["datetime"],
                record2["datetime"],
                await self.db.sql_select(sql,(last_record["record_id"],record1["record_id"],record2["record_id"])))

    async def find_record(self,dt,canvas_code=None):
        """ find the record with  the closest date to the given date in the database
        :param dt: the datetime to find
        :param canvas_code: the canvas to find the record in, if None, will search among all the canvases """
        if canvas_code == None:
            canvas_code = "NOT NULL" # to get all the canvas codes
        else:
            canvas_code = f"'{str(canvas_code)}'"

        sql = """
            SELECT record_id, datetime, min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM record
            WHERE canvas_code IS {}
            """.format(canvas_code)
        res = await self.db.sql_select(sql,(dt))
        return res[0]

        ### general stats functions ###
    async def get_general_stat(self,name,dt):
        ''' get all the values of a general stat after a datetime 
        (this is used to plot the stat) '''
        sql = """SELECT value,datetime from pxls_general_stat
                WHERE stat_name = ?
                AND datetime > ?
                ORDER BY datetime DESC"""

        return await self.db.sql_select(sql,(name,dt))

    async def add_general_stat(self,name,value,canvas,date):
        sql = ''' INSERT INTO pxls_general_stat(stat_name, value ,canvas_code, datetime)
                VALUES(?,?,?,?) '''
        await self.db.sql_update(sql,(name,value,canvas,date))
