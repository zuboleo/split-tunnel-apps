import json

import requests


def test_debug_rustore_feedback_api():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        "Referer": "https://www.rustore.ru/",
        "Origin": "https://www.rustore.ru",
    })
    package = "ru.desport.android"
    url = f"https://web-api.rustore.ru/v1/showcase/web/feedbacks/comments/{package}"
    response = session.get(
        url,
        params={"limit": 30, "sortBy": "NEW_FIRST"},
        timeout=20,
    )
    print("\nSTATUS", response.status_code)
    print("FINAL_URL", response.url)
    print("CONTENT_TYPE", response.headers.get("content-type"))
    print("BODY", response.text[:12000])
    response.raise_for_status()

    payload = response.json()
    print("TOP_KEYS", list(payload) if isinstance(payload, dict) else type(payload).__name__)
    elements = payload.get("elements") if isinstance(payload, dict) else None
    print("ELEMENT_COUNT", len(elements or []))
    print("CONTINUATION", payload.get("continuation") if isinstance(payload, dict) else None)
    for index, item in enumerate((elements or [])[:5]):
        print("ELEMENT", index, json.dumps(item, ensure_ascii=False)[:8000])
        if isinstance(item, dict):
            print("ELEMENT_KEYS", index, list(item))

    assert False, "intentional debug failure; inspect payload schema"
