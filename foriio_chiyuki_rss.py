import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape

import requests


API_URL = "https://api.foriio.com/api/v1/users/yamaguchichiyuki/works"
PROFILE_URL = "https://www.foriio.com/yamaguchichiyuki"

OUTPUT_FILE = "foriio_chiyuki.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": PROFILE_URL,
}


def fetch_json(url, params=None):
    last_error = None

    for attempt in range(1, 4):
        try:
            print(f"取得中: {url}  試行 {attempt}/3")

            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=30,
            )

            print("HTTP:", response.status_code)

            response.raise_for_status()

            return response.json()

        except Exception as e:
            last_error = e
            print("取得失敗:", repr(e))

            if attempt < 3:
                print("10秒待って再試行します")
                time.sleep(10)

    raise RuntimeError(
        f"3回とも取得に失敗しました: {last_error}"
    )


def parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except Exception:
        return None


def rss_date(dt):
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return format_datetime(dt)


def get_work_link(work):
    screen_name = work.get("screen_name") or "yamaguchichiyuki"

    signed_ref = work.get("signed_ref")

    if signed_ref:
        return (
            f"https://www.foriio.com/"
            f"{screen_name}/works/{signed_ref}"
        )

    work_id = work.get("id")

    if work_id:
        return (
            f"https://www.foriio.com/"
            f"{screen_name}/works/{work_id}"
        )

    return PROFILE_URL


def load_existing_items():
    items = {}

    if not os.path.exists(OUTPUT_FILE):
        return items

    try:
        tree = ET.parse(OUTPUT_FILE)
        root = tree.getroot()

        for item in root.findall("./channel/item"):
            guid_el = item.find("guid")

            if guid_el is None or not guid_el.text:
                continue

            guid = guid_el.text.strip()

            items[guid] = {
                "title": (
                    item.findtext("title") or ""
                ),
                "link": (
                    item.findtext("link") or ""
                ),
                "guid": guid,
                "description": (
                    item.findtext("description") or ""
                ),
                "pubDate": (
                    item.findtext("pubDate") or ""
                ),
            }

        print(
            "既存RSS:",
            len(items),
            "件"
        )

    except Exception as e:
        print(
            "既存RSS読み込み失敗:",
            repr(e)
        )

    return items


def fetch_all_works():
    all_works = []
    seen = set()

    page = 1

    while True:
        print()
        print(f"API page={page}")

        data = fetch_json(
            API_URL,
            params={
                "page": page,
            },
        )

        works = data.get("works")

        if not isinstance(works, list):
            raise RuntimeError(
                "APIの works が配列ではありません"
            )

        meta = data.get("meta") or {}

        print(
            "このページ:",
            len(works),
            "件"
        )

        print(
            "meta:",
            meta
        )

        for work in works:
            work_id = work.get("id")

            if work_id is None:
                continue

            key = str(work_id)

            if key in seen:
                continue

            seen.add(key)
            all_works.append(work)

        total_pages = meta.get("total_pages")

        if isinstance(total_pages, int):
            if page >= total_pages:
                break

        elif len(works) == 0:
            break

        else:
            # metaが変わった場合の安全策
            if len(works) < 20:
                break

        page += 1

        if page > 100:
            raise RuntimeError(
                "ページ数が異常です。処理を中止します"
            )

    return all_works


def work_to_item(work):
    work_id = work.get("id")

    title = (
        work.get("title")
        or f"foriio作品 {work_id}"
    ).strip()

    link = get_work_link(work)

    guid = f"foriio-work-{work_id}"

    published_at = parse_iso_datetime(
        work.get("published_at")
    )

    pub_date = rss_date(published_at)

    roles = work.get("user_roles") or []

    if isinstance(roles, list):
        roles_text = "、".join(
            str(x) for x in roles if x
        )
    else:
        roles_text = str(roles)

    work_type = (
        work.get("type") or ""
    )

    thumbnail = (
        work.get("thumbnail") or ""
    )

    description_parts = []

    if roles_text:
        description_parts.append(
            f"担当：{escape(roles_text)}"
        )

    if work_type:
        description_parts.append(
            f"種類：{escape(work_type)}"
        )

    if thumbnail:
        description_parts.append(
            (
                f'<p><img src="{escape(thumbnail)}" '
                f'alt="{escape(title)}"></p>'
            )
        )

    description = "<br>".join(
        description_parts
    )

    return {
        "title": title,
        "link": link,
        "guid": guid,
        "description": description,
        "pubDate": pub_date or "",
        "_datetime": published_at,
    }


def parse_existing_pubdate(value):
    if not value:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


def build_rss(items):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        }
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = "山口ちゆき - foriio"

    ET.SubElement(
        channel,
        "link"
    ).text = PROFILE_URL

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "foriio 山口ちゆきさんの"
        "新着作品を配信する非公式RSS"
    )

    ET.SubElement(
        channel,
        "language"
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(timezone.utc)
    )

    for item_data in items:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = item_data["title"]

        ET.SubElement(
            item,
            "link"
        ).text = item_data["link"]

        guid = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false"
            }
        )

        guid.text = item_data["guid"]

        ET.SubElement(
            item,
            "description"
        ).text = item_data["description"]

        if item_data["pubDate"]:
            ET.SubElement(
                item,
                "pubDate"
            ).text = item_data["pubDate"]

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    print("=" * 70)
    print("山口ちゆき foriio RSS")
    print("=" * 70)

    existing = load_existing_items()

    try:
        works = fetch_all_works()

        print()
        print(
            "API取得作品数:",
            len(works)
        )

        if not works:
            raise RuntimeError(
                "作品が0件だったためRSSを更新しません"
            )

        current_items = {}

        for work in works:
            item = work_to_item(work)

            current_items[
                item["guid"]
            ] = item

        print(
            "有効作品数:",
            len(current_items)
        )

        # 現在のAPI取得分を優先し、
        # 過去RSSにしかない項目も残す
        merged = {}

        for guid, old in existing.items():
            old["_datetime"] = (
                parse_existing_pubdate(
                    old.get("pubDate")
                )
            )

            merged[guid] = old

        for guid, current in current_items.items():
            merged[guid] = current

        items = list(
            merged.values()
        )

        items.sort(
            key=lambda x: (
                x.get("_datetime")
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
            reverse=True,
        )

        print(
            "RSS保存件数:",
            len(items)
        )

        print()
        print("上位10件")

        for i, item in enumerate(
            items[:10],
            start=1
        ):
            print(
                f"{i:2}. "
                f"{item['pubDate']} | "
                f"{item['title']}"
            )

        build_rss(items)

        print()
        print(
            f"保存完了: {OUTPUT_FILE}"
        )

    except Exception as e:
        print()
        print(
            "エラー:",
            repr(e)
        )

        print(
            "RSSは更新せず、"
            "既存ファイルを保持します"
        )

        raise


if __name__ == "__main__":
    main()