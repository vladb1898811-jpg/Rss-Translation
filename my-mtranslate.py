import configparser
import datetime
import hashlib
import os
import time
from urllib import parse
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from jinja2 import Template
from mtranslate import translate


def get_md5_value(src):
    _m = hashlib.sha256()
    _m.update(src.encode(encoding="utf-8"))
    return _m.hexdigest()


def getTime(e):
    try:
        struct_time = e.published_parsed
    except AttributeError:
        struct_time = time.localtime()

    return datetime.datetime(*struct_time[:6])


class BingTran:
    def __init__(
        self,
        url,
        source="auto",
        target="zh-CN",
        rss_text=None
    ):
        self.url = url
        self.source = source
        self.target = target

        if rss_text is not None:
            self.d = feedparser.parse(rss_text)
        else:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/131.0 Safari/537.36"
                )
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=15
            )

            response.raise_for_status()

            self.d = feedparser.parse(response.text)

    def tr(self, content):
        if not content:
            return ""

        max_attempts = 4

        for attempt in range(max_attempts):
            try:
                result = translate(
                    content,
                    to_language=self.target,
                    from_language=self.source
                )

                time.sleep(2)

                return result

            except Exception as e:
                error_text = str(e)

                if (
                    "429" in error_text
                    or "Too Many Requests" in error_text
                ):
                    wait_time = 10 * (attempt + 1)

                    print(
                        "Translation rate limit (429). "
                        "Waiting %s seconds before retry..."
                        % wait_time
                    )

                    time.sleep(wait_time)

                else:
                    print(
                        "Translation error: %s"
                        % error_text
                    )

                    return ""

        print(
            "Translation failed after %s attempts"
            % max_attempts
        )

        return ""

    def get_newcontent(self, max_item=10):
        item_set = set()
        item_list = []

        for entry in self.d.entries:
            try:
                title = self.tr(entry.title)
            except Exception:
                title = ""

            if not hasattr(entry, "link"):
                continue

            parsed_link = urlparse(entry.link)

            if not all(
                [
                    parsed_link.scheme,
                    parsed_link.netloc
                ]
            ):
                continue

            link = entry.link
            description = ""

            try:
                description = self.tr(entry.summary)

            except Exception:
                try:
                    description = self.tr(
                        entry.content[0].value
                    )

                except Exception:
                    pass

            guid = link
            pubDate = getTime(entry)

            one = {
                "title": title,
                "link": link,
                "description": description,
                "guid": guid,
                "pubDate": pubDate,
            }

            if guid not in item_set:
                item_set.add(guid)
                item_list.append(one)

            if len(item_list) >= max_item:
                break

        sorted_list = sorted(
            item_list,
            key=lambda x: x["pubDate"],
            reverse=True
        )

        feed = self.d.feed

        try:
            rss_description = self.tr(
                feed.subtitle
            )

        except AttributeError:
            rss_description = ""

        newfeed = {
            "title": self.tr(feed.title),
            "link": feed.link,
            "description": rss_description,
            "lastBuildDate": getTime(feed),
            "items": sorted_list,
        }

        return newfeed


def update_readme(links):
    with open(
        "README.md",
        "r+",
        encoding="UTF-8"
    ) as f:
        list1 = f.readlines()

    list1 = list1[:13] + links

    with open(
        "README.md",
        "w+",
        encoding="UTF-8"
    ) as f:
        f.writelines(list1)


def tran(sec, max_item):
    xml_file = os.path.join(
        BASE,
        f'{get_cfg(sec, "name")}.xml'
    )

    url = get_cfg(sec, "url")
    old_md5 = get_cfg(sec, "md5")

    source, target = get_cfg_tra(
        sec,
        config
    )

    global links

    links += [
        " - %s [%s](%s) -> [%s](%s)\n"
        % (
            sec,
            url,
            url,
            get_cfg(sec, "name"),
            parse.quote(xml_file)
        )
    ]

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "Chrome/131.0 Safari/537.36"
            )
        }

        r = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        r.raise_for_status()

        new_md5 = get_md5_value(r.text)

    except Exception as e:
        print(
            "Error occurred when fetching RSS content "
            "for %s: %s"
            % (sec, str(e))
        )
        return

    if old_md5 == new_md5:
        print(
            "No update needed for %s"
            % sec
        )
        return

    print(
        "Updating %s..."
        % sec
    )

    try:
        feed = BingTran(
            url,
            target=target,
            source=source,
            rss_text=r.text
        ).get_newcontent(
            max_item=max_item
        )

    except Exception as e:
        print(
            "Error occurred when translating RSS content "
            "for %s: %s"
            % (sec, str(e))
        )
        return

    rss_items = []

    for item in feed["items"]:
        title = item["title"]
        link = item["link"]
        description = item["description"]
        guid = item["guid"]
        pubDate = item["pubDate"]

        soup = BeautifulSoup(
            description,
            "html.parser"
        )

        description = soup.get_text()

        description = (
            description
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

        link = link.replace(
            "&",
            "&amp;"
        )

        guid = guid.replace(
            "&",
            "&amp;"
        )

        one = dict(
            title=title,
            link=link,
            description=description,
            guid=guid,
            pubDate=pubDate
        )

        rss_items.append(one)

    rss_title = feed["title"]
    rss_link = feed["link"]
    rss_description = feed["description"]

    rss_last_build_date = (
        feed["lastBuildDate"]
        .strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
    )

    template = Template(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{{ rss_title }}</title>
    <link>{{ rss_link }}</link>
    <description>{{ rss_description }}</description>
    <lastBuildDate>{{ rss_last_build_date }}</lastBuildDate>
    {% for item in rss_items -%}
    <item>
      <title>{{ item.title }}</title>
      <link>{{ item.link }}</link>
      <description><![CDATA[{{ item.description }}]]></description>
      <guid>{{ item.guid }}</guid>
      <pubDate>{{ item.pubDate.strftime('%a, %d %b %Y %H:%M:%S GMT') }}</pubDate>
    </item>
    {% endfor -%}
  </channel>
</rss>"""
    )

    rss = template.render(
        rss_title=rss_title,
        rss_link=rss_link,
        rss_description=rss_description,
        rss_last_build_date=rss_last_build_date,
        rss_items=rss_items
    )

    try:
        os.makedirs(
            BASE,
            exist_ok=True
        )

    except Exception as e:
        print(
            "Error occurred when creating directory "
            "%s: %s"
            % (BASE, str(e))
        )
        return

    if os.path.isfile(xml_file):
        try:
            with open(
                xml_file,
                "r",
                encoding="utf-8"
            ) as f:
                old_rss = f.read()

            if rss == old_rss:
                print(
                    "No change in RSS content for %s"
                    % sec
                )
                return

            os.remove(xml_file)

        except Exception as e:
            print(
                "Error occurred when deleting RSS file "
                "%s for %s: %s"
                % (
                    xml_file,
                    sec,
                    str(e)
                )
            )
            return

    try:
        with open(
            xml_file,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(rss)

    except Exception as e:
        print(
            "Error occurred when writing RSS file "
            "%s for %s: %s"
            % (
                xml_file,
                sec,
                str(e)
            )
        )
        return

    set_cfg(
        sec,
        "md5",
        new_md5
    )

    with open(
        "test.ini",
        "w",
        encoding="utf-8"
    ) as configfile:
        config.write(configfile)


def get_cfg(sec, name):
    return config.get(
        sec,
        name
    ).strip('"')


def set_cfg(sec, name, value):
    config.set(
        sec,
        name,
        '"%s"' % value
    )


def get_cfg_tra(sec, config):
    cc = config.get(
        sec,
        "action"
    ).strip('"')

    if cc == "auto":
        source = "auto"
        target = "zh-CN"

    else:
        source = cc.split("->")[0]
        target = cc.split("->")[1]

    return source, target


config = configparser.ConfigParser()

config.read("test.ini")

BASE = get_cfg(
    "cfg",
    "base"
)

try:
    os.makedirs(BASE)

except:
    pass

links = []

secs = config.sections()

for x in secs[1:]:
    max_item = int(
        get_cfg(
            x,
            "max"
        )
    )

    tran(
        x,
        max_item
    )

update_readme(links)

with open(
    "test.ini",
    "w",
    encoding="utf-8"
) as configfile:
    config.write(configfile)


YML = "README.md"

with open(
    YML,
    "r+",
    encoding="UTF-8"
) as f:
    list1 = f.readlines()

list1 = list1[:13] + links

with open(
    YML,
    "w+",
    encoding="UTF-8"
) as f:
    f.writelines(list1)
