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
    urls = [
        f"https://www.rustore.ru/catalog/app/{package}",
        f"https://www.rustore.ru/catalog/app/{package}/reviews",
        f"https://backapi.rustore.ru/applicationData/overallInfo/{package}",
    ]
    print("\n=== REQUESTS ===")
    pages = []
    for url in urls:
        headers = {"ruStoreVerCode": "110802"} if "backapi" in url else {}
        r = session.get(url, headers=headers, timeout=20, allow_redirects=True)
        print("URL", url)
        print("STATUS", r.status_code, "FINAL", r.url, "CT", r.headers.get("content-type"), "LEN", len(r.content))
        print("HAS_VPN", "VPN" in r.text.upper() or "ВПН" in r.text.upper())
        print("HEAD", re.sub(r"\\s+", " ", r.text[:400]))
        if "rustore.ru/catalog" in url and r.status_code == 200:
            pages.append(r.text)
        if "backapi" in url:
            try:
                data = r.json()
                print("JSON_KEYS", list(data)[:20])
                print("BODY_KEYS", list((data.get("body") or {}).keys())[:80] if isinstance(data, dict) else None)
                print("BODY_SAMPLE", json.dumps(data.get("body") if isinstance(data, dict) else data, ensure_ascii=False)[:2500])
            except Exception as exc:
                print("JSON_ERR", repr(exc))

    print("\n=== SCRIPT ASSETS ===")
    script_urls = []
    for page in pages:
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', page, flags=re.I):
            if src.startswith("/"):
                src = "https://www.rustore.ru" + src
            if src.startswith("http") and src not in script_urls:
                script_urls.append(src)
    print("SCRIPTS", len(script_urls))
    for src in script_urls[:30]:
        print("SCRIPT", src)

    needles = ("review", "feedback", "comment", "rating", "applicationData", "showcase")
    print("\n=== BUNDLE MATCHES ===")
    found = []
    for src in script_urls[:25]:
        try:
            r = session.get(src, timeout=20)
            if r.status_code != 200 or len(r.text) > 8_000_000:
                continue
            text = r.text
            if not any(n.lower() in text.lower() for n in needles):
                continue
            # Print URL-like/path-like strings near interesting words.
            for m in re.finditer(r"(?i)(review|feedback|comment|rating|applicationData|showcase)", text):
                frag = text[max(0, m.start()-180):m.end()+260]
                frag = re.sub(r"\\s+", " ", frag)
                key = frag[:500]
                if key not in found:
                    found.append(key)
                if len(found) >= 80:
                    break
            if len(found) >= 80:
                break
        except Exception as exc:
            print("SCRIPT_ERR", src, repr(exc))
    for frag in found:
        print("MATCH", frag)

    assert False, "intentional debug failure; inspect captured stdout"
