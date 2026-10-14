# Scraper

- `discovery/` — поиск новых ссылок.
- `link_finder.py` — формирование и запуск поисковых запросов.
- `article_parser.py` — разбор найденных страниц.
- `evidence_classifier.py` — классификация VPN-сигналов.
- `stores/` — независимые адаптеры магазинов приложений.
- `package_resolver.py` — определение Android package ID.
- `seed.py` — загрузка начального проверенного набора.
- `dataset.py` — объединение подтверждений и генерация `app_ids.txt`.
- `orchestrator.py` — основной ежедневный pipeline.
