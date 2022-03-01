import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()
default_log_level = os.environ.get("LOG_LEVEL")
if default_log_level:
    default_log_level = getattr(logging, default_log_level)
else:
    default_log_level = logging.INFO


def get_logger(name, level="DEBUG", file="clueless.log", in_console=True):
    """Get a logger with the default format and handlers.

    - Write logs in files no matter what (with level >DEBUG).
    - Console logs depends on the .env LOG_LEVEL variable

    Parameters
    ----------
    name: The logger's name.
    level: The logger's level for the console (can be None to not write in files)
    file: The logger's file.
    in_console: To add a StreamHandler to the logger."""
    level = getattr(logging, level)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    datetime_format = '%Y-%m-%d %H:%M:%S'
    log_format = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    formatter = logging.Formatter(log_format, datetime_format)

    if file is not None:
        file_handler = logging.FileHandler(
            filename="logs/" + file, encoding='utf-8', mode='a'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    if in_console:
        # formatter
        console_format = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
        console_formatter = logging.Formatter(console_format, '%H:%M:%S')

        # stdout
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(default_log_level)
        console_handler.addFilter(lambda record: record.levelno <= default_log_level)
        logger.addHandler(console_handler)

        # stderr
        console_handler_err = logging.StreamHandler()
        console_handler_err.setFormatter(console_formatter)
        console_handler_err.setLevel(logging.WARNING)
        logger.addHandler(console_handler_err)

    return logger


def setup_loggers():
    """setup the loggers"""

    # make the log folder if it doesn't exist
    log_folder = "logs"
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    # Silence irrelevant loggers
    get_logger(name="disnake", level="INFO", file=None)
    get_logger(name="disnake.http", level="WARNING", file=None)
    get_logger(name="disnake.gateway", level="WARNING", file=None)
    get_logger(name="websockets", level="ERROR", file=None)

    root = logging.getLogger()
    root.setLevel(logging.INFO)


def close_loggers():
    # close all handlers correctly
    log = logging.getLogger()
    handlers = log.handlers[:]
    for hdlr in handlers:
        hdlr.close()
        log.removeHandler(hdlr)
