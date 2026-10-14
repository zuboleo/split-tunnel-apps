import json
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

    review_chunk = re.search(
        r'href=["\'](/catalog/_next/static/chunks/reviewsView\.[^"\']+\.js)["\']',
        page,
        flags=re.I,
    )
    assert review_chunk, "reviewsView chunk not found"
    chunk_url = "https://www.rustore.ru" + review_chunk.group(1)
    text = session.get(chunk_url, timeout=20).text
    print("\nCHUNK", chunk_url, "LEN", len(text))

    print("\n=== API STRING LITERALS ===")
    strings = sorted(set(re.findall(r'["\']([^"\']{1,500})["\']', text)))
    for value in strings:
        low = value.lower()
        if any(token in low for token in ("feedback", "review", "showcase", "comment", "rating")):
            print("STR", value)

    print("\n=== FEEDBACK CONTEXT ===")
    for pattern in (
        r"/v1/showcase/web/feedbacks",
        r"WEB_GATEWAY_URL",
        r"packageName",
        r"continuation",
        r"sortBy",
        r"comments",
    ):
        print("PATTERN", pattern)
        for idx, match in enumerate(re.finditer(pattern, text, flags=re.I)):
            print("CTX", text[max(0, match.start()-1000):match.end()+1800])
            if idx >= 15:
                break

    # Extract likely relative HTTP endpoints from the minified chunk.
    print("\n=== LIKELY ENDPOINTS ===")
    endpoints = sorted(set(re.findall(r'["\'](/v\d+/[^"\']+)["\']', text)))
    for endpoint in endpoints:
        print("ENDPOINT", endpoint)

    # The page itself exposes runtime env config; print any gateway URL values.
    print("\n=== PAGE GATEWAY VALUES ===")
    for m in re.finditer(r'(?:WEB_GATEWAY_URL|SERVER_WEB_GATEWAY_URL)', page):
        print("PAGE_GATEWAY", page[max(0, m.start()-500):m.end()+800])

    # Print structured data top-level app identity to correlate any API IDs.
    print("\n=== PAGE IDS ===")
    for key in ("packageName", "appId", "appIdInt", "publicId", "developerId"):
        values = sorted(set(re.findall(rf'["\']{key}["\']\s*:\s*["\']?([^,}}"\']+)', page)))
        if values:
            print("ID", key, values[:20])

    assert False, "intentional debug failure"
