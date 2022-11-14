import asyncio
import os
import re
import shutil
import sys
import tarfile
import time

import aiohttp
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from utils.setup import DbCanvasManager, DbConnection  # noqa: E402
from utils.utils import get_content  # noqa: E402

basepath = os.path.dirname(__file__)
CANVASES_FOLDER = os.path.abspath(
    os.path.join(basepath, "..", "..", "resources", "canvases")
)
LOGS_URL = "https://pxls.space/extra/logs/"


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


async def get_logs_urls():
    """Get a list of all the logs urls"""
    logs_urls = []
    html_page = await get_content(LOGS_URL, "bytes")

    regex = r"\/pixels_c(.*)\.sanit\.log\.tar\.xz"

    soup = BeautifulSoup(html_page, "html.parser")
    for link in soup.findAll("a"):
        url = LOGS_URL + link.get("href")
        match = re.findall(regex, url)
        if match:
            canvas_code = match[0]
            logs_urls.append(
                {"canvas_code": canvas_code, "url": url, "filename": url.split("/")[-1]}
            )
    return logs_urls


async def main():
    start = time.time()

    # getting the canvases that already have logs
    db_conn = DbConnection()
    db_canvas = DbCanvasManager(db_conn)
    await db_canvas.setup()
    canvases_with_logs = await db_canvas.get_logs_canvases()

    # getting the logs available on the pxls page
    logs_urls = await get_logs_urls()

    for log in logs_urls:
        canvas_code = log["canvas_code"]
        logs_url = log["url"]
        filename = log["filename"]
        if canvas_code not in canvases_with_logs:
            # get file size
            session = aiohttp.ClientSession()
            d = await session.head(logs_url)
            await session.close()
            size = d.content_length

            # get disk free space
            total, used, free = shutil.disk_usage("/")
            print("-" * 73)
            input_str = "Logs to download for c{}: {}\nSize: {}, Free Space: {} - Confirm download? (y/n): ".format(
                canvas_code,
                logs_url,
                sizeof_fmt(size),
                sizeof_fmt(free),
            )

            if input(input_str).lower() == "y":
                # check if log is already here
                extract_dir = os.path.join(CANVASES_FOLDER, canvas_code)
                log_path = os.path.join(extract_dir, f"pixels_c{canvas_code}.sanit.log")
                if os.path.exists(log_path):
                    print("Logs already downloaded (final canvas image might be missing)")
                    continue

                # download compressed
                compressed_logs_path = os.path.join(os.curdir, filename)
                print(f"Dowloading into {compressed_logs_path}... ", end="", flush=True)
                compressed_logs = await get_content(logs_url, "bytes")
                open(compressed_logs_path, "wb").write(compressed_logs)
                print("done! ")

                try:
                    if not os.path.exists(extract_dir):
                        os.makedirs(extract_dir)
                    print(f"Extracting into {extract_dir}... ", end="", flush=True)
                    tar = tarfile.open(compressed_logs_path, "r:xz")
                    tar.extractall(extract_dir)
                    tar.close()
                    print("done!")
                finally:
                    print(f"Deleting {compressed_logs_path}... ", end="", flush=True)
                    os.remove(compressed_logs_path)
                    del compressed_logs_path
                    print("done!")
            else:
                print("Cancelled")
    print("Done in", round(time.time() - start, 2), "seconds")
    return None


if __name__ == "__main__":
    asyncio.run(main())
