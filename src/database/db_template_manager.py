from database.db_connection import DbConnection
from datetime import datetime, timezone
# This import is only necessary for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from utils.pxls.template_manager import Template, Combo


class DbTemplateManager():
    """A class to manage templates in the database"""

    def __init__(self, db_conn: DbConnection) -> None:
        self.db = db_conn

    async def create_tables(self):

        create_template_table = """
            CREATE TABLE IF NOT EXISTS template(
                id INTEGER PRIMARY KEY,
                name TEXT,
                url TEXT,
                canvas_code TEXT,
                owner_id TEXT,
                hidden BOOLEAN,
                FOREIGN KEY(owner_id) REFERENCES discord_user(discord_id)
            );
        """

        create_template_stat_table = """
            CREATE TABLE IF NOT EXISTS template_stat(
                template_id INTEGER,
                datetime TIMESTAMP,
                progress INTEGER,
                PRIMARY KEY(template_id, datetime),
                FOREIGN KEY(template_id) REFERENCES template(id)
            );
        """
        await self.db.sql_update(create_template_table)
        await self.db.sql_update(create_template_stat_table)

    async def get_template_id(self, t: "Template"):
        """Return the template ID matching with the args from the database, Return None if it doesn't exist"""
        sql = """SELECT id FROM template WHERE name = ? AND canvas_code = ? and owner_id = ? and hidden = ?"""
        rows = await self.db.sql_select(sql, (t.name, t.canvas_code, t.owner_id, t.hidden))
        if not rows:
            return None
        else:
            return rows[0][0]

    async def create_template(self, t: "Template"):
        """Add a template in the database and return its ID or None if it already exists"""
        template_id = await self.get_template_id(t)
        if template_id:
            return None
        sql = "INSERT INTO template(name, url, canvas_code, owner_id, hidden) VALUES (?, ?, ?, ?, ?)"
        return await self.db.sql_insert(sql, (t.name, t.url, t.canvas_code, t.owner_id, t.hidden))

    async def create_template_stat(self, template: "Template", datetime, progress):
        """Add a template stat in the database"""
        template_id = await self.get_template_id(template)
        if not template_id:
            return None
        sql = "INSERT INTO template_stat(template_id, datetime, progress) VALUES(?, ?, ?)"
        return await self.db.sql_insert(sql, (template_id, datetime, progress))

    async def update_template(self, t: "Template", new_url, new_name, new_owner_id):
        """Update a template URL, return None"""
        template_id = await self.get_template_id(t)
        if not template_id:
            return None
        sql = """
            UPDATE template
            SET url = ?, name = ?, owner_id = ?
            WHERE id = ?
            """
        await self.db.sql_insert(sql, (new_url, new_name, new_owner_id, template_id))
        return template_id

    async def delete_template(self, t: "Template"):
        """Delete a template and all its stats from the database"""
        template_id = await self.get_template_id(t)
        sql = "DELETE from template_stat WHERE template_id = ?"
        await self.db.sql_update(sql, template_id)

        sql = "DELETE from template WHERE id = ?"
        await self.db.sql_update(sql, template_id)

    async def get_all_templates(self, canvas_code):
        """Get all the templates from the database (as database objects)"""
        sql = "SELECT * FROM template WHERE canvas_code = ?"
        return await self.db.sql_select(sql, canvas_code)

    async def get_template_progress(self, template: "Template", datetime):
        """ Get the progress of a template at a given datetime"""
        sql = """
            SELECT *, min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM template_stat
            WHERE template_id = (
                SELECT id
                FROM template
                WHERE name = ? AND canvas_code = ? and owner_id = ? and hidden = ?
            )
        """
        res = await self.db.sql_select(sql, (datetime, template.name, template.canvas_code, template.owner_id, template.hidden))
        if not res or all([r is None for r in list(res[0])]):
            return None
        else:
            return res[0]

    async def get_template_oldest_progress(self, template: "Template"):
        """ Get the progress of a template at a given datetime"""
        template_id = await self.get_template_id(template)
        sql = """
            SELECT *, min(abs(JulianDay(datetime) - JulianDay(?)))*24*3600 as diff_with_time
            FROM template_stat
            WHERE template_id = ?
        """
        res = await self.db.sql_select(sql, (datetime.min, template_id))
        if not res:
            return None
        else:
            return res[0]

    async def get_last_update_time(self) -> datetime:
        """Get the last datetime inserted in the template_stat table"""
        sql = "SELECT datetime FROM template_stat ORDER BY datetime DESC LIMIT 1"
        res = await self.db.sql_select(sql)
        if not res:
            return None

        res_datetime = res[0][0]
        res_datetime.replace(tzinfo=timezone.utc)
        return res_datetime

    async def get_all_template_data(self, t: "Template", dt1: datetime, dt2: datetime):
        """Get all the template stats between 2 datetimes from the database (Return `None` if not found)"""
        template_id = await self.get_template_id(t)
        if not template_id:
            return None
        sql = """
            SELECT datetime, progress
            FROM template_stat
            WHERE
                template_id = ?
                AND datetime BETWEEN ? AND ?
            ORDER BY datetime
        """
        rows = await self.db.sql_select(sql, (template_id, dt1, dt2))
        if not rows:
            return None
        return rows

    async def create_combo_stat(self, combo: "Combo", datetime, progress):
        """Save the combo stats in the database, create a combo template in the
        database if it's not found"""
        if not await self.get_template_id(combo):
            await self.create_template(combo)
            print("New combo created in the database")
        return await self.create_template_stat(combo, datetime, progress)
