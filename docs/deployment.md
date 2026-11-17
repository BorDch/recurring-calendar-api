# Развёртывание и профили запуска

Вернуться к [README](../README.md).

## Профили запуска

Профиль выбирается переменной `CALENDAR_PROFILE`. По умолчанию действует `local`: база `db.local.sqlite3`, пять исходных API-маршрутов доступны без входа, POST работает с обычным `curl`, сервер слушает `localhost:8000`. Защищённый профиль `private` использует `db.sqlite3`, сеансовый вход Django и CSRF. Старые серии без владельца скрыты до явного назначения.

```bash
# Локальный профиль
CALENDAR_PROFILE=local .venv/bin/python manage.py migrate
CALENDAR_PROFILE=local .venv/bin/python manage.py runserver localhost:8000

# Защищённый профиль (в другом запуске)
CALENDAR_PROFILE=private .venv/bin/python manage.py migrate
CALENDAR_PROFILE=private .venv/bin/python manage.py createsuperuser
CALENDAR_PROFILE=private .venv/bin/python manage.py runserver localhost:8000
```

В защищённом профиле откройте `http://localhost:8000/login/`. Выход доступен кнопкой календаря (POST `/logout/`). Для назначения старых серий сначала просмотрите список: `CALENDAR_PROFILE=private .venv/bin/python manage.py assign_series USERNAME 1 2`, затем повторите с `--apply`. Команда принимает только существующие серии без владельца и не меняет исключения или дату обрезания.

## Доступ и CSRF

В профиле `private` календарь и все API-маршруты требуют входа. Серии доступны только своему владельцу; чужой id при изменении даёт `404`. Браузер передаёт CSRF-токен в заголовке `X-CSRFToken` для POST. В профиле `local` сохраняется прежний договор API без входа и CSRF для локального задания.

## Production (отдельный профиль)

Production использует PostgreSQL, вход Django и изоляцию серий по владельцу. Старые серии с `owner=NULL` скрыты; назначайте их через `assign_series` после проверки владельцев. Для публичного сервера установите переменные из `.env.example` в process manager или секретах хостинга. Django **не читает `.env` сам**. Для ручной локальной проверки можно выполнить `set -a; source .env; set +a`, предварительно создав свой `.env` (он игнорируется Git). Пример не содержит рабочих секретов.

Обязательные переменные: `CALENDAR_PROFILE=production`, `SECRET_KEY` (длинный случайный ключ), `ALLOWED_HOSTS` (список имён через запятую), `CSRF_TRUSTED_ORIGINS` (полные HTTPS origins через запятую), `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`. `POSTGRES_PORT` по умолчанию `5432`. При отсутствии обязательных значений запуск завершается с сообщением о переменной. `CALENDAR_TRUST_PROXY_HTTPS=1` ставьте только если доверенный reverse proxy удаляет присланный клиентом `X-Forwarded-Proto` и выставляет его сам. Без этого Django не доверяет forwarded-заголовку. `CALENDAR_HTTPS_ENABLED=0` разрешён только для локальной HTTP-проверки production-конфигурации; по умолчанию редирект на HTTPS и secure cookies включены. Обе переменные принимают только `0` или `1`; пустые и другие значения вызывают ошибку с названием переменной. По умолчанию HTTPS включён, доверие proxy выключено. TLS завершается на reverse proxy, который передаёт трафик Gunicorn по закрытому каналу. HSTS действует только для текущего хоста, без preload и includeSubDomains.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Экспортируйте переменные окружения перед следующими командами.
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

WhiteNoise обслуживает собранные статические файлы из `staticfiles/` через Gunicorn. Запускайте `collectstatic` после каждого обновления ресурсов. `psycopg[binary]` — PostgreSQL-драйвер, `gunicorn` — WSGI-сервер, `whitenoise` — обслуживание статики. Для проверки с локальным контейнером: `docker compose up -d --wait postgres`, затем используйте `POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_PASSWORD=local-test-only`; не используйте этот пароль публично. При HTTP-проверке также задайте `CALENDAR_HTTPS_ENABLED=0`, `ALLOWED_HOSTS=localhost,127.0.0.1` и `CSRF_TRUSTED_ORIGINS=http://localhost:8000`.

Резервное копирование и проверка восстановления в **отдельную пустую тестовую базу** (подставьте свои соединения, не восстанавливайте поверх пользовательской базы):

```bash
pg_dump -Fc -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f calendar.dump
createdb -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" calendar_restore_test
pg_restore -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d calendar_restore_test --no-owner calendar.dump
```

Остаются задачи публичного развёртывания: настроить и проверить TLS, DNS, секреты, мониторинг, регулярные резервные копии и восстановление, лимиты ресурсов и обновления безопасности на целевом хостинге. Успешные тесты сами по себе не подтверждают готовность публичного сервера.
