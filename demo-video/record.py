#!/usr/bin/env python3
"""Record the real local Django calendar UI with a fresh disposable database."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'demo-video' / 'artifacts'
BASE = 'http://127.0.0.1:8000'
ORIGINAL = 'Еженедельный осмотр линии №2'
RENAMED = 'Повторный осмотр линии №2'
DAYS = (2, 9, 16, 23, 30)


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def port_available():
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', 8000))
        except OSError as exc:
            raise RuntimeError('localhost:8000 is occupied; inspect it and stop only your own process') from exc


def ready(url=BASE + '/'):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError('Django server did not become ready')


def api_day(day):
    with urllib.request.urlopen(f'{BASE}/events/2026/11/{day}/', timeout=5) as response:
        assert response.status == 200
        return json.load(response)


def wait_calendar(page):
    page.locator('#month-grid .day-cell').first.wait_for()
    page.wait_for_function("!document.querySelector('#status-line').classList.contains('loading') && document.querySelector('#status-message').textContent === ''")


def navigate_november(page):
    year, month = page.evaluate('() => { const d = new Date(); return [d.getUTCFullYear(), d.getUTCMonth() + 1] }')
    offset = (2026 - year) * 12 + (11 - month)
    if abs(offset) > 240:
        raise RuntimeError(f'Unexpected browser UTC date: {year}-{month}')
    for _ in range(abs(offset)):
        page.locator('#next-month' if offset > 0 else '#prev-month').click()
        wait_calendar(page)
    assert page.locator('#month-title').inner_text() == 'Ноябрь 2026'
    assert page.locator('#month-grid .day-cell').count() == 42  # November 1 is Sunday; Nov 30 is sixth row.


def cell(page, day):
    return page.locator(f'.day-cell:has(.day-number[aria-label="{day} ноября 2026"])')


def assert_visible_days(page, expected):
    for day in DAYS:
        events = cell(page, day).locator('.cell-event')
        name = expected.get(day)
        assert events.count() == (1 if name else 0), f'{day} November: event count mismatch'
        if name:
            assert name in events.first.get_attribute('title'), f'{day} November: name mismatch'


def click_event(page, day):
    cell(page, day).locator('.cell-event').click()
    assert page.locator('#selected-date-title').inner_text() == f'{day} ноября'
    page.locator('#event-detail').wait_for(state='visible')


def capture(page, folder, label):
    page.screenshot(path=str(folder / f'{label}.png'))
    geometry = page.evaluate('''() => ({
        viewport: [innerWidth, innerHeight],
        document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
        grid: (() => {const r=document.querySelector('#month-grid').getBoundingClientRect();return [r.x,r.y,r.width,r.height,r.bottom]})(),
        lastRow: (() => {const r=document.querySelectorAll('.day-cell')[35].getBoundingClientRect();return [r.y,r.bottom]})(),
        font: getComputedStyle(document.querySelector('.cell-event') || document.querySelector('#month-title')).fontSize
    })''')
    assert geometry['viewport'] == [1920, 1080]
    assert geometry['document'][0] <= 1920 and geometry['grid'][4] <= 1080, geometry
    return geometry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['trial', 'full'])
    args = parser.parse_args()
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str((ROOT / 'demo-video' / '.browsers').resolve())
    port_available()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ARTIFACTS / f'{args.mode}-{stamp}'
    folder.mkdir(parents=True)
    db = folder / 'demo.sqlite3'
    env = os.environ.copy()
    env['CALENDAR_PROFILE'] = 'local'
    env['CALENDAR_DB'] = str(db.resolve())
    sha = run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True).stdout.strip()
    run([str(ROOT / '.venv/bin/python'), 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env,
        stdout=(folder / 'migrate.log').open('w'), stderr=subprocess.STDOUT)
    server_log = (folder / 'server.log').open('w')
    server = subprocess.Popen([str(ROOT / '.venv/bin/python'), 'manage.py', 'runserver', '--noreload', '127.0.0.1:8000'],
                              cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT)
    result = {'mode': args.mode, 'source_sha': sha, 'db': str(db), 'profile': 'local', 'viewport': [1920, 1080],
              'browser': None, 'playwright': None, 'checkpoints': {}, 'api': {}, 'post_responses': []}
    context = None
    browser = None
    try:
        ready()
        from importlib.metadata import version
        result['playwright'] = version('playwright')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            result['browser'] = browser.version
            context = browser.new_context(viewport={'width': 1920, 'height': 1080},
                screen={'width': 1920, 'height': 1080}, device_scale_factor=1,
                record_video_dir=str(folder), record_video_size={'width': 1920, 'height': 1080},
                locale='ru-RU', timezone_id='UTC')
            page = context.new_page()
            page.on('response', lambda response: result['post_responses'].append({'url': response.url, 'status': response.status})
                    if response.request.method == 'POST' and response.url.startswith(BASE) else None)
            page.goto(BASE, wait_until='domcontentloaded')
            wait_calendar(page)
            navigate_november(page)
            result['checkpoints']['opening'] = capture(page, folder, 'opening')
            start = time.monotonic()
            marks = {}
            def mark(name):
                marks[name] = round(time.monotonic() - start, 2)
            mark('opening')
            if args.mode == 'trial':
                page.wait_for_timeout(3500)
                page.locator('#create-button').click()
                page.locator('#event-dialog').wait_for(state='visible')
                result['checkpoints']['trial_form'] = capture(page, folder, 'trial_form')
                mark('trial_form')
                page.wait_for_timeout(4000)
                page.locator('#event-dialog [data-close]').first.click()
                page.wait_for_timeout(4500)
            else:
                page.wait_for_timeout(2200)
                page.locator('#create-button').click()
                page.locator('#event-dialog').wait_for(state='visible')
                page.locator('#event-name').fill(ORIGINAL)
                page.locator('#event-date').fill('2026-11-02')
                page.locator('#event-time').fill('09:00')
                page.locator('#event-repeat').select_option('weekly')
                result['checkpoints']['create_form'] = capture(page, folder, 'create_form')
                mark('create_form')
                page.wait_for_timeout(1600)
                page.locator('#save-event').click()
                page.locator('#event-dialog').wait_for(state='hidden')
                wait_calendar(page)
                assert_visible_days(page, {day: ORIGINAL for day in DAYS})
                result['checkpoints']['created'] = capture(page, folder, 'created')
                mark('created')
                page.wait_for_timeout(3200)
                click_event(page, 9)
                page.locator('#event-detail button').first.click()
                page.locator('#rename-dialog').wait_for(state='visible')
                page.locator('#rename-name').fill(RENAMED)
                result['checkpoints']['rename_form'] = capture(page, folder, 'rename_form')
                mark('rename_form')
                page.wait_for_timeout(1200)
                page.locator('#save-rename').click()
                page.locator('#rename-dialog').wait_for(state='hidden')
                wait_calendar(page)
                assert_visible_days(page, {2: ORIGINAL, 9: RENAMED, 16: ORIGINAL, 23: ORIGINAL, 30: ORIGINAL})
                result['checkpoints']['renamed'] = capture(page, folder, 'renamed')
                mark('renamed')
                page.wait_for_timeout(1600)
                cell(page, 2).locator('.day-number').click()
                assert ORIGINAL in page.locator('#day-list').inner_text()
                result['checkpoints']['original_2_after_rename'] = capture(page, folder, 'original_2_after_rename')
                page.wait_for_timeout(1500)
                cell(page, 16).locator('.day-number').click()
                assert ORIGINAL in page.locator('#day-list').inner_text()
                result['checkpoints']['original_16_after_rename'] = capture(page, folder, 'original_16_after_rename')
                page.wait_for_timeout(1500)
                click_event(page, 16)
                page.locator('#event-detail button').nth(1).click()
                page.locator('#delete-dialog').wait_for(state='visible')
                assert 'только это повторение' in page.locator('#delete-copy').inner_text()
                result['checkpoints']['delete_one_confirm'] = capture(page, folder, 'delete_one_confirm')
                mark('delete_one_confirm')
                page.wait_for_timeout(1300)
                page.locator('#confirm-delete').click()
                page.locator('#delete-dialog').wait_for(state='hidden')
                wait_calendar(page)
                assert_visible_days(page, {2: ORIGINAL, 9: RENAMED, 23: ORIGINAL, 30: ORIGINAL})
                result['checkpoints']['deleted_one'] = capture(page, folder, 'deleted_one')
                mark('deleted_one')
                page.wait_for_timeout(3000)
                click_event(page, 23)
                page.locator('#event-detail button').nth(2).click()
                page.locator('#delete-dialog').wait_for(state='visible')
                assert 'все последующие' in page.locator('#delete-copy').inner_text()
                result['checkpoints']['delete_next_confirm'] = capture(page, folder, 'delete_next_confirm')
                mark('delete_next_confirm')
                page.wait_for_timeout(1300)
                page.locator('#confirm-delete').click()
                page.locator('#delete-dialog').wait_for(state='hidden')
                wait_calendar(page)
                assert_visible_days(page, {2: ORIGINAL, 9: RENAMED})
                result['checkpoints']['deleted_next'] = capture(page, folder, 'deleted_next')
                mark('deleted_next')
                page.wait_for_timeout(3000)
                page.reload(wait_until='domcontentloaded')
                wait_calendar(page)
                navigate_november(page)
                assert_visible_days(page, {2: ORIGINAL, 9: RENAMED})
                cell(page, 9).locator('.day-number').click()
                result['checkpoints']['reloaded'] = capture(page, folder, 'reloaded')
                mark('reloaded')
                page.wait_for_timeout(1300)
                for day in DAYS:
                    cell(page, day).locator('.day-number').click()
                    expected = ORIGINAL if day == 2 else RENAMED if day == 9 else 'В этот день событий нет.'
                    assert expected in page.locator('#day-list').inner_text()
                    result['checkpoints'][f'after_reload_{day}'] = capture(page, folder, f'after_reload_{day}')
                    page.wait_for_timeout(1000)
                cell(page, 9).locator('.day-number').click()
                page.wait_for_timeout(1300)
                for day in DAYS:
                    result['api'][str(day)] = api_day(day)
                first, second = result['api']['2'], result['api']['9']
                assert len(first) == len(second) == 1
                assert first[0]['id'] == second[0]['id']
                assert first[0]['name'] == ORIGINAL and second[0]['name'] == RENAMED
                for day in (16, 23, 30):
                    assert result['api'][str(day)] == [], f'Unexpected API result on {day} November'
                mark('end')
            result['marks'] = marks
            video = page.video
            context.close()  # Playwright flushes and closes the raw recording here.
            context = None
            raw = folder / 'source.webm'
            shutil.move(video.path(), raw)
            result['raw_video'] = str(raw)
            browser.close()
            browser = None
        mp4 = folder / 'demo.mp4'
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(raw),
             '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', '-fps_mode', 'passthrough', str(mp4)])
        result['mp4'] = str(mp4)
        for key, path in [('raw_probe', raw), ('mp4_probe', mp4)]:
            result[key] = json.loads(run(['ffprobe', '-v', 'error', '-show_entries',
                'format=duration:stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames',
                '-of', 'json', str(path)], capture_output=True).stdout)
        (folder / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'folder': str(folder), 'raw': str(raw), 'mp4': str(mp4),
                          'marks': result['marks'], 'probe': result['mp4_probe'], 'api': result['api']}, ensure_ascii=False, indent=2))
    finally:
        if context:
            context.close()
        if browser:
            browser.close()
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        server_log.close()


if __name__ == '__main__':
    main()
