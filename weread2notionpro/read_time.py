from collections import defaultdict
from datetime import datetime, timezone
from datetime import timedelta
import os

import pendulum

from weread2notionpro.weread_api import WeReadApi
from weread2notionpro.notion_helper import NotionHelper
from weread2notionpro.utils import (
    format_date,
    get_date,
    get_icon,
    get_number,
    get_relation,
    get_title,
)


def insert_to_notion(page_id, timestamp, duration):
    parent = {"database_id": notion_helper.day_database_id, "type": "database_id"}
    properties = {
        "标题": get_title(
            format_date(
                datetime.utcfromtimestamp(timestamp) + timedelta(hours=8),
                "%Y年%m月%d日",
            )
        ),
        "日期": get_date(
            start=format_date(datetime.utcfromtimestamp(timestamp) + timedelta(hours=8))
        ),
        "时长": get_number(duration),
        "时间戳": get_number(timestamp),
        "年": get_relation(
            [
                notion_helper.get_year_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "月": get_relation(
            [
                notion_helper.get_month_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "周": get_relation(
            [
                notion_helper.get_week_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
    }
    if page_id != None:
        notion_helper.client.pages.update(page_id=page_id, properties=properties)
    else:
        notion_helper.client.pages.create(
            parent=parent,
            icon=get_icon("https://www.notion.so/icons/target_red.svg"),
            properties=properties,
        )


def get_file():
    # 设置文件夹路径
    folder_path = "./OUT_FOLDER"

    # 检查文件夹是否存在
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        entries = os.listdir(folder_path)

        file_name = entries[0] if entries else None
        return file_name
    else:
        print("OUT_FOLDER does not exist.")
        return None

HEATMAP_GUIDE = "https://mp.weixin.qq.com/s?__biz=MzI1OTcxOTI4NA==&mid=2247484145&idx=1&sn=81752852420b9153fc292b7873217651&chksm=ea75ebeadd0262fc65df100370d3f983ba2e52e2fcde2deb1ed49343fbb10645a77570656728&token=157143379&lang=zh_CN#rd"


notion_helper = NotionHelper()
weread_api = WeReadApi()
def main():
    api_data = weread_api.get_api_data()
    readTimes = {int(key): value for key, value in api_data.get("readTimes").items()}
    now = pendulum.now("Asia/Shanghai").start_of("day")
    today_timestamp = now.int_timestamp
    if today_timestamp not in readTimes:
        readTimes[today_timestamp] = 0
    readTimes = dict(sorted(readTimes.items()))
    results = notion_helper.query_all(database_id=notion_helper.day_database_id)
    for result in results:
        timestamp = result.get("properties").get("时间戳").get("number")
        duration = result.get("properties").get("时长").get("number")
        id = result.get("id")
        if timestamp in readTimes:
            value = readTimes.pop(timestamp)
            if value != duration:
                insert_to_notion(page_id=id, timestamp=timestamp, duration=value)
    for key, value in readTimes.items():
        insert_to_notion(None, int(key), value)
    backfill_from_read_records()

def backfill_from_read_records():
    """readTimes 里没有（或为 0）的日子，用「阅读记录」补齐。

    背景：2025-04 之后同步断过一次，日表有 68 天缺失、5 天被写成 0，
    而阅读记录里逐书数据还在。只信 readTimes 的话，日/周/月/年 汇总会比明细少 6 万多分钟。
    """
    days = {}
    for r in notion_helper.query_all(database_id=notion_helper.day_database_id):
        p = r["properties"]
        ts = p["时间戳"].get("number")
        if ts is None:
            continue
        days[int(ts)] = (r["id"], p["时长"].get("number") or 0)
    rec = defaultdict(int)
    for r in notion_helper.query_all(database_id=notion_helper.read_database_id):
        p = r["properties"]
        d = p["日期"].get("date")
        if not d:
            continue
        rec[d["start"][:10]] += p["时长"].get("number") or 0
    filled = created = 0
    for day_str, minutes in sorted(rec.items()):
        if minutes <= 0:
            continue
        ts = int(
            datetime.strptime(day_str, "%Y-%m-%d")
            .replace(tzinfo=timezone(timedelta(hours=8)))
            .timestamp()
        )
        cur = days.get(ts)
        if cur is None:
            insert_to_notion(None, ts, minutes)
            created += 1
        elif cur[1] == 0:
            insert_to_notion(page_id=cur[0], timestamp=ts, duration=minutes)
            filled += 1
    if filled or created:
        print(f"阅读记录兜底：改值 {filled} 天、新建 {created} 天")


if __name__ == "__main__":
    main()
