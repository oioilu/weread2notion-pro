#!/usr/bin/env python3
"""自建热力图：Notion 数据库 → PNG（Pillow）→ 上传进 Notion 图片块。

零第三方服务：自己画图、自己上传，不依赖任何外部图床或渲染站。
渲染窗口默认最近 12 个月；HTTP 走 curl（本机可带代理），只依赖 Pillow。
"""
import argparse
import collections
import datetime as dt
import json
import os
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont

API = "https://api.notion.com/v1"
VER_BLOCK = "2022-06-28"   # 块操作/file_upload 用旧版本
VER_DATA = "2026-03-11"    # 数据源查询必须用新版
MARK = "自建热力图"
COLORS = ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E", "#216E39"]
CELL, GAP = 11, 3
LEFT, TOP = 30, 30
LEGEND_H = 26


def _proxy():
    return os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")


def api(method, path, token, body=None, ver=None):
    ver = ver or VER_BLOCK
    args = ["-w", "\n%{http_code}", f"{API}{path}", "-X", method,
            "-H", f"Authorization: Bearer {token}", "-H", f"Notion-Version: {ver}"]
    if body is not None:
        args += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    p = _proxy()
    routes = (["-x", p], []) if p else ([],)
    last = ""
    for i in range(5):
        for route in routes:
            r = subprocess.run(["curl", "-sS", "-m", "90", "--http1.1"] + route + args, capture_output=True, text=True)
            payload, _, code = r.stdout.rpartition("\n")
            code = code.strip()
            if code in ("200", "201"):
                return json.loads(payload) if payload.strip().startswith(("{", "[")) else {}
            last = f"{code} {payload[:200]}"
        time.sleep(1 + i)
    raise RuntimeError(f"{method} {path} -> {last}")


def data_source_id(token, database_id):
    d = api("GET", f"/databases/{database_id}", token, ver=VER_DATA)
    ds = d.get("data_sources") or []
    if not ds:
        raise RuntimeError(f"database {database_id} 无 data_source")
    return ds[0]["id"]


def query_all(token, database_id):
    dsid = data_source_id(token, database_id)
    out, cur = [], None
    while True:
        body = {"page_size": 100}
        if cur:
            body["start_cursor"] = cur
        d = api("POST", f"/data_sources/{dsid}/query", token, body, ver=VER_DATA)
        out += d.get("results", [])
        if not d.get("has_more"):
            break
        cur = d.get("next_cursor")
    return out


def pick(props, name, want):
    p = props.get(name) or {}
    t = p.get("type")
    v = p.get(t)
    if t == want:
        return v
    if t in ("formula", "rollup") and isinstance(v, dict) and v.get("type") == want:
        return v.get(want)
    return None


def level(n, maxn):
    if n <= 0:
        return 0
    q = n / maxn
    return 1 if q <= 0.25 else 2 if q <= 0.5 else 3 if q <= 0.75 else 4


def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render(counts, out_path, unit="", title="", months=12, today=None):
    """GitHub 风格：最近 N 个月，列=周，行=日，带月份/年份/星期标签与颜色图例。"""
    if not counts:
        raise SystemExit("没有可渲染的数据")
    today = today or dt.date.today()
    start = today - dt.timedelta(days=months * 30)
    start = dt.date(start.year, start.month, 1)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # 对齐到周日
    end = today + dt.timedelta(days=(6 - (today.weekday() + 1) % 7))

    window = {d: n for d, n in counts.items() if dt.date.fromisoformat(d) >= start}
    maxn = max(window.values()) if window else 1
    weeks = ((end - start).days + 1) // 7

    w = LEFT + weeks * (CELL + GAP) + 10
    h = TOP + 7 * (CELL + GAP) + LEGEND_H + 6
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    f10, f12, fbold = _font(10), _font(12), _font(12)

    # 星期标签
    for j, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        d.text((2, TOP + j * (CELL + GAP) + 1), lab, fill="#57606a", font=f10)

    # 月份标签 + 年份（间隔不足 3 列就跳过，避免 OctNov 挤在一起）
    last_month, last_idx = None, -9
    for i in range(weeks):
        d0 = start + dt.timedelta(days=i * 7)
        if d0.month != last_month and (i - last_idx) >= 3:
            d.text((LEFT + i * (CELL + GAP), 8), d0.strftime("%b"), fill="#57606a", font=f10)
            if i == 0:
                d.text((LEFT + i * (CELL + GAP), 20), str(d0.year), fill="#24292f", font=fbold)
            last_month, last_idx = d0.month, i

    # 格子
    for i in range(weeks):
        for j in range(7):
            day = start + dt.timedelta(days=i * 7 + j)
            if day > today:
                continue
            n = counts.get(day.isoformat(), 0)
            x, y = LEFT + i * (CELL + GAP), TOP + j * (CELL + GAP)
            d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=COLORS[level(n, maxn)])

    # 图例：Less ▢▢▢▢▢ More
    base_y = TOP + 7 * (CELL + GAP) + 4
    d.text((LEFT, base_y), "Less", fill="#57606a", font=f10)
    x0 = LEFT + 34
    for k in range(5):
        d.rectangle([x0 + k * (CELL + GAP), base_y + 1, x0 + k * (CELL + GAP) + CELL - 1, base_y + CELL],
                    fill=COLORS[k])
    d.text((x0 + 5 * (CELL + GAP) + 4, base_y), "More", fill="#57606a", font=f10)

    total = sum(window.values())
    txt = f"{title}  {total}{(' ' + unit) if unit else ''} in last {months} months"
    d.text((x0 + 5 * (CELL + GAP) + 44, base_y), txt.strip(), fill="#24292f", font=f12)

    img.save(out_path, "PNG")
    return out_path


def upload_png(token, path):
    name = os.path.basename(path)[:100]
    up = api("POST", "/file_uploads", token, {"filename": name, "content_type": "image/png"})
    last = ""
    routes = [[], ["-x", _proxy()]] if _proxy() else [[]]
    for i in range(4):
        for route in routes:
            r = subprocess.run(["curl", "-sS", "-m", "120", "--http1.1"] + route + [
                "-o", "/dev/null", "-w", "%{http_code}",
                "-X", "POST", up["upload_url"],
                "-H", f"Authorization: Bearer {token}", "-H", f"Notion-Version: {VER_BLOCK}",
                "-F", f"file=@{path};type=image/png"], capture_output=True, text=True)
            if r.stdout.strip() in ("200", "201"):
                return up["id"]
            last = r.stdout.strip() or r.stderr.strip()[:60]
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"上传 PNG 失败 {last}")


def find_blocks(token, page_id, depth=3, parent=None):
    """递归遍历，返回 [(block, parent_id)]，以便把热力图放回原来 embed 所在的列里。"""
    out, cur = [], None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100" + (f"&start_cursor={cur}" if cur else "")
        d = api("GET", path, token)
        out += [(b, page_id) for b in d.get("results", [])]
        if not d.get("has_more"):
            break
        cur = d.get("next_cursor")
    if depth > 1:
        for b, par in list(out):
            if b.get("has_children"):
                out += find_blocks(token, b["id"], depth - 1, b["id"])
    return out


def publish(token, page_id, path):
    up_id = upload_png(token, path)
    ours, stale, stale_parent = None, [], page_id
    for b, par in find_blocks(token, page_id):
        t = b.get("type")
        if t == "image":
            cap = "".join(x.get("plain_text", "") for x in (b["image"].get("caption") or []))
            if MARK in cap:
                ours = b["id"]
        if t == "embed" and "malinkang.com" in (b.get("embed") or {}).get("url", ""):
            stale.append(b["id"])
            stale_parent = par

    body = {"type": "file_upload", "file_upload": {"id": up_id},
            "caption": [{"type": "text", "text": {"content": MARK}}]}
    if ours:
        # 更新块时 image 里不能带 type（Notion 校验：body.image.type should be not present）
        api("PATCH", f"/blocks/{ours}", token,
            {"image": {k: v for k, v in body.items() if k != "type"}})
        action = f"更新图片块 {ours[:8]}"
    else:
        api("PATCH", f"/blocks/{stale_parent}/children", token, {"children": [{"type": "image", "image": body}]})
        action = "新建图片块" + ("" if stale_parent == page_id else "（替换原 embed 所在列）")
    for bid in stale:
        api("PATCH", f"/blocks/{bid}", token, {"archived": True})
    return action, len(stale)


def resolve():
    """从 NotionHelper 拿页面与「阅读记录」库。"""
    from weread2notionpro.notion_helper import NotionHelper
    nh = NotionHelper()
    # 用「日」表：它是逐日分钟数的准绳（阅读记录只作兜底来源）
    if not nh.page_id or not nh.day_database_id:
        raise SystemExit("环境变量里找不到页面或日表")
    return nh.page_id, nh.day_database_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.getenv("NOTION_TOKEN"))
    ap.add_argument("--page")
    ap.add_argument("--db")
    ap.add_argument("--date-prop", default="日期")
    ap.add_argument("--value-prop")
    ap.add_argument("--agg", choices=["count", "sum"], default="count")
    ap.add_argument("--unit", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--out", default="heatmap.png")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not (a.page and a.db):
        a.page, a.db = resolve()
    if not a.token:
        raise SystemExit("没有 Notion 令牌")

    rows = query_all(a.token, a.db)
    counts = collections.Counter()
    for r in rows:
        dv = pick(r["properties"], a.date_prop, "date")
        if not dv or not dv.get("start"):
            continue
        day = dv["start"][:10]
        if a.agg == "count":
            counts[day] += 1
        else:
            n = pick(r["properties"], a.value_prop, "number") if a.value_prop else None
            counts[day] += int(n or 0)
    render(counts, a.out, a.unit, a.title, a.months)
    print(f"渲染 {a.out} | 数据点 {len(counts)} | 总合计 {sum(counts.values())}")
    if a.dry_run:
        return
    action, deleted = publish(a.token, a.page, a.out)
    print(f"{action} | 清理旧 embed {deleted} 个")


if __name__ == "__main__":
    main()