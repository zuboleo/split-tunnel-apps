# split-tunnel-apps

Автоматически обновляемый список Android-приложений, для которых есть подтверждения проблем при активном VPN: предупреждения, требования отключить VPN или ограничения доступа.

Проект запускается раз в сутки через GitHub Actions и публикует компактный список Android package ID для split tunneling.

## Готовый список

Файл:

```text
public/app_ids.txt
```

Формат — одна строка с package ID через запятую:

```text
com.example.one,com.example.two,ru.example.app
```

После публикации репозитория файл можно использовать напрямую:

```text
https://raw.githubusercontent.com/OWNER/REPO/main/public/app_ids.txt
```

Либо через GitHub Pages:

```text
https://OWNER.github.io/REPO/app_ids.txt
```

## Как это работает

Ежедневный запуск:

1. Ищет новые публичные упоминания проблем приложений с VPN.
2. Проверяет найденные страницы и контекст упоминания.
3. Извлекает или определяет Android package ID.
4. Объединяет независимые подтверждения и отбрасывает дубли.
5. Обновляет `data/apps.json`, `data/evidence.json` и `public/app_ids.txt`.

Поддерживаются отдельные адаптеры магазинов приложений в `scraper/stores/`.

## Структура

```text
scraper/
  discovery/          поиск новых ссылок
  stores/             адаптеры магазинов приложений
  article_parser.py   разбор найденных страниц
  orchestrator.py     основной pipeline
  dataset.py          хранение состояния и генерация списка

data/
  seed.json           начальный проверенный набор
  apps.json           текущее состояние
  evidence.json       найденные подтверждения
  allowlist.txt       ручное принудительное добавление
  denylist.txt        ручные исключения
public/
  app_ids.txt         список для внешнего использования
  status.json         состояние последнего обновления
```

## Локальный запуск

```bash
python -m pip install -r requirements.txt
pytest -q
python -m scraper.main
```

Проверка без сетевых запросов:

```bash
python -m scraper.main --offline
```

Ограниченный сетевой запуск:

```bash
python -m scraper.main --max-queries 5 --no-deep-store
```

## Автообновление

`.github/workflows/update.yml` запускается раз в сутки и коммитит изменившиеся файлы из `data/` и `public/` обратно в репозиторий.

Для GitHub Pages включите **Settings → Pages → Source: GitHub Actions**. Workflow публикации уже находится в `.github/workflows/pages.yml`.
