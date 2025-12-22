Kino — сервис для совместного просмотра видео (MVP)

Простой проект для совместного (synchronized) просмотра видео несколькими пользователями.

Основные части:
- Backend: FastAPI
- Асинхронные фоновые задачи: dramatiq (Redis broker)
- DB: PostgreSQL (по-умолчанию в docker-compose). Для локальной разработки можно использовать SQLite.
- Storage: MinIO (S3-совместимое) — используется для хранения видео фрагментов и исходных файлов
- WebSocket-based синхронизация playback состояний

Что есть в этом репозитории (MVP):
- API для создания комнаты и загрузки видео
- Простой веб-интерфейс (HTML/JS) для просмотра и синхронизации действий (play/pause/seek)
- Фоновые задачи (dramatiq) — placeholder для разделения/транскодирования (ffmpeg)
- Пре‑загрузка sample видео при старте (если MinIO доступен) — UI сразу показывает несколько видео для выбора
- Docker Compose конфиг с app, worker, redis, db и MinIO (S3-совместимое хранилище)

Поддержка persistence:
- MinIO хранит данные в именованном volume `minio-data` (docker-compose) — загруженные видео сохраняются между перезапусками контейнеров.

Быстрый старт (требуется Docker):

1. Клонируйте репозиторий и запустите контейнеры

```bash
docker compose up --build
```

2. App будет доступно по http://localhost:8000

3. Откройте http://localhost:8000 в нескольких вкладках и создайте комнату для совместного просмотра.

Запуск локально без Docker (venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Запуск worker'а (dramatiq):

```bash
dramatiq app.tasks
```

Тесты:

```bash
pytest -q
```

Документация API доступна по /docs после старта `uvicorn`.
