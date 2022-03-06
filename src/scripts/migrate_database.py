from alive_progress import alive_bar
import os
import sys
import asyncio
import sqlite3
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database.db_connection import DbConnection  # noqa: E402
from database.db_stats_manager import DbStatsManager  # noqa: E402
from database.db_servers_manager import DbServersManager  # noqa: E402
from database.db_user_manager import DbUserManager  # noqa: E402

""" Script used to move the old database data to the new format """

OLD_DB_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "database_old.db")
db_conn = DbConnection()
db_serv = DbServersManager(db_conn, ">")
db_user = DbUserManager(db_conn)
db_stat = DbStatsManager(db_conn)


async def create_pxls_user(username, cur: sqlite3.Cursor):
    """create a 'pxls_user' and its associated 'pxls_name'"""
    sql = """ INSERT INTO pxls_user (pxls_user_id) VALUES (NULL)"""
    await cur.execute(sql)
    pxls_user_id = cur.get_cursor().lastrowid

    # create the pxls_name
    sql = """ INSERT INTO pxls_name(pxls_user_id,name) VALUES(?,?) """
    await cur.execute(sql, (pxls_user_id, username))
    return cur.get_cursor().lastrowid


async def create_all_tables():
    await db_serv.create_tables()
    await db_user.create_tables()
    await db_stat.create_tables()


async def migrate_pxls_user_stats():

    old_conn = sqlite3.connect(OLD_DB_FILE)
    old_cur = old_conn.cursor()

    sql = """ SELECT * FROM pxls_user_stats"""
    with alive_bar(
        0, title="Fetching old db data", bar="classic", spinner="classic"
    ) as bar:
        old_cur.execute(sql)
        rows = old_cur.fetchall()
        bar()
    old_cur.close()
    old_conn.close()
    res = {}
    total_lines = len(rows)
    with alive_bar(
        total_lines, title="Groupping by date", bar="classic", spinner="classic"
    ) as bar:

        for row in rows:
            # row type: [name,alltime_count,canvas_count,datetime]
            name = row[0]
            alltime_count = row[1]
            canvas_count = row[2]
            datetime = row[3]
            try:
                res[datetime].append((name, alltime_count, canvas_count))
            except Exception:
                res[datetime] = [(name, alltime_count, canvas_count)]
            bar()

    sql = """SELECT pxls_name_id, name FROM pxls_name"""
    users = await db_conn.sql_select(sql)
    users_dict = {}
    for user in users:
        users_dict[user["name"]] = user["pxls_name_id"]

    total_lines = len(rows)
    values_list = []
    await db_conn.create_connection()
    async with db_conn.conn.cursor() as cur:
        with alive_bar(
            total_lines, title="Formating users", bar="classic", spinner="classic"
        ) as bar:
            for datetime in res.keys():
                sql = """ INSERT INTO record (datetime, canvas_code) VALUES (?,?)"""
                await cur.execute(sql, (datetime, "48"))
                record_id = cur.get_cursor().lastrowid
                for user in res[datetime]:
                    name, alltime_count, canvas_count = user
                    # get user id
                    try:
                        pxls_name_id = users_dict[name]
                    except KeyError:
                        # if user does not exist, create it
                        pxls_name_id = await create_pxls_user(name, cur)
                        users_dict[name] = pxls_name_id
                    values = (record_id, pxls_name_id, alltime_count, canvas_count)
                    values_list.append(values)
                    bar()
        sql = """ INSERT INTO pxls_user_stat (record_id, pxls_name_id, alltime_count, canvas_count)
                  VALUES (?,?,?,?)"""
        with alive_bar(
            0,
            title=f"Inserting {len(values_list)} lines",
            bar="classic",
            spinner="classic",
        ) as bar:
            await cur.execute("PRAGMA synchronous = OFF")
            await cur.execute("PRAGMA journal_mode = OFF")
            await cur.execute("BEGIN TRANSACTION;")
            await cur.executemany(sql, values_list)
            await cur.execute("COMMIT;")
            await db_conn.conn.commit()
            bar()
    await db_conn.close_connection()


async def migrate_general_stats():
    with alive_bar(
        0, title="Inserting general stats", bar="classic", spinner="classic"
    ) as bar:

        old_conn = sqlite3.connect(OLD_DB_FILE)
        old_cur = old_conn.execute("SELECT * FROM pxls_general_stats")
        rows = old_cur.fetchall()
        old_conn.close()
        values_list = []
        for row in rows:
            stat_name = row[0]
            value = row[1]
            datetime = row[3]
            values_list.append((stat_name, value, "48", datetime))

        await db_conn.create_connection()
        async with db_conn.conn.cursor() as curs:
            await curs.execute("BEGIN TRANSACTION;")
            await curs.executemany(
                "INSERT INTO pxls_general_stat(stat_name,value,canvas_code,datetime) VALUES (?,?,?,?)",
                values_list,
            )
        await db_conn.conn.commit()
        await db_conn.close_connection()
        bar()


async def main():
    start = time.time()
    await create_all_tables()
    await migrate_general_stats()
    await migrate_pxls_user_stats()
    print("done! time:", time.time() - start, "seconds")


if __name__ == "__main__":
    asyncio.run(main())
