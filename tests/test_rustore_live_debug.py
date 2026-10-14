import html
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
    response = session.get(review_url, timeout=20)
    response.raise_for_status()
    page = response.text

    print("\n=== REVIEW HTML VPN CONTEXT ===")
    upper = page.upper()
    positions = []
    for token in ("ВПН", "VPN", "ОТКЛЮЧ"):
        start = 0
        while True:
            index = upper.find(token, start)
            if index < 0:
                break
            positions.append(index)
            start = index + len(token)
    for index in sorted(set(positions))[:20]:
        fragment = html.unescape(page[max(0, index - 500):index + 1200])
        print("HTML_CTX", re.sub(r"\\s+", " ", fragment))

    script_urls = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', page, flags=re.I):
        if src.startswith("/"):
            src = "https://www.rustore.ru" + src
        if src.startswith("http"):
            script_urls.append(src)

    review_bundles = [url for url in script_urls if "/reviews/page-" in url]
    print("\n=== REVIEW BUNDLES ===", review_bundles)
    assert review_bundles, "reviews bundle not found"

    text = session.get(review_bundles[-1], timeout=20).text
    print("BUNDLE_LEN", len(text))

    print("\n=== FEEDBACK PATHS ===")
    paths = sorted(set(re.findall(r'["\']([^"\']*(?:feedback|review)[^"\']*)["\']', text, flags=re.I)))
    for value in paths:
        if len(value) < 700:
            print("PATH", value)

    print("\n=== SHOWCASE CONTEXT ===")
    for pattern in (
        r"/v1/showcase/web/feedbacks",
        r"WEB_GATEWAY_URL",
        r"feedbacks/comments",
        r"sortBy",
        r"continuation",
    ):
        print("PATTERN", pattern)
        count = 0
        for match in re.finditer(pattern, text, flags=re.I):
            fragment = text[max(0, match.start() - 700):match.end() + 1300]
            print("CTX", re.sub(r"\\s+", " ", fragment))
            count += 1
            if count >= 12:
                break

    # Search all page bundles for where WEB_GATEWAY_URL is actually defined.
    print("\n=== GATEWAY DEFINITION ===")
    for src in script_urls:
        try:
            bundle = session.get(src, timeout=20).text
        except Exception:
            continue
        if "WEB_GATEWAY_URL" not in bundle:
            continue
        for match in re.finditer(r"WEB_GATEWAY_URL", bundle):
            fragment = bundle[max(0, match.start() - 800):match.end() + 1400]
            print("GATEWAY_SRC", src)
            print("GATEWAY_CTX", re.sub(r"\\s+", " ", fragment))

    assert False, "intentional debug failure; inspect captured stdout"
