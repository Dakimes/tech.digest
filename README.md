# KG Tech Digest (GitHub Pages)

Статический сайт для публикации на GitHub Pages: главная (радар + доска) и страница дайджеста.

## Структура
```
.
├─ index.html                 # главная (ведёт на digest.html)
├─ digest.html                # текущий дайджест
├─ assets/
│  ├─ logo.png
│  └─ regional-analytics.png
└─ .github/workflows/pages.yml
```

## Деплой на GitHub Pages
1. Создайте репозиторий и включите **Pages** (Source: GitHub Actions).
2. Закоммитьте содержимое этой папки в корень `main`.
3. Workflow сам соберёт и опубликует сайт.

> Для продакшна можно заменить ссылку `SUBDOMAIN_URL` в `index.html` на реальный субдомен технологии.

