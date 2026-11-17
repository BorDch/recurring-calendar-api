# Запись демонстрации календаря

`record.py` запускает настоящий Django UI на `127.0.0.1:8000`, использует новый изолированный контекст Chromium и отдельную SQLite-базу для каждого прогона. Все изменения серии выполняются только кликами и вводом через UI. После перезагрузки скрипт делает независимые HTTP GET к API и проверяет результат. Профиль всегда `CALENDAR_PROFILE=local`, а `CALENDAR_DB` указывает на абсолютный путь новой базы в `artifacts/`.

## Подготовка

Из корня репозитория (Python 3.14, ffmpeg и ffprobe должны быть доступны):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 -m venv demo-video/.venv
demo-video/.venv/bin/python -m pip install -r demo-video/requirements-recording.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/demo-video/.browsers" demo-video/.venv/bin/python -m playwright install chromium
```

Playwright и Chromium размещаются отдельно от зависимостей Django. Папки `.venv`, `.browsers` и `artifacts` внутри `demo-video` исключены из Git. Системные настройки не меняются.

## Запуск

```bash
demo-video/.venv/bin/python demo-video/record.py trial
demo-video/.venv/bin/python demo-video/record.py full
```

Сначала используйте `trial`: его видео длится около 13 секунд. После просмотра кадра запустите `full`. Каждый вызов создаёт новую папку `demo-video/artifacts/{mode}-{timestamp}/` с новой базой, логом миграций, логом сервера, исходным `source.webm`, совместимым `demo.mp4`, контрольными PNG и `report.json`. Скрипт отказывается использовать занятый порт 8000. Он останавливает только сервер, который запустил сам, и закрывает браузерный контекст до чтения исходного видео.

Видео записывается браузерной библиотекой Playwright при viewport и размере записи 1920×1080. MP4 кодируется `libx264`, `yuv420p`, `-movflags +faststart` с сохранением кадровой частоты исходной записи (`-fps_mode passthrough`). Озвучка и субтитры не вшиты в кадр: [текст озвучивания](voiceover.md), [субтитры первого ролика](subtitles.srt). Таймкоды SRT соответствуют первому готовому ролику; у повторных прогонов они могут отличаться.

## Проверка первого ролика

См. [отчёт о записи](recording-report.md). Файлы находятся в `artifacts/full-20261117T124517061920Z/`. Для независимой проверки:

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_frames -of json demo-video/artifacts/full-20261117T124517061920Z/demo.mp4
```
