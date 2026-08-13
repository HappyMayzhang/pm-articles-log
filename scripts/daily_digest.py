#!/usr/bin/env python3
"""每日抓取产品经理文章、去重、推送到微信（PushPlus），并更新去重记录。"""
import datetime
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    "https://www.woshipm.com/pmd/feed",
    "https://www.woshipm.com/zhichang/feed",
    "https://www.woshipm.com/operate/feed",
]

BLOCKLIST_KEYWORDS = [
    "报名", "训练营", "限时优惠", "加入我们", "社群招募", "扫码", "优惠券",
    "秒杀", "内部群", "加微信", "私信我", "点击领取", "免费领取",
]

RECORD_FILE = "已推送记录.md"
LATEST_FILE = "latest.md"
PICK_COUNT = 5


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        creator = ""
        for child in item:
            if child.tag.endswith("creator"):
                creator = (child.text or "").strip()
        author = creator or (item.findtext("author") or "").strip()
        desc_raw = item.findtext("description") or ""
        desc = html.unescape(re.sub(r"<[^>]+>", "", desc_raw)).strip()
        desc = re.sub(r"\s+", " ", desc)[:80]
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "author": author,
                "summary": desc,
                "pub_date": pub_date,
                "source": url,
            })
    return items


def load_seen_links():
    if not os.path.exists(RECORD_FILE):
        return set()
    seen = set()
    with open(RECORD_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) == 3:
                seen.add(parts[2].strip())
    return seen


def is_spam(title):
    return any(kw in title for kw in BLOCKLIST_KEYWORDS)


def pick_articles(candidates, seen_links, count):
    fresh = [c for c in candidates if c["link"] not in seen_links and not is_spam(c["title"])]
    dedup_by_link = {}
    for item in fresh:
        dedup_by_link.setdefault(item["link"], item)
    fresh = list(dedup_by_link.values())

    by_source = {}
    for item in fresh:
        by_source.setdefault(item["source"], []).append(item)

    picked = []
    while len(picked) < count and any(by_source.values()):
        for source in list(by_source.keys()):
            if by_source[source]:
                picked.append(by_source[source].pop(0))
                if len(picked) == count:
                    break
    return picked


def build_markdown(picked, today):
    lines = [f"# 今日产品经理文章推荐 {today}", ""]
    if not picked:
        lines.append("今天没有找到新的、未推送过的文章。")
    for item in picked:
        author = f"（{item['author']}）" if item["author"] else ""
        summary = item["summary"] or "点击查看原文"
        lines.append(f"[{item['title']}]({item['link']}){author} — {summary}")
    return "\n".join(lines) + "\n"


def send_pushplus(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        raise SystemExit("PUSHPLUS_TOKEN not set")
    payload = json.dumps({
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = resp.read().decode("utf-8")
        print(result)
        data = json.loads(result)
        if data.get("code") != 200:
            raise SystemExit(f"PushPlus failed: {result}")


def main():
    today = datetime.date.today().isoformat()
    seen_links = load_seen_links()

    candidates = []
    for url in FEEDS:
        try:
            candidates.extend(fetch_feed(url))
        except Exception as e:
            print(f"WARN: failed to fetch {url}: {e}")

    picked = pick_articles(candidates, seen_links, PICK_COUNT)
    markdown = build_markdown(picked, today)

    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        f.write(markdown)

    if picked:
        with open(RECORD_FILE, "a", encoding="utf-8") as f:
            for item in picked:
                f.write(f"{today} | {item['title']} | {item['link']}\n")

    send_pushplus(f"今日产品经理文章推荐 {today}", markdown)
    print(f"Picked {len(picked)} articles, pushed and recorded.")


if __name__ == "__main__":
    main()
