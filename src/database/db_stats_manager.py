from sqlite3 import IntegrityError
from datetime import datetime, timedelta

from database.db_connection import DbConnection
from utils.pxls.pxls_stats_manager import PxlsStatsManager


class DbStatsManager:
    """A class to manage the pxls stats in the database"""

    def __init__(self, db_conn: DbConnection, stats: PxlsStatsManager) -> None:
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

    # pxls user stats functions #
    async def create_record(self, last_updated, canvas_code):
        """Create a record at the time and canvas given, return None if the
        record already exists"""
        sql = """ INSERT INTO record (datetime, canvas_code) VALUES (?,?)"""
        try:
            # create a time record
            record_id = await self.db.sql_insert(sql, (last_updated, canvas_code))
            return record_id
        except IntegrityError:
            # there is already a record for this time
            return None

    async def update_all_pxls_stats(self, alltime_stats, canvas_stats, record_id):
        """Insert all the pxls stats data in the database"""

        await self.db.create_connection()
        async with self.db.conn.cursor() as cur:
            # make a dictionary of key: username, value: {alltime: ..., canvas: ...}
            users = {}
            for user in alltime_stats:
                username = user["username"]
                alltime_count = user["pixels"]
                users[username] = {"alltime": alltime_count, "canvas": 0}

            for user in canvas_stats:
                username = user["username"]
                canvas_count = user["pixels"]
                try:
                    users[username]["canvas"] = canvas_count
                except KeyError:
                    users[username] = {"alltime": None, "canvas": canvas_count}

            # get all the pxls_name_id in a dictionary (pxls_name:pxls_name_id)
            pxls_names = await self.db.sql_select(
                "SELECT pxls_name_id, name FROM pxls_name"
            )
            names_dict = {}
            for name in pxls_names:
                names_dict[name["name"]] = name["pxls_name_id"]

            # get the values to insert for each user
            values_list = []
            for username in users.keys():
                alltime_count = users[username]["alltime"]
                canvas_count = users[username]["canvas"]
                try:
                    # get user id
                    pxls_name_id = names_dict[username]
                except KeyError:
                    # if user does not exist, create it
                    pxls_name_id = await self.create_pxls_user(username, cur)
                    names_dict[username] = pxls_name_id

                values = (record_id, pxls_name_id, alltime_count, canvas_count)
                values_list.append(values)

            sql = """
                INSERT INTO pxls_user_stat (record_id, pxls_name_id, alltime_count, canvas_count)
                VALUES (?,?,?,?)"""
            await cur.execute("BEGIN TRANSACTION;")
            await cur.executemany(sql, values_list)
            await cur.execute("COMMIT;")

        await self.db.conn.commit()
        await self.db.close_connection()

    async def create_pxls_user(self, username, cur):
        """create a 'pxls_user' and its associated 'pxls_name'"""
        sql = """ INSERT INTO pxls_user (pxls_user_id) VALUES (NULL)"""
        await cur.execute(sql)
        pxls_user_id = cur.get_cursor().lastrowid

        # create the pxls_name
        sql = """INSERT INTO pxls_name(pxls_user_id,name) VALUES(?,?)"""
        await cur.execute(sql, (pxls_user_id, username))
        return cur.get_cursor().lastrowid

    async def get_pxls_name_id(self, username, cursor):
        sql = """SELECT pxls_name_id FROM pxls_name WHERE name = ?"""
        await cursor.execute(sql, (username,))
        res = await cursor.fetchall()
        if len(res) == 0:
            return None
        else:
            return res[0][0]

    async def get_last_two_alltime_counts(self, pxls_user_id: int) -> tuple:
        """Get a tuple of the last 2 alltime pixel counts in the database for
        a given user (used to check if the user hit a milestone)"""
        sql = """
        SELECT name, alltime_count FROM pxls_name
        INNER JOIN(pxls_user_stat) ON pxls_user_stat.pxls_name_id = pxls_name.pxls_name_id
        WHERE pxls_user_id = ?
        ORDER BY record_id DESC
        LIMIT 2"""

        res = await self.db.sql_select(sql, pxls_user_id)
        if len(res) == 0:
            raise ValueError(f"No use found with ID: '{pxls_user_id}'")
        else:
            return (res[0][0], res[0][1], res[1][1])

    async def get_last_leaderboard(self):
        sql = """
        SELECT
            name,
            ROW_NUMBER() OVER(ORDER BY (alltime_count) DESC) AS alltime_rank,
            alltime_count,
            ROW_NUMBER() OVER(ORDER BY (canvas_count) DESC) AS canvas_rank,
            canvas_count,
            datetime
        FROM pxls_user_stat p
        JOIN record r ON r.record_id = p.record_id
        JOIN pxls_name n ON n.pxls_name_id = p.pxls_name_id
        WHERE r.datetime = (SELECT MAX(datetime) FROM record)"""

        rows = await self.db.sql_select(sql)
        return rows

    async def get_stats_history(self, user_list, date1, date2, canvas_opt):
        """get the stats between 2 dates"""
        if canvas_opt:
            canvas_to_select = await self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(date1, canvas_to_select)
        record2 = await self.find_record(date2, canvas_to_select)
        sql = """
            SELECT name, {0} as pixels, datetime
            FROM pxls_user_stat
            JOIN record ON record.record_id = pxls_user_stat.record_id
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name IN ({1})
            AND datetime BETWEEN ? AND ?
            ORDER BY {0} """.format(
            "canvas_count" if canvas_opt else "alltime_count",
            ", ".join("?" for u in user_list),
        )

        rows = await self.db.sql_select(
            sql, tuple(user_list) + (record1["datetime"], record2["datetime"])
        )

        # group by user
        users_dict = {}
        for row in rows:
            try:
                users_dict[row["name"]].append(row)
            except KeyError:
                users_dict[row["name"]] = [row]

        users_list = list(users_dict.items())
        return (record1["datetime"], record2["datetime"], users_list)

    async def get_grouped_stats_history(
        self, user_list, dt1, dt2, groupby_opt, canvas_opt
    ):
        """get the stats between 2 dates grouped by day or hour"""

        # check on the groupby param
        if groupby_opt == "month":
            groupby = "%Y-%m"
        elif groupby_opt == "week":
            groupby = "%Y-%W"
        elif groupby_opt == "day":
            groupby = "%Y-%m-%d"
        elif groupby_opt == "hour":
            groupby = "%Y-%m-%d %H"
        else:
            return None

        # find the records closest to the dates
        if canvas_opt:
            canvas_to_select = await self.stats_manager.get_canvas_code()
        else:
            canvas_to_select = None
        record1 = await self.find_record(dt1, canvas_to_select)
        record2 = await self.find_record(dt2, canvas_to_select)

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
            ", ".join("?" for u in user_list),
        )

        rows = await self.db.sql_select(
            sql,
            tuple(user_list) + (record1["record_id"], record2["record_id"], groupby),
        )

        # group by user
        users_dict = {}
        for row in rows:
            try:
                users_dict[row["name"]].append(row)
            except KeyError:
                users_dict[row["name"]] = [row]
        res_list = list(users_dict.items())

        if len(res_list) == 0:
            return None, None, res_list
        elif len(res_list[0][1]) == 1:
            return None, None, res_list
        else:
            # find the min and max in all the dates of each user
            all_datas = [user[1][1:] for user in res_list]
            all_datas = [row for data in all_datas for row in data]
            past_time = min(
                [
                    datetime.strptime(d["first_datetime"], "%Y-%m-%d %H:%M:%S")
                    for d in all_datas
                ]
            )
            now_time = max(
                [
                    datetime.strptime(d["last_datetime"], "%Y-%m-%d %H:%M:%S")
                    for d in all_datas
                ]
            )
            return past_time, now_time, res_list

    async def get_leaderboard_between(self, dt1, dt2, canvas, orderby_opt):
        """ Get the leaderboard between 2 dates
        ### Parameters
        - :param dt1: the lower date
        - :param dt2: the most recent date
        - :param canvas: boolean to indicate if we want canvas stats or alltime
        - :param orderby_opt: indicate how to order the leaderboard (either \
            `canvas`, `alltime` or `speed`)

        ### Returns
        Return a tuple (last_date, datetime1, datetime2, leaderboard)
        - canvas_opt: True if we had to compare canvas count to get the speed
        - last_date: the latest date in the data (used to know the last updated time)
        - date1: the closest date found to :param dt1:
        - date2: the closest date found to :param dt2:
        - leaderboard: a list of rows with the leaderboard, each row has:
            - rank: the rank depending on how we ordered the leaderboard
            - name: the pxls username
            - alltime_count or canvas_count: the last count (depends on :param canvas:)
            - placed: the amount placed in the time frame"""
        current_canvas_code = await self.stats_manager.get_canvas_code()
        if canvas:
            canvas_to_select = current_canvas_code
        else:
            canvas_to_select = None

        last_record = await self.find_record(datetime.utcnow(), canvas_to_select)
        record1 = await self.find_record(dt1, canvas_to_select)
        record2 = await self.find_record(dt2, canvas_to_select)

        # if the record1 is on the current canvas and we're checking the speed,
        # we *have* to compare canvas counts
        if orderby_opt == "speed" and record1["canvas_code"] == current_canvas_code:
            canvas = True

        order_dict = {
            "speed": "b.{0}_count - a.{0}_count".format(
                "canvas" if canvas else "alltime"
            ),
            "canvas": "last.canvas_count",
            "alltime": "last.alltime_count",
        }
        assert (
            orderby_opt in order_dict.keys()
        ), "orderby paramater must be: 'placed', 'canvas' or 'alltime'"
        orderby = order_dict[orderby_opt]

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
            orderby, "canvas" if canvas else "alltime"
        )

        return (
            canvas,
            last_record["datetime"],
            record1["datetime"],
            record2["datetime"],
            await self.db.sql_select(
                sql,
                (last_record["record_id"], record1["record_id"], record2["record_id"]),
            ),
        )

    async def get_pixels_at(
        self, datetime: datetime, user_name: str, canvas: bool = False
    ):
        """get the record of a specific user at a given time"""

        current_canvas_code = await self.stats_manager.get_canvas_code()
        if canvas:
            canvas_to_select = current_canvas_code
        else:
            canvas_to_select = None

        record = await self.find_record(datetime, canvas_to_select)
        record_id = record["record_id"]
        sql = """
            SELECT canvas_count, alltime_count, record_id
            FROM pxls_user_stat
            JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE name = ?
            AND record_id = ?"""
        rows = await self.db.sql_select(sql, (user_name, record_id))

        if len(rows) == 0:
            return (None, None)
        else:
            return (record["datetime"], rows[0])

    async def find_record(self, dt, canvas_code=None):
        """find the record with  the closest date to the given date in the database
        :param dt: the datetime to find
        :param canvas_code: the canvas to find the record in, if None, will search among all the canvases"""
        if canvas_code is None:
            canvas_code = "NOT NULL"  # to get all the canvas codes
        else:
            canvas_code = f"'{str(canvas_code)}'"

        sql = """
            SELECT
                record_id,
                datetime,
                canvas_code,
                min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM record
            WHERE canvas_code IS {}
            """.format(
            canvas_code
        )
        res = await self.db.sql_select(sql, (dt))
        return res[0]

        # general stats functions #

    async def get_general_stat(self, name, dt1, dt2, canvas=False):
        """get all the values of a general stat after a datetime
        (this is used to plot the stat)"""

        if not canvas:
            canvas_code = "NOT NULL"
        else:
            current_canvas = await self.stats_manager.get_canvas_code()
            canvas_code = f"'{str(current_canvas)}'"

        sql = f"""
            SELECT datetime, min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM pxls_general_stat
            WHERE canvas_code IS {canvas_code}
            """

        closest_data1 = await self.db.sql_select(sql, dt1)
        closest_dt1 = closest_data1[0][0]
        closest_data2 = await self.db.sql_select(sql, dt2)
        closest_dt2 = closest_data2[0][0]

        sql = """
            SELECT value,datetime from pxls_general_stat
            WHERE stat_name = ?
            AND datetime >= ?
            AND datetime <= ?
            ORDER BY datetime DESC"""

        return await self.db.sql_select(sql, (name, closest_dt1, closest_dt2))

    async def add_general_stat(self, name, value, canvas, date):
        sql = """ INSERT INTO pxls_general_stat(stat_name, value ,canvas_code, datetime)
                VALUES(?,?,?,?) """
        await self.db.sql_update(sql, (name, value, canvas, date))

    async def save_palette(self, palette_list, canvas_code):
        """Save the palette with the given canvas code,
        do nothing if there is already a palette for the canvas code."""

        sql = """
            INSERT INTO palette_color (canvas_code,color_id,color_name,
                color_hex) VALUES (?,?,?,?) """

        for i, color in enumerate(palette_list):
            color_id = i
            color_name = color["name"]
            color_hex = color["value"]
            values = (canvas_code, color_id, color_name, color_hex)
            try:
                await self.db.sql_insert(sql, values)
            except IntegrityError:
                # a color with this id is already saved for this canvas
                pass

    async def save_color_stats(self, colors_dict: dict, record_id: int):
        """Save the color stats"""

        # get the values to insert
        values_list = []
        for color_id in colors_dict.keys():
            amount = colors_dict[color_id]["amount"]
            amount_placed = colors_dict[color_id]["amount_placed"]

            values = (record_id, color_id, amount, amount_placed)
            values_list.append(values)

        sql = """
        INSERT INTO color_stat (record_id, color_id, amount, amount_placed)
        VALUES (?,?,?,?)"""
        # create a db connection and insert all the values in the db
        await self.db.create_connection()
        async with self.db.conn.cursor() as cur:
            await cur.execute("BEGIN TRANSACTION;")
            await cur.executemany(sql, values_list)
            await cur.execute("COMMIT;")
        await self.db.conn.commit()
        await self.db.close_connection()

    async def get_canvas_color_stats(self, canvas_code, dt1=None, dt2=None):
        """Get all the color stats as a list of sqlite3 rows

        Get the data between dt1 and dt2 if they're not null or for the whole
        canvas"""

        if dt1 and dt2:
            record1 = await self.find_record(dt1, canvas_code)
            datetime1 = record1["datetime"]
            record2 = await self.find_record(dt2, canvas_code)
            datetime2 = record2["datetime"]
        else:
            datetime1 = datetime(1900, 1, 1)
            datetime2 = datetime.utcnow()

        sql = """
            SELECT color_id, amount, amount_placed, datetime
            FROM color_stat
            JOIN record ON record.record_id = color_stat.record_id
            WHERE canvas_code = ?
            AND datetime BETWEEN ? AND ?
            ORDER BY record.datetime
        """

        rows = await self.db.sql_select(sql, (canvas_code, datetime1, datetime2))
        return rows

    async def get_palette(self, canvas_code):
        sql = """ SELECT color_id,color_name,color_hex
            FROM palette_color WHERE canvas_code = ? """

        palette_colors = await self.db.sql_select(sql, canvas_code)

        return palette_colors

    async def get_session_start_time(self, user_id, canvas: bool):
        """Find the last time frame where the user didn't place"""
        sql = """
            SELECT *
            FROM (
                SELECT
                    datetime,
                    canvas_code,
                    record.record_id,
                    {0}-(LAG({0}) OVER (ORDER BY datetime)) as placed
                FROM pxls_user_stat
                JOIN record on record.record_id = pxls_user_stat.record_id
                JOIN pxls_name on pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
                WHERE pxls_user_id = ?
                AND datetime > ?
                ORDER BY datetime desc
            ) p
            WHERE p.placed = 0
            LIMIT 1""".format(
            "canvas_count" if canvas else "alltime_count"
        )

        # only search in the last 7 days to make the query faster
        td = datetime.utcnow() - timedelta(days=7)
        res = await self.db.sql_select(sql, (user_id, td))

        if len(res) == 0:
            return None
        else:
            return res[0]

    async def get_last_online(self, user_id, canvas: bool, last_count):
        sql = """
            SELECT datetime, canvas_code, pxls_user_stat.record_id
            FROM pxls_user_stat
            JOIN record on record.record_id = pxls_user_stat.record_id
            JOIN pxls_name on pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
            WHERE pxls_user_id = ?
            AND {} = ?
            ORDER BY datetime
            LIMIT 1""".format(
            "canvas_count" if canvas else "alltime_count"
        )

        res = await self.db.sql_select(sql, (user_id, last_count))

        if len(res) == 0:
            return None
        else:
            return res[0]

    async def get_stats_per_canvas(self, user_list):
        sql_last_canvas_records = """
            SELECT
                record_id,
                min(datetime) as canvas_start,
                max(datetime) as canvas_end,
                canvas_code
            FROM record
            GROUP BY canvas_code """
        last_canvas_records = await self.db.sql_select(sql_last_canvas_records)

        res = []
        for user in user_list:
            user_data = []
            for canvas in last_canvas_records:
                record_id = canvas["record_id"]
                canvas_code = canvas["canvas_code"]
                sql = """
                    SELECT name, alltime_count as pixels, canvas_count as placed, canvas_code
                    FROM pxls_user_stat
                        JOIN pxls_name on pxls_user_stat.pxls_name_id = pxls_name.pxls_name_id
                        JOIN record r on r.record_id = pxls_user_stat.record_id
                    WHERE r.record_id = ?
                        AND name = ? """
                rows = await self.db.sql_select(sql, (record_id, user))
                if rows:
                    user_data.append(rows[0])
                else:
                    user_data.append(
                        {
                            "name": user,
                            "pixels": None,
                            "placed": None,
                            "canvas_code": canvas_code,
                        }
                    )
            res.append([user, user_data])

        past_time = datetime.strptime(
            last_canvas_records[0]["canvas_start"], "%Y-%m-%d %H:%M:%S"
        )
        now_time = datetime.strptime(
            last_canvas_records[-1]["canvas_end"], "%Y-%m-%d %H:%M:%S"
        )
        return (past_time, now_time, res)

    async def get_all_pxls_names(self):
        sql = "SELECT name from pxls_name ORDER BY pxls_name_id"
        rows = await self.db.sql_select(sql)
        if rows:
            return [r["name"] for r in rows]
        else:
            return None
