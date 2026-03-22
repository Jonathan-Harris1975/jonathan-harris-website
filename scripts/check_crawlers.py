#!/usr/bin/env python3
from pathlib import Path

from ebook_pipeline import CRAWLER_CHECKSUMS_PATH, EXTERNAL_CRAWLER_FILES, ROOT, build_crawler_checksums, build_llms_txt, build_robots_txt, build_sitemap_xml, load_master, read_json


def main() -> int:
    books = load_master()
    expected_files = {
        ROOT / "robots.txt": build_robots_txt(),
        ROOT / "sitemap.xml": build_sitemap_xml(books),
        ROOT / "llms.txt": build_llms_txt(books),
    }
    for path, expected in expected_files.items():
        if not path.exists():
            print(f"Crawler check failed: missing {path.relative_to(ROOT)}")
            return 1
        if path.read_text(encoding="utf-8") != expected:
            print(f"Crawler check failed: generated snapshot drift in {path.relative_to(ROOT)}")
            return 1

    checksum_payload = read_json(CRAWLER_CHECKSUMS_PATH, default={}) or {}
    expected_checksums = build_crawler_checksums(books).get("files", {})
    actual_checksums = checksum_payload.get("files", {})
    if set(expected_checksums.keys()) != set(actual_checksums.keys()):
        print("Crawler check failed: config/crawler-checksums.json is incomplete")
        return 1
    for name, payload in expected_checksums.items():
        if actual_checksums.get(name, {}).get("sha256") != payload.get("sha256"):
            print(f"Crawler check failed: checksum drift in {name}")
            return 1

    redirects_text = (ROOT / "_redirects").read_text(encoding="utf-8")
    for source, url in [("/robots.txt", EXTERNAL_CRAWLER_FILES["robots"]), ("/sitemap.xml", EXTERNAL_CRAWLER_FILES["sitemap"]), ("/llms.txt", EXTERNAL_CRAWLER_FILES["llms"])] :
        if url not in redirects_text or source not in redirects_text:
            print(f"Crawler check failed: _redirects is missing the governed external rule for {source}")
            return 1

    print("Crawler file check passed: repo snapshots are generated, versioned, and matched to the governed external publication targets.")
    for name, url in EXTERNAL_CRAWLER_FILES.items():
        print(f"- {name}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
