# Дополнительные профили

[Основной запуск и API](../README.md).

## Private: SQLite и вход

```bash
CALENDAR_PROFILE=private .venv/bin/python manage.py migrate
CALENDAR_PROFILE=private .venv/bin/python manage.py createsuperuser
CALENDAR_PROFILE=private .venv/bin/python manage.py runserver localhost:8000
```

Откройте http://localhost:8000/login/. Используется отдельная база `db.sqlite3`.
Пользователь видит только собственные серии. Для POST требуется CSRF-токен; браузерный интерфейс передаёт его автоматически.

Серии без владельца скрыты. Для назначения существующих серий сначала выполните просмотр, затем примените изменение:

```bash
CALENDAR_PROFILE=private .venv/bin/python manage.py assign_series USERNAME 1 2
CALENDAR_PROFILE=private .venv/bin/python manage.py assign_series USERNAME 1 2 --apply
```

## Production: PostgreSQL и Gunicorn

Создайте базу PostgreSQL и задайте переменные по [.env.example](../.env.example).
Обязательны `CALENDAR_PROFILE=production`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`.
`POSTGRES_PORT` по умолчанию равен `5432`. Django не загружает `.env` автоматически: экспортируйте переменные через окружение процесса.

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

Статика обслуживается WhiteNoise. Доступ и CSRF работают как в `private`.
HTTPS включён по умолчанию; TLS должен завершаться на reverse proxy.
`CALENDAR_TRUST_PROXY_HTTPS=1` разрешает доверять `X-Forwarded-Proto` только за proxy, который удаляет входящий заголовок клиента и устанавливает собственный.
`CALENDAR_HTTPS_ENABLED=0` предназначен для локальной HTTP-проверки. Оба параметра принимают только `0` или `1`.
Публичное развёртывание требует настройки TLS, секретов, резервного копирования и мониторинга на целевом сервере.

## Локальный PostgreSQL для тестов

Профиль Compose `postgres` запускает только базу; приложение выполняется из виртуального окружения.
Docker нужен только для этого варианта, если PostgreSQL не установлен отдельно.

```bash
docker compose --profile postgres up -d --wait postgres
```

Экспортируйте переменные production-профиля из раздела выше; для локальной базы используйте:

```bash
export POSTGRES_DB=calendar POSTGRES_USER=calendar
export POSTGRES_PASSWORD=local-test-only POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py test events
```

Пользователю PostgreSQL для запуска тестов нужно право создания тестовой базы.
Завершение работы контейнера: `docker compose --profile postgres down`.
