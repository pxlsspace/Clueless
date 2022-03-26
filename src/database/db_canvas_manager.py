import os
import re
from database.db_connection import DbConnection
from utils.log import get_logger

logger = get_logger(__name__)

basepath = os.path.dirname(__file__)
CANVASES_FOLDER = os.path.abspath(
    os.path.join(basepath, "..", "..", "resources", "canvases")
)


class DbCanvasManager:
    """A class to manage templates in the database"""

    def __init__(self, db_conn: DbConnection) -> None:
        self.db = db_conn

    async def setup(self):
        canvas_counter = 0
        loaded_canvases = 0
        for canvas_code in os.listdir(CANVASES_FOLDER):
            canvas_counter += 1
            has_logs = False
            has_final = False
            for root, dirs, files in os.walk(os.path.join(CANVASES_FOLDER, canvas_code)):
                for file in files:
                    if file.endswith(".log"):
                        has_logs = True
                    elif file == os.path.join(f"final c{canvas_code}.png"):
                        has_final = True

            # load the font image
            if not has_final:
                logger.warning(
                    f"Failed to load canvas {canvas_code}: canvas final not found."
                )
                continue
            await self.create_canvas(canvas_code)
            await self.update_canvas(canvas_code, has_logs=has_logs)
            loaded_canvases += 1
        logger.info(f"{loaded_canvases}/{canvas_counter} canvas archives loaded.")

    async def create_tables(self):

        create_user_keys_table = """
            CREATE TABLE IF NOT EXISTS canvas(
                canvas_code TEXT PRIMARY KEY,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                has_logs BOOLEAN,
                size INTEGER,
                placed_pixels INTEGER,
                users INTEGER,
                non_virgin_pixels INTEGER
            )
        """

        await self.db.sql_update(create_user_keys_table)

    async def create_canvas(self, canvas_code):
        """Add a canvas in the database, return its rowid or None if it already exists"""
        sql = "INSERT OR IGNORE INTO canvas(canvas_code) VALUES (?)"
        return await self.db.sql_insert(sql, canvas_code)

    async def get_canvas(self, canvas_code: str):
        """Get a canvas sqlrow with the given canvas code, Return None if it doesn't exist"""
        sql = """SELECT * FROM canvas WHERE canvas_code = ?"""
        rows = await self.db.sql_select(sql, canvas_code)
        if not rows:
            return None
        else:
            return rows[0]

    async def update_canvas(self, canvas_code, **kwargs):
        """Update a canvas"""
        if not kwargs:
            return None
        sql = "UPDATE canvas {} WHERE canvas_code = ?".format(
            "".join([f"SET {key} = ?" for key in kwargs.keys()])
        )
        return await self.db.sql_update(sql, tuple(kwargs.values()) + (canvas_code,))

    async def get_logs_canvases(self, raw=False):
        """Get all the canvases that have logs."""
        canvases = await self.db.sql_select("SELECT * FROM canvas WHERE has_logs = TRUE")
        if raw:
            return canvases
        else:
            res = [c["canvas_code"] for c in canvases]
            res.sort(key=natural_keys)
            return res

    async def get_all_canvases(self, raw=False):
        """Get all the canvases that have logs."""
        canvases = await self.db.sql_select("SELECT * FROM canvas")
        if raw:
            return canvases
        else:
            res = [c["canvas_code"] for c in canvases]
            res.sort(key=natural_keys)
            return res


def atoi(text):
    return int(text) if text.isdigit() else text


def natural_keys(text):
    return [atoi(c) for c in re.split(r"(\d+)", text)]
