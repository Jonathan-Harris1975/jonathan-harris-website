"""
sync_podcast_episodes.py
Build-time script: fetches the Turing's Torch: AI Weekly RSS feed and
rewrites the recent-episodes section of podcast/index.html with live data.

Called from build.sh before deployment_ci.py.
"""

import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

RSS_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml"
HTML_FILE = Path("podcast/index.html")
LIMIT = 4


def fetch_episodes():
    with urllib.request.urlopen(RSS_URL, timeout=15) as response:
        tree = ET.parse(response)
    episodes = []
    for item in tree.findall(".//item")[:LIMIT]:
        title = item.findtext("title", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        link = item.findtext("link", "").strip()
        formatted_date = _format_date(pub_date)
        episodes.append(
            {
                "title": title,
                "link": link,
                "formatted_date": formatted_date,
            }
        )
    return episodes


def _format_date(pub_date_str):
    """Parse RFC 2822 pubDate and return 'DD Month YYYY', e.g. '10 April 2026'."""
    if not pub_date_str:
        return pub_date_str
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%-d %B %Y")
    except Exception:
        return pub_date_str


def build_html(episodes):
    rows = []
    for ep in episodes:
        t = html.escape(ep["title"])
        u = html.escape(ep["link"])
        d = ep["formatted_date"]
        rows.append(
            '<div class="podcast-episode-item">\n'
            '  <span aria-hidden="true" class="podcast-episode-item__num">&#9654;</span>\n'
            '  <div class="podcast-episode-item__body">\n'
            '    <div class="podcast-episode-item__title">\n'
            f'      <a href="{u}" rel="noopener noreferrer" target="_blank">{t}</a>\n'
            "    </div>\n"
            f'    <div class="podcast-episode-item__date">{d}</div>\n'
            "  </div>\n"
            "</div>"
        )
    return "\n".join(rows)


def inject(episodes):
    src = HTML_FILE.read_text(encoding="utf-8")

    # Match the opening <section> tag (preserving it and all its attributes),
    # then the <p class="ep-note"> paragraph (preserving it),
    # then the existing episode <div> blocks (replacing them),
    # then the closing </section> tag (preserving it).
    pattern = (
        r"(<section[^>]*podcast-episodes-static[^>]*>)"   # group 1: opening tag
        r"(\s*<p\s[^>]*ep-note[^>]*>.*?</p>)"             # group 2: ep-note paragraph
        r".*?"                                             # existing episode divs (discarded)
        r"(</section>)"                                    # group 3: closing tag
    )

    fresh_html = build_html(episodes)
    replacement = r"\1\2\n" + fresh_html + r"\n\3"

    new_src, count = re.subn(pattern, replacement, src, flags=re.DOTALL)

    if count == 0:
        print(
            "WARNING: Target section not found in podcast/index.html — file left unchanged.",
            file=sys.stderr,
        )
        return

    HTML_FILE.write_text(new_src, encoding="utf-8")
    print(f"Injected {len(episodes)} episodes into podcast/index.html.")


def main():
    try:
        episodes = fetch_episodes()
    except Exception as exc:
        print(
            f"WARNING: RSS fetch failed — {exc}. podcast/index.html left unchanged.",
            file=sys.stderr,
        )
        sys.exit(0)

    inject(episodes)


if __name__ == "__main__":
    main()
