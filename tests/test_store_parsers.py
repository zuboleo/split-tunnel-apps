from scraper.models import SearchHit
from scraper.stores.google_play import GooglePlayParser
from scraper.stores.huawei import HuaweiAppGalleryParser
from scraper.stores.rustore import RuStoreParser
from scraper.stores.samsung import SamsungStoreParser


def hit(url: str) -> SearchHit:
    return SearchHit("test", "q", "App", url, "отключите VPN")


class FakeSearch:
    def search(self, query: str, limit: int = 10):
        return [
            SearchHit(
                "test",
                query,
                "32 отзыва о приложении Desport: интернет-магазин в RuStore",
                "https://www.rustore.ru/catalog/app/ru.desport.android/reviews",
                "Приложение не работает. Требует отключить VPN, но он у меня не включен.",
            )
        ]


def test_google_play_id() -> None:
    p = GooglePlayParser()
    assert p.parse_hit(hit("https://play.google.com/store/apps/details?id=ru.dns.shop.android")).package_id == "ru.dns.shop.android"


def test_rustore_id() -> None:
    p = RuStoreParser()
    assert p.parse_hit(hit("https://www.rustore.ru/catalog/app/ru.mosgorpass/reviews")).package_id == "ru.mosgorpass"


def test_rustore_catalog_link_extraction() -> None:
    p = RuStoreParser()
    rows = p._collect_app_links(
        "https://www.rustore.ru/catalog/all",
        '<a href="/catalog/app/ru.example.app">Example App</a>',
    )
    assert rows == [("ru.example.app", "Example App")]


def test_rustore_indexed_review_scan_finds_explicit_block() -> None:
    evidence = RuStoreParser().scan_indexed_reviews(FakeSearch(), limit_per_phrase=1)
    assert evidence
    item = evidence[0]
    assert item.package_id == "ru.desport.android"
    assert item.verdict == "positive"
    assert item.confidence >= 0.9


def test_samsung_id() -> None:
    p = SamsungStoreParser()
    assert p.parse_hit(hit("https://galaxystore.samsung.com/detail/com.example.app?langCd=ru")).package_id == "com.example.app"


def test_samsung_legacy_query_id() -> None:
    p = SamsungStoreParser()
    url = "https://apps.samsung.com/appquery/appDetail.as?appId=com.example.legacy"
    assert p.matches(url)
    assert p.parse_hit(hit(url)).package_id == "com.example.legacy"


def test_samsung_embedded_package() -> None:
    p = SamsungStoreParser()
    url = "https://apps.samsung.com/appquery/appDetail.as"
    parsed = p.parse_hit(hit(url), '<script>{"packageName":"com.example.embedded"}</script>')
    assert parsed.package_id == "com.example.embedded"


def test_huawei_pkg_name() -> None:
    p = HuaweiAppGalleryParser()
    assert p.parse_hit(hit("https://appgallery.cloud.huawei.com/appDetail?pkgName=com.example.app")).package_id == "com.example.app"


def test_huawei_package_path() -> None:
    p = HuaweiAppGalleryParser()
    assert p.parse_hit(hit("https://appgallery.huawei.com/app/com.example.path")).package_id == "com.example.path"


def test_huawei_cid_needs_metadata() -> None:
    p = HuaweiAppGalleryParser()
    url = "https://appgallery.huawei.com/app/C123456789"
    assert p.parse_hit(hit(url)).package_id is None
    parsed = p.parse_hit(hit(url), '<script>{"package":"com.example.fromjson"}</script>')
    assert parsed.package_id == "com.example.fromjson"
