import matplotlib.pyplot as plt
import bar_chart_race as bcr
import pandas
from datetime import datetime

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_connection import DbConnection
from database.db_stats_manager import DbStatsManager
from utils.setup import stats

""" Script to generate a bar chart race video for a given canvas """

async def get_stats_df(dt1,dt2,canvas:bool) -> pandas.DataFrame:
    
    # config
    dates_skipped = 1
    video_duration = 30 # seconds
    title = "Canvas 49 - Top 20"
    steps_per_period = 10
    canvas_code = "49"

    db_conn = DbConnection()
    db_stats = DbStatsManager(db_conn,stats)

    record1 = await db_stats.find_record(dt1)
    record2 = await db_stats.find_record(dt2)

    sql = """
    SELECT datetime, name, alltime_count, canvas_count
    FROM pxls_user_stat
    JOIN pxls_name ON pxls_name.pxls_name_id = pxls_user_stat.pxls_name_id
    JOIN record on record.record_id = pxls_user_stat.record_id
    WHERE pxls_user_stat.record_id BETWEEN ? AND ?
    AND record.canvas_code = ?
    AND pxls_user_stat.pxls_name_id in (
        SELECT pxls_name_id
        FROM pxls_user_stat
        WHERE record_id = ?
        ORDER BY canvas_count DESC
        LIMIT 100 )"""

    print("getting data...")
    rows = await db_conn.sql_select(sql,(
        record1["record_id"],
        record2["record_id"],
        canvas_code,
        record2["record_id"]))
    print("nb rows:",len(rows))

    # step 1 - group by date
    users_dict = {}
    dates_dict = {}
    for row in rows:
        name = row["name"]
        dt = row["datetime"]
        if canvas:
            pixels = row["canvas_count"]
        else:
            pixels = row["alltime_count"]

        try:
            dates_dict[dt][name] = pixels
        except KeyError:
            dates_dict[dt] = {}
            dates_dict[dt][name] = pixels

        users_dict[name] = None
    
    # truncate the data to only keep the top 100 (at the time of dt2)
    last_values_sorted = sorted(dates_dict[record2["datetime"]].items(), key=lambda x: x[1], reverse=True)
    users_list = [u[0] for u in last_values_sorted[0:100]]
    # step 2 - make columns for each user
    columns = {}
    indexes =[]
    for i,dt in enumerate(dates_dict.keys()):
        if i%dates_skipped!=0 and i != len(dates_dict.keys())-1:
            continue
        indexes.append(dt)
        for name in users_list:
            try:
                pixels = dates_dict[dt][name]
            except KeyError:
                pixels = None
            try:
                columns[name].append(pixels)
            except KeyError:
                columns[name] = [pixels]
    nb_dates = len(indexes)
    print("nb dates:",nb_dates)
    df = pandas.DataFrame(columns,index=indexes)

    print("genrating chart...")

    # Set up a figure looking like bar_chart_race's default.
    fig, ax = plt.subplots(figsize=(4, 2.5), dpi=144)
    ax.set_facecolor('.8')
    ax.tick_params(labelsize=8, length=0)
    ax.grid(True, axis='x', color='white')
    ax.set_axisbelow(True)
    [spine.set_visible(False) for spine in ax.spines.values()]

    # Setting background to a solid color fixes the problem.
    fig.patch.set_facecolor('white')

    period_length = ((video_duration*1000)/nb_dates)*dates_skipped
    print(period_length)
    bcr.bar_chart_race(
        df,
        "out.mp4",
        n_bars=20,
        filter_column_colors=True,
        title=title,
        steps_per_period=steps_per_period,
        period_length=period_length,
        shared_fontdict=dict(color="#b9bbbe"),
        bar_kwargs = dict(ec="black",lw=1,alpha=0.9),
        cmap = "tab20",
        period_fmt="%Y-%m-%d %H:%M" 
    )


import time
import asyncio
async def main():
    start = time.time()
    dt1 = datetime(2021,7,1)
    dt2 = datetime.utcnow()
    canvas = True
    await get_stats_df(dt1,dt2,canvas)
    print("done! time:",time.time()-start,"seconds")

if __name__ == "__main__":
    asyncio.run(main())