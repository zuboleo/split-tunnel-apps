import re

import requests


def test_debug_rustore_delivery():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
    })
    package = "ru.desport.android"
    review_url = f"https://www.rustore.ru/catalog/app/{package}/reviews"
    page = session.get(review_url, timeout=20).text

    script_urls = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', page, flags=re.I):
        if src.startswith("/"):
            src = "https://www.rustore.ru" + src
        if src.startswith("http"):
            script_urls.append(src)

    chunk_ids = (6214, 883, 8331, 9874, 6290, 5125, 73918)
    print("\n=== PAGE REFERENCES ===")
    for cid in chunk_ids:
        for m in re.finditer(str(cid), page):
            print("PAGE_ID", cid, page[max(0, m.start()-300):m.end()+500])
            break

    print("\n=== SCRIPT REFERENCES ===")
    loaded = {}
    for src in script_urls:
        text = session.get(src, timeout=20).text
        loaded[src] = text
        hits = [cid for cid in chunk_ids if str(cid) in text]
        if hits:
            print("SRC", src, "IDS", hits)
            for cid in hits:
                m = re.search(str(cid), text)
                if m:
                    print("CTX", cid, text[max(0, m.start()-500):m.end()+1000])

    print("\n=== CHUNK FILENAMES FROM HTML/RUNTIME ===")
    all_text = page + "\n" + "\n".join(loaded.values())
    for cid in chunk_ids:
        # Next/webpack forms seen in runtime: 6214:"hash" or {6214:"hash"}
        pats = [
            rf'{cid}["\']?\s*:\s*["\']([^"\']+)["\']',
            rf'["\']{cid}["\']\s*:\s*["\']([^"\']+)["\']',
            rf'{cid}[^\n]{{0,120}}?([0-9a-f]{{8,}})\.js',
        ]
        for pat in pats:
            matches = re.findall(pat, all_text)
            if matches:
                print("MAP", cid, matches[:20])

    print("\n=== ALL STATIC CHUNK URLS IN PAGE ===")
    urls = sorted(set(re.findall(r'(/catalog/_next/static/chunks/[^"\']+?\.js)', page)))
    for url in urls:
        print("STATIC", "https://www.rustore.ru" + url)

    # Runtime often contains a function that maps numeric chunk ids to hashed filenames.
    print("\n=== WEBPACK MAPPER ===")
    for src, text in loaded.items():
        if "webpack-" not in src:
            continue
        for cid in chunk_ids:
            for m in re.finditer(str(cid), text):
                print("WEBPACK", cid, text[max(0, m.start()-1200):m.end()+1600])
                break

    assert False, "intentional debug failure"
