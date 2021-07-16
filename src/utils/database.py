import sqlite3
from sqlite3 import Error
import os

DB_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "database.db")

create_server_table = """CREATE TABLE IF NOT EXISTS servers(
                            server_id INTEGER PRIMARY KEY, 
                            prefix TEXT,
                            alert_channel_id INTEGER,
                            twitch_channel_id TEXT,
                            informations_channel_id,
                            emote_log_channel_id INTEGER,
                            emote_list_channel_id INTEGER
                            
                        );"""

create_pxls_user_table = """ CREATE TABLE IF NOT EXISTS pxls_users(
                            name TEXT PRIMARY KEY,
                            pixel_count INTEGER
                        );"""

create_server_user_table = """ CREATE TABLE IF NOT EXISTS server_pxls_users(
                            server_id INTEGER,
                            name TEXT,
                            FOREIGN KEY(server_id) REFERENCES server(server_id),
                            FOREIGN KEY(name) REFERENCES pxls_user(name),
                            PRIMARY KEY(name,server_id)
                        );"""

create_pxls_user_stats_table = """ CREATE TABLE IF NOT EXISTS pxls_user_stats(
                            name TEXT,
                            alltime_count INTEGER,
                            canvas_count INTEGER,
                            date TIMESTAMP,
                            PRIMARY KEY (name, date)
                            );"""

# create a database connection to the SQLite database specified by db_file
def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file,detect_types=sqlite3.PARSE_DECLTYPES)
        return conn
    except Error as e:
        print(e)

    return conn
# create a table from the create_table_sql statement
def create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except Error as e:
        print(e)

# create a new server into the servers table
def create_server(server_id,prefix):
    conn = create_connection(DB_FILE)
    sql = ''' INSERT INTO servers(server_id,prefix)
              VALUES(?,?) '''
    cur = conn.cursor()
    cur.execute(sql, (server_id,prefix))
    conn.commit()
    print(f'Server {server_id} added to the db')
    return cur.lastrowid

def create_emoji(name, channel_id, twitch_id, discord_id, server_id, url, is_animated):
    conn = create_connection(DB_FILE)
    emoji = (name, channel_id, twitch_id, discord_id, server_id, url, is_animated)
    sql = ''' INSERT INTO emojis(name, channel_id, twitch_id, discord_id, server_id, url, is_animated)
              VALUES(?,?,?,?,?,?,?)'''
    cur = conn.cursor()
    cur.execute(sql, emoji)
    conn.commit()
    return cur.lastrowid

def get_emoji(name):
    sql = '''SELECT * 
            FROM emojis 
            WHERE name = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(name,))
    rows = cur.fetchall()
    if (len(rows))==0:
        return None
    return rows[0]

def get_all_emojis(channel_id):
    sql = '''SELECT * 
            FROM emojis
            WHERE channel_id = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(channel_id,))
    rows = cur.fetchall()
    return rows



def create_pxls_user(name, pxls_count):
    conn = create_connection(DB_FILE)
    sql = ''' INSERT INTO pxls_users(name, pixel_count)
              VALUES(?,?) '''
    cur = conn.cursor()
    cur.execute(sql, (name,pxls_count))
    conn.commit()

def create_server_pxls_user(server_id,name):
    conn = create_connection(DB_FILE)
    sql = ''' INSERT INTO server_pxls_users(server_id, name)
              VALUES(?,?) '''
    cur = conn.cursor()
    cur.execute(sql, (server_id,name))
    conn.commit()
    return cur.lastrowid


def create_tables():
    conn = create_connection(DB_FILE)
    if (conn == None):
        print("Error! cannot create the database connection.")
        return
    create_table(conn,create_server_table)
    create_table(conn,create_pxls_user_table)
    create_table(conn,create_server_user_table)
    create_table(conn,create_pxls_user_stats_table)
    return

# adds a user to the server_pxls_user table and pxls_user table if not added
# returns -1 if the user was already added 
def add_user(server_id,name,pxls_count):
    try:
        # create pxls_user if it doesnt exist
        sql = "SELECT * FROM pxls_users WHERE name = ?"
        conn = create_connection(DB_FILE)
        cur = conn.cursor()
        cur.execute(sql,(name,))
        if (len(cur.fetchall()) == 0):
            create_pxls_user(name,pxls_count)
        # create join table entry (server_pxls_users)
        create_server_pxls_user(server_id,name)
        return name
    except sqlite3.IntegrityError:
        return -1

def remove_user(server_id,name):
    # removing the user from the server_pixel_users table
    sql = "DELETE from server_pxls_users WHERE server_id = ? AND name = ?"
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(server_id,name))
    conn.commit()
    # check if the user has been deleted
    if (conn.total_changes == 0):
        # no changes have been made
        return -1
    
    # check if the user is still in other servers
    sql = "SELECT COUNT(*) FROM server_pxls_users WHERE name=?"
    cur.execute(sql,(name,))
    nb_of_user_servers = cur.fetchall()[0][0]

    # if not, remove it from the pxls_users table too
    if (nb_of_user_servers == 0):
        sql = "DELETE from pxls_users WHERE name = ?"
        cur.execute(sql,(name,))
        conn.commit()

def update_alert_channel(channel_id,server_id):
    conn = create_connection(DB_FILE)
    sql = ''' UPDATE servers
            SET alert_channel_id = ?
            WHERE server_id = ?'''
    cur = conn.cursor()
    cur.execute(sql,(channel_id,server_id))
    conn.commit()

def get_alert_channel(server_id):
    sql = '''SELECT alert_channel_id 
                FROM servers 
                WHERE server_id = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(server_id,))
    rows = cur.fetchall()
    if (len(rows))==0:
        return None
    return rows[0][0]    

def get_all_channels(name):
    '''returns a list of channels_id for the servers tracking the user "name"'''
    sql = '''SELECT alert_channel_id 
            FROM servers
            INNER JOIN server_pxls_users
            ON servers.server_id = server_pxls_users.server_id
            WHERE name = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(name,))
    rows = cur.fetchall()
    res=[]
    for row in rows:
        res.append(row[0])

    return res

# returns a list of all the users tracked in a server
def get_all_server_users(server_id):
    sql = '''SELECT pxls_users.name, pxls_users.pixel_count 
            FROM pxls_users
            INNER JOIN server_pxls_users
            ON server_pxls_users.name = pxls_users.name
            WHERE server_pxls_users.server_id = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(server_id,))
    rows = cur.fetchall()
    return rows

def get_all_users():
    ''' Get all the users ([name,pixel count]) tracked in at least one server'''
    sql = "SELECT name, pixel_count from pxls_users"
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    return rows

def get_all_servers():
    sql = "SELECT server_id from servers"
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    res = []
    for row in rows:
        res.append(row[0])
    return res

def update_pixel_count(name,new_count):
    conn = create_connection(DB_FILE)
    sql = ''' UPDATE pxls_users
            SET pixel_count = ?
            WHERE name = ?'''
    cur = conn.cursor()
    cur.execute(sql,(new_count,name))
    conn.commit()

def update_prefix(prefix,server_id):
    conn = create_connection(DB_FILE)
    sql = ''' UPDATE servers
            SET prefix = ?
            WHERE server_id = ?'''
    cur = conn.cursor()
    cur.execute(sql,(prefix,server_id))
    conn.commit()

def get_prefix(client,message):
    sql = '''SELECT prefix 
                FROM servers 
                WHERE server_id = ?'''
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(message.guild.id,))
    rows = cur.fetchall()
    if (len(rows))==0:
        return None
    return rows[0][0]

def create_pxls_user_stats(name, alltime_count,canvas_count,time):
    conn = create_connection(DB_FILE)
    sql = ''' INSERT INTO pxls_user_stats(name, alltime_count,canvas_count,date)
              VALUES(?,?,?,?) '''
    cur = conn.cursor()

    cur.execute(sql, (name,alltime_count,canvas_count,time))
    conn.commit()

def get_alltime_pxls_count(user,dt):
    sql = """SELECT
                alltime_count,
                date,
                min(abs(JulianDay(date) - JulianDay(?)))*24*3600 as diff_with_query
            FROM pxls_user_stats
            WHERE name = ? """

    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(dt,user))
    res = cur.fetchone()
    if not res:
        return (None,None)
    else:
        return res

def get_canvas_pxls_count(user,dt):
    sql = """SELECT
                canvas_count,
                date,
                min(abs(JulianDay(date) - JulianDay(?)))*24*3600 as diff_with_query
            FROM pxls_user_stats
            WHERE name = ? """

    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    cur.execute(sql,(dt,user))
    res = cur.fetchone()
    if not res:
        return (None,None)
    else:
        return res

def update_all_pxls_stats(alltime_stats,canvas_stats,last_updated):

    conn = create_connection(DB_FILE)
    cur = conn.cursor()

    for user in alltime_stats:
        name = user["username"]
        alltime_count = user["pixels"]
        sql = """INSERT INTO pxls_user_stats(name, date, alltime_count, canvas_count) 
                VALUES (?,?,?,?)
                ON CONFLICT (name,date) 
                DO UPDATE SET
                    alltime_count = ?"""
        cur.execute(sql,(name,last_updated,alltime_count,0,alltime_count))


    for user in canvas_stats:
        name = user["username"]
        canvas_count = user["pixels"]
        sql = """INSERT INTO pxls_user_stats(name, date, canvas_count) 
                VALUES (?,?,?)
                ON CONFLICT (name,date) 
                DO UPDATE SET
                    canvas_count = ?"""
        cur.execute(sql,(name,last_updated,canvas_count,canvas_count))

    conn.commit()

def get_last_leaderboard(canvas=False):
    if canvas == True:
        sql = """SELECT ROW_NUMBER() OVER(ORDER BY canvas_count DESC) AS rank, name, canvas_count, date
                FROM pxls_user_stats
                WHERE date = (select max(date) from pxls_user_stats)
                ORDER by canvas_count desc"""
    else:
        sql = """ SELECT ROW_NUMBER() OVER(ORDER BY alltime_count DESC) AS rank, name, alltime_count, date
                FROM pxls_user_stats
                WHERE date = (select max(date) from pxls_user_stats)
                AND alltime_count IS NOT NULL
                ORDER by alltime_count desc"""

    return sql_select(sql)

def sql_select(query,param=None):
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    if param == None:
        cur.execute(query)
    else:
        cur.execute(query,tuple(param))

    return cur.fetchall()

def sql_update(query,param=None):
    conn = create_connection(DB_FILE)
    cur = conn.cursor()
    if param:
        cur.execute(query,tuple(param))
    else:
        cur.execute(query)
    conn.commit()
    if (conn.total_changes == 0):
        # no changes have been made
        return -1

def get_pixels_placed_between(datetime1,datetime2,canvas:bool,orderby,users=None):
    """ Get the amount of pixels placed between 2 dates
    ## parameters
    - `datetime1`: the oldest date
    - `datetime2`: the most recent date
    - `canvas`: boolean to get the canvas stats instead of alltime
    - `orderby`: sort the return list by: `canvas` (pixels), `alltime` (pixels), `speed` (amount)
    - `users` (optional): 
        - if len is 0 or 1: the return list will have data for all the users
        - if len is more than 1: the return list will only have data for the given users 
    ## return 
    a list in the format:
    List(
        - rank,
        - name,
        - canvas_pixels | alltime_pixels,
        - pixel difference,
        - last date in the db,
        - closest date to datetime1 in the db,
        - closest date to datetime2 in the db)"""
    if orderby == 'speed':
        orderby = "b.canvas_count - a.canvas_count"
    elif orderby == 'canvas':
        orderby = "last.canvas_count"
    elif orderby == 'alltime':
        orderby = "last.alltime_count"
    else:
        raise ValueError("orderby paramater must be: placed, canvas or alltime (got '"+orderby+"')")

    sql = """SELECT 
                ROW_NUMBER() OVER(ORDER BY ({0}) DESC) AS rank,
                a.name,
                last.{1}_count,
                b.canvas_count - a.canvas_count as placed,
                last.date, a.date, b.date
            FROM pxls_user_stats a, pxls_user_stats b, pxls_user_stats last
            WHERE a.name = b.name AND b.name = last.name
            {2}
            AND last.date = (SELECT max(date) FROM pxls_user_stats)
            AND a.date = (SELECT k.date FROM
                            (SELECT c.date, min(abs(JulianDay(c.date) - JulianDay(?)))
                            FROM pxls_user_stats c) k)

            AND b.date = (SELECT l.date FROM
                            (SELECT d.date, min(abs(JulianDay(d.date) - JulianDay(?)))
                            FROM pxls_user_stats d) l)
            ORDER BY {0} desc""".format(
                orderby,
                "canvas" if canvas else "alltime",
                (f"AND a.name IN ({', '.join('?'*len(users))})") if users else ''
            )
    if users:
        users.append(datetime1)
        users.append(datetime2)
        return sql_select(sql,users)

    else:
        return sql_select(sql,(datetime1,datetime2))

import time
def main():
    ''' Test/debug code '''
    #DB_FILE = "test.db"
    # create db connection
    conn = create_connection(DB_FILE)
    create_tables()
    if (conn == None):
        print("Error! cannot create the database connection.")
        return
    
    #create_pxls_user_stats("someone",2070,2046,datetime.utcnow())

    start = time.time()
    ldb = get_last_leaderboard(True)
    getldbtime = (time.time() - start)*1000
    print("time: ",getldbtime,"ms")
    nb_line = 10

    i = 0
    DASH = 40*"-"
    text = DASH + "\n"
    text += "{:<5}| {:<15s}| {:<10s}\n".format("rank","username","canvas px")
    text += DASH + "\n"
    for line in ldb:
        i+=1
        #print(line)
        rank,name, pixels, date = line
        pixels = f'{int(pixels):,}'
        pixels = pixels.replace(","," ")
        text += " {:<4d}| {:<15s}| {:<10s}\n".format(rank,name,pixels)
        if i == nb_line:
            break
    print(text)
    
if __name__ == "__main__":
    main()
