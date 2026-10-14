from scraper.models import SearchHit
from scraper.stores.google_play import GooglePlayParser
from scraper.stores.huawei import HuaweiAppGalleryParser
from scraper.stores.rustore import RuStoreParser
from scraper.stores.samsung import SamsungStoreParser


def hit(url: str) -> SearchHit:
    return SearchHit("test", "q", "App", url, "отключите VPN")


def test_google_play_id() -> None:
    p = GooglePlayParser()
    assert p.parse_hit(hit("https://play.google.com/store/apps/details?id=ru.dns.shop.android")).package_id == "ru.dns.shop.android"


def test_rustore_id() -> None:
    p = RuStoreParser()
    assert p.parse_hit(hit("https://www.rustore.ru/catalog/app/ru.mosgorpass/reviews")).package_id == "ru.mosgorpass"


def test_samsung_id() -> None:
    p = SamsungStoreParser()
    assert p.parse_hit(hit("https://galaxystore.samsung.com/detail/com.example.app?langCd=ru")).package_id == "com.example.app"


def test_huawei_pkg_name() -> None:
    p = HuaweiAppGalleryParser()
    assert p.parse_hit(hit("https://appgallery.cloud.huawei.com/appDetail?pkgName=com.example.app")).package_id == "com.example.app"
