import sqlite3
from sqlite3 import Error

#connection = sqlite3.connect('emotes.db')
DB_FILE = 'database.db'


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
# create a database connection to the SQLite database specified by db_file
def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
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

# returns a list of channels_id for the servers tracking the user "name"
def get_all_channels(name):
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

# returns all the users tracked in any server
def get_all_users():
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


def main():
    #DB_FILE = "test.db"
    # create db connection
    conn = create_connection(DB_FILE)
    if (conn == None):
        print("Error! cannot create the database connection.")
        return
    
    print(get_all_servers())

    sql ="SELECT * FROM servers"

    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()

    print(cursor.fetchall())
    print("done")

if __name__ == "__main__":
    main()
