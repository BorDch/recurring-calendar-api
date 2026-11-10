# Проверка узкого viewport

Команда: `.venv/bin/python scripts/mobile_viewport_check.py` (Selenium, Firefox, WebDriver BiDi `browsingContext.setViewport`). Запуск создаёт временную копию проекта и новую SQLite-базу. Полные замеры каждого состояния: [`qa/mobile-viewport-metrics.jsonl`](qa/mobile-viewport-metrics.jsonl).

| Viewport | `window.innerWidth` | `document.documentElement.clientWidth` | `document.documentElement.scrollWidth` | Горизонтальное переполнение |
| ---: | ---: | ---: | ---: | --- |
| 360 × 740 | 360 | 348 | 348 | нет |
| 390 × 740 | 390 | 378 | 378 | нет |
| 360 × 360 | 360 | 348 | 348 | нет |
| 390 × 360 | 390 | 378 | 378 | нет |

Разница в 12 px между `innerWidth` и `clientWidth` вызвана вертикальной полосой прокрутки Firefox. Во всех измеренных состояниях `scrollWidth` равен `clientWidth`.

На обеих ширинах проверены пустой главный экран, создание события с длинным названием и повторением каждые 7 дней, ошибка периода `0` с сохранением введённых данных, день с шестью событиями и кнопкой «Ещё 4», панель дня, подтверждение удаления с названием, датой и областью действия, удаление одной даты и обновление панели. При высоте 360 px проверена возможность прокрутить диалог до каждого поля, сообщения об ошибке и кнопок. Для этого добавлено ограничение высоты и внутренняя прокрутка диалога.

Headless Firefox не открывает настоящую экранную клавиатуру. Высота 360 px моделирует уменьшенную доступную область, но не проверяет поведение клавиатуры конкретной мобильной ОС. Формат отображения нативных полей даты и времени зависит от языка браузера.

Скриншоты: [360 — главный экран](screenshots/calendar-360-main.png), [360 — ошибка формы](screenshots/calendar-360-form-error.png), [360 — короткая высота](screenshots/calendar-360-short-height.png), [360 — удаление](screenshots/calendar-360-delete.png), [390 — главный экран](screenshots/calendar-390-main.png), [390 — ошибка формы](screenshots/calendar-390-form-error.png), [390 — короткая высота](screenshots/calendar-390-short-height.png), [390 — удаление](screenshots/calendar-390-delete.png).
