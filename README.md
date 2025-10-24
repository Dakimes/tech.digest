# scisource.ru — Технологический радар и дайджесты

## Как развернуть
1) Создайте репозиторий и включите GitHub Pages (Source: GitHub Actions).
2) Добавьте DNS CNAME: `scisource.ru -> <username>.github.io`.
3) Закоммитьте содержимое этого архива в `main` — сайт опубликуется автоматически.

## Структура
- `index.html` — главная (радар + доска).
- `ekg/index.html` — страница технологии «Платформы корпоративных графов знаний».
- `assets/logo.png` — логотип.
- `assets/regional-analytics.png` — региональная аналитика.
- `CNAME` — домен `scisource.ru`.
- `.github/workflows/pages.yml` — автодеплой на Pages.

## Добавление новой технологии
1) Создайте папку `/<slug>/index.html`.
2) На главной добавьте объект в `technologies[]` с `slug` и `link: \`/${slug}/\``.
