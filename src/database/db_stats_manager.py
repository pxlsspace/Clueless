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

        create_palette_color_table = """
            CREATE TABLE IF NOT EXISTS palette_color(
                canvas_code TEXT,
                color_id INTEGER,
                color_name TEXT,
                color_hex TEXT,
                PRIMARY KEY(canvas_code,color_id)
            );"""

        create_color_stat_table = """
            CREATE TABLE IF NOT EXISTS color_stat(
                record_id INTEGER,
                color_id INTEGER,
                amount INTEGER,
                amount_placed INTEGER,
                FOREIGN KEY (record_id) REFERENCES record(record_id),
                PRIMARY KEY (record_id,color_id)
            );"""

        await self.db.sql_update(create_pxls_general_stats_table)
        await self.db.sql_update(create_record_table)
        await self.db.sql_update(create_pxls_user_stat_table)
        await self.db.sql_update(create_palette_color_table)
        await self.db.sql_update(create_color_stat_table)

    ### pxls user stats functions ###
    async def create_record(self,last_updated,canvas_code):
        ''' Create a record at the time and canvas given, return None if the
        record already exists'''
        sql = ''' INSERT INTO record (datetime, canvas_code) VALUES (?,?)'''
        try:
            # create a time record
            record_id = await self.db.sql_insert(sql,(last_updated,canvas_code))
            return record_id
        except IntegrityError:
            # there is already a record for this time
            return None

    async def update_all_pxls_stats(self,alltime_stats,canvas_stats,record_id):
        ''' Insert all the pxls stats data in the database'''

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

    async def get_stats_history(self,user_list,date1,date2,canvas_opt):
        """ get the stats between 2 dates """
        if canvas_opt:
            canvas_to_select = await self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(date1,canvas_to_select)
        record2 = await self.find_record(date2,canvas_to_select)
        sql = """
            SELECT name, {0} as pixels, datetime
            FROM pxls_user_stat
            JOIN record ON record.record_id = pxls_user_stat.record_id
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name IN ({1})
            AND datetime BETWEEN ? AND ? 
            ORDER BY {0} """.format(
                "canvas_count" if canvas_opt else "alltime_count",
                ', '.join('?' for u in user_list))

        rows = await self.db.sql_select(sql,tuple(user_list) +\
            (record1["datetime"],record2["datetime"]))

        # group by user
        users_dict = {}
        for row in rows:
            try:
                users_dict[row["name"]].append(row)
            except KeyError:
                users_dict[row["name"]] = [row]

        users_list = list(users_dict.items())
        return (record1["datetime"], record2["datetime"], users_list)

    async def get_grouped_stats_history(self,user_list,dt1,dt2,groupby_opt,canvas_opt):
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
            canvas_to_select = await self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(dt1,canvas_to_select)
        record2 = await self.find_record(dt2,canvas_to_select)

        sql = """
            SELECT 
                name,
                {0} as pixels,
                {0}-(LAG({0}) OVER (ORDER BY name, datetime)) as placed,
                MIN(record.datetime) as first_datetime,
                MAX(record.datetime) as last_datetime
            FROM pxls_user_stat
            JOIN record ON record.record_id = pxls_user_stat.record_id
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name IN ({1}) 
                AND pxls_user_stat.record_id BETWEEN ? AND ?
            GROUP BY strftime(?,datetime), name""".format(
                "canvas_count" if canvas_opt else "alltime_count",
                ', '.join('?' for u in user_list))

        rows = await self.db.sql_select(sql,tuple(user_list) +
            (record1["record_id"],record2["record_id"],groupby))

        # group by user
        users_dict = {}
        for row in rows:
            try:
                users_dict[row["name"]].append(row)
            except KeyError:
                users_dict[row["name"]] = [row]
        res_list = list(users_dict.items())

        # find the min and max in all the dates of each user
        all_datas = [user[1][1:] for user in res_list]
        all_datas = [row for data in all_datas for row in data ]
        past_time = min([datetime.strptime(d["first_datetime"],"%Y-%m-%d %H:%M:%S") for d in all_datas])
        now_time = max([datetime.strptime(d["last_datetime"],"%Y-%m-%d %H:%M:%S") for d in all_datas])

        return past_time, now_time, res_list

    async def get_pixels_placed_between(self,dt1,dt2,canvas,orderby_opt):

            order_dict ={
                "speed": "b.{0}_count - a.{0}_count".format("canvas" if canvas else "alltime"),
                "canvas": "last.canvas_count",
                "alltime": "last.alltime_count"
            }
            assert orderby_opt in order_dict.keys(),"orderby paramater must be: 'placed', 'canvas' or 'alltime'"
            orderby = order_dict[orderby_opt]

            
            if canvas:
                canvas_to_select = await self.stats_manager.get_canvas_code()
            else:
                canvas_to_select = None

            last_record = await self.find_record(datetime.utcnow(),canvas_to_select)
            record1 = await self.find_record(dt1,canvas_to_select)
            record2 = await self.find_record(dt2,canvas_to_select)

            sql = """
            SELECT
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
    async def get_general_stat(self,name,dt1,dt2):
        ''' get all the values of a general stat after a datetime 
        (this is used to plot the stat) '''

        sql = """
            SELECT datetime, min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM pxls_general_stat
            """
        closest_data1 = await self.db.sql_select(sql,dt1)
        closest_dt1 = closest_data1[0][0]
        closest_data2 = await self.db.sql_select(sql,dt2)
        closest_dt2 = closest_data2[0][0]

        sql = """
            SELECT value,datetime from pxls_general_stat
            WHERE stat_name = ?
            AND datetime >= ?
            AND datetime <= ?
            ORDER BY datetime DESC"""

        return await self.db.sql_select(sql,(name,closest_dt1,closest_dt2))

    async def add_general_stat(self,name,value,canvas,date):
        sql = ''' INSERT INTO pxls_general_stat(stat_name, value ,canvas_code, datetime)
                VALUES(?,?,?,?) '''
        await self.db.sql_update(sql,(name,value,canvas,date))

    async def save_palette(self,palette_list,canvas_code):
        """ Save the palette with the given canvas code,
        do nothing if there is already a palette for the canvas code."""

        sql = """ 
            INSERT INTO palette_color (canvas_code,color_id,color_name,
                color_hex) VALUES (?,?,?,?) """

        for i,color in enumerate(palette_list):
            color_id = i
            color_name = color["name"]
            color_hex = color["value"]
            values = (canvas_code,color_id,color_name,color_hex)
            try:
                await self.db.sql_insert(sql,values)
            except IntegrityError:
                # a color with this id is already saved for this canvas
                pass

    async def save_color_stats(self,colors_dict:dict,record_id:int):
        """ Save the color stats """

        # get the values to insert
        values_list = []
        for color_id in colors_dict.keys():
            amount = colors_dict[color_id]["amount"]
            amount_placed = colors_dict[color_id]["amount_placed"]

            values = (record_id,color_id,amount,amount_placed)
            values_list.append(values)

        sql = """ 
        INSERT INTO color_stat (record_id, color_id, amount, amount_placed)
        VALUES (?,?,?,?)"""
        # create a db connection and insert all the values in the db
        await self.db.create_connection()
        async with self.db.conn.cursor() as cur:
            await cur.execute('BEGIN TRANSACTION;')
            await cur.executemany(sql,values_list)
            await cur.execute('COMMIT;')
        await self.db.conn.commit()
        await self.db.close_connection()

    async def get_canvas_color_stats(self,canvas_code,dt1=None,dt2=None):
        """ Get all the color stats as a list of sqlite3 rows 
        
        Get the data between dt1 and dt2 if they're not null or for the whole 
        canvas"""

        if dt1 and dt2:
            record1 = await self.find_record(dt1,canvas_code)
            datetime1 = record1["datetime"]
            record2 = await self.find_record(dt2,canvas_code)
            datetime2 = record2["datetime"]
        else:
            datetime1 = datetime(1900,1,1)
            datetime2 = datetime.utcnow()

        sql = """
            SELECT color_id, amount, amount_placed, datetime
            FROM color_stat
            JOIN record ON record.record_id = color_stat.record_id
            WHERE canvas_code = ?
            AND datetime BETWEEN ? AND ?
            ORDER BY record.datetime
        """

        rows = await self.db.sql_select(sql,(canvas_code,datetime1,datetime2))
        return rows

    async def get_palette(self,canvas_code):
        sql = """ SELECT color_id,color_name,color_hex 
            FROM palette_color WHERE canvas_code = ? """

        palette_colors = await self.db.sql_select(sql,canvas_code)

        return palette_colors
