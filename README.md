# Recurring Calendar API

Календарь повторяющихся событий на Django с REST API и браузерным интерфейсом.
Можно создать серию, посмотреть события дня, переименовать или отменить один повтор и удалить все повторы с выбранной даты.

![Календарь](docs/demo-calendar.png)

## Запуск

Требования: Python 3.14. Команды выполняются из корня проекта; пример для Linux/macOS.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver localhost:8000
```

Откройте http://localhost:8000/. По умолчанию используется SQLite, вход не требуется.
Для этого запуска Docker и Node.js не нужны. Данные сохраняются в `db.local.sqlite3`.

## API

| Метод | Маршрут | Действие | Успешный ответ |
| --- | --- | --- | --- |
| POST | `/add/` | Создать событие или серию | `201`, `{"id": 1}` |
| GET | `/events/{year}/{month}/{day}/` | Получить события дня | `200`, массив `{"name": "…", "id": 1}` |
| POST | `/update/{id}/{year}/{month}/{day}/` | Переименовать один повтор | `204` |
| POST | `/remove/{id}/{year}/{month}/{day}/` | Отменить один повтор | `204` |
| POST | `/remove-next/{id}/{year}/{month}/{day}/` | Удалить выбранный и следующие повторы | `204` |

Создание еженедельного события со 2 ноября 2026 года, 09:00 UTC:

```bash
curl -i -X POST http://localhost:8000/add/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"Осмотр линии","start_at":1793610000,"period":7}'

curl http://localhost:8000/events/2026/11/2/
```

Для переименования передайте `{"name":"Новое название"}` в JSON-теле запроса.
Оба удаления выполняются без тела. В URL используйте `id`, полученный при создании.
Полные схемы запросов, ответы и дополнительный маршрут диапазона для интерфейса: [OpenAPI](docs/openapi.yaml).

## Правила

- `start_at` — Unix timestamp в секундах; даты и время интерпретируются в UTC.
- `period` — положительное целое число дней; `null` означает одиночное событие.
- У всех повторов один ID серии. Повторы вычисляются при чтении.
- Переименование и отмена действуют только на выбранную дату.
- Обрезание серии исключает выбранную дату и все последующие.
- Пустой день возвращает `[]`; неверный ввод — `400`, недоступный повтор — `404`, неверный HTTP-метод — `405`.

## Устройство

`EventsSeries` хранит правило повторения и границу серии, `EventException` — переименование или отмену на конкретную дату.
Маршруты находятся в `config/urls.py`, модели и обработчики — в `events/models.py` и `events/views.py`, интерфейс — в `events/templates/` и `events/static/`.

Локальный профиль предназначен для проверки задания. Профили с входом, изоляцией данных пользователей и PostgreSQL описаны в [инструкции](docs/deployment.md).

## Проверки

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test events
CALENDAR_PROFILE=private .venv/bin/python manage.py test events
```

Тесты проверяют повторы, исключения, границы дат, валидацию, права доступа и конкурентные изменения.
Часть тестов выполняется только в соответствующем профиле. CI проверяет SQLite и PostgreSQL; PostgreSQL-тесты конкурентных изменений требуют PostgreSQL.

Для проверки форматирования (нужен Node.js только для Prettier):

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
npm ci
npm run format:web:check
```
