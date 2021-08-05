from datetime import datetime
from database.db_connection import DbConnection

class DbStatsManager():
    ''' A class to manage the pxls stats in the database '''

    def __init__(self,db_conn:DbConnection) -> None:
        self.db = db_conn

    async def create_tables(self):
        create_pxls_user_stats_table = """ CREATE TABLE IF NOT EXISTS pxls_user_stats(
                                    name TEXT,
                                    alltime_count INTEGER,
                                    canvas_count INTEGER,
                                    date TIMESTAMP,
                                    PRIMARY KEY (name, date)
                                );"""
        create_pxls_general_stats_table = """ CREATE TABLE IF NOT EXISTS pxls_general_stats(
                                    name TEXT,
                                    value TEXT,
                                    canvas_code TEXT,
                                    datetime TIMESTAMP
                                );"""
        await self.db.sql_update(create_pxls_user_stats_table)
        await self.db.sql_update(create_pxls_general_stats_table)

    ### pxls user stats functions ###
    async def update_all_pxls_stats(self,alltime_stats,canvas_stats,last_updated):

        conn = self.db.conn

        async with conn.cursor() as cur:
            for user in alltime_stats:
                name = user["username"]
                alltime_count = user["pixels"]
                sql = """INSERT INTO pxls_user_stats(name, date, alltime_count, canvas_count) 
                        VALUES (?,?,?,?)
                        ON CONFLICT (name,date) 
                        DO UPDATE SET
                            alltime_count = ?"""
                await cur.execute(sql,(name,last_updated,alltime_count,0,alltime_count))


            for user in canvas_stats:
                name = user["username"]
                canvas_count = user["pixels"]
                sql = """INSERT INTO pxls_user_stats(name, date, canvas_count) 
                        VALUES (?,?,?)
                        ON CONFLICT (name,date) 
                        DO UPDATE SET
                            canvas_count = ?"""
                await cur.execute(sql,(name,last_updated,canvas_count,canvas_count))

            await self.db.conn.commit()

    async def get_grouped_stats_history(self,user,date1,date2,groupby_opt):
        """ get the stats between 2 dates grouped by day or hour """

        # check on the groupby param
        if groupby_opt == "day":
            groupby = '%Y-%m-%d'
        elif groupby_opt == "hour":
            groupby = '%Y-%m-%d %H'
        else:
            return None

        sql = """SELECT name, alltime_count, canvas_count,
                    alltime_count-(LAG(alltime_count) OVER (ORDER BY date)) as placed,
                    MAX(date) as last_datetime
                FROM pxls_user_stats
                WHERE name = ?
                AND DATE >= ?
                AND DATE <= ?
                GROUP BY strftime(?,date)"""

        return await self.db.sql_select(sql,(user,date1,date2,groupby))

    async def get_pixels_placed_between(self,dt1,dt2,canvas,orderby_opt):

            order_dict ={
                "speed": "b.canvas_count - a.canvas_count",
                "canvas": "last.canvas_count",
                "alltime": "last.alltime_count"
            }
            assert orderby_opt in order_dict.keys(),"orderby paramater must be: 'placed', 'canvas' or 'alltime'"
            orderby = order_dict[orderby_opt]

            last_date = await self.find_closet_date(datetime.utcnow())
            datetime1 = await self.find_closet_date(dt1)
            datetime2 = await self.find_closet_date(dt2)

            sql = """SELECT 
                    ROW_NUMBER() OVER(ORDER BY ({0}) DESC) AS rank,
                    a.name,
                    last.{1}_count,
                    b.canvas_count - a.canvas_count as placed,
                    last.date, a.date, b.date
                FROM pxls_user_stats a, pxls_user_stats b, pxls_user_stats last
                WHERE a.name = b.name AND b.name = last.name
                AND last.date = ?
                AND a.date =  ?
                AND b.date = ?
                ORDER BY {0} desc""".format(
                    orderby,
                    "canvas" if canvas else "alltime")
            return await self.db.sql_select(sql,(last_date,datetime1,datetime2))

    async def find_closet_date(self,dt):
        """ find the closest date to the given date in the database """
        sql = """SELECT date, min(abs(JulianDay(date) - JulianDay(?)))*24*3600 as diff_with_time
            FROM pxls_user_stats
            WHERE name = ?"""
        res = await self.db.sql_select(sql,(dt,"GrayTurtles"))
        return res[0][0]

        ### general stats functions ###
    async def get_general_stat(self,name,dt):
        ''' get all the values of a general stat after a datetime 
        (this is used to plot the stat) '''
        sql = """SELECT value,datetime from pxls_general_stats
                WHERE name = ?
                AND datetime > ?
                ORDER BY datetime DESC"""

        return await self.db.sql_select(sql,(name,dt))

    async def add_general_stat(self,name,value,canvas,date):
        sql = ''' INSERT INTO pxls_general_stats(name, value ,canvas_code, datetime)
                VALUES(?,?,?,?) '''
        await self.db.sql_update(sql,(name,value,canvas,date))

    async def get_stats_history(self,user,date1,date2):
        """ get the stats between 2 dates """
        sql = """SELECT * FROM pxls_user_stats
                                WHERE name = ?
                                AND date >= ?
                                AND date <= ?"""
        return await self.db.sql_select(sql,(user,date1,date2))
