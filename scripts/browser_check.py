"""Run the calendar flow in headless Firefox using a disposable SQLite database."""
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / 'screenshots'
SHOTS.mkdir(exist_ok=True)


def wait_for(driver, predicate, seconds=10):
    return WebDriverWait(driver, seconds).until(predicate)


def click(driver, selector):
    item = driver.find_element(By.CSS_SELECTOR, selector)
    driver.execute_script('arguments[0].scrollIntoView({block:"center"})', item)
    item.click()


def set_value(driver, selector, value):
    driver.execute_script('const el=document.querySelector(arguments[0]); el.value=arguments[1]; el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true}));', selector, value)


def day_event(driver, day):
    cell = driver.find_element(By.CSS_SELECTOR, f'.day-cell:has(.day-number[aria-label="{day} января 2027"])')
    cell.find_element(By.CSS_SELECTOR, '.cell-event').click()


with tempfile.TemporaryDirectory(prefix='recurring-browser-') as tmp:
    target = Path(tmp)
    for name in ('manage.py',): shutil.copy2(ROOT / name, target / name)
    for name in ('config', 'events'): shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns('__pycache__'))
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=target, check=True, stdout=subprocess.DEVNULL)
    port = 28000 + __import__('os').getpid() % 10000
    server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', '--noreload', f'127.0.0.1:{port}'], cwd=target, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    options = Options(); options.add_argument('-headless')
    driver = None
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1): break
            except OSError: time.sleep(.05)
        else: raise RuntimeError('server did not start')
        driver = webdriver.Firefox(options=options)
        driver.set_window_size(1440, 900)
        driver.get(f'http://127.0.0.1:{port}/')
        wait_for(driver, lambda d: len(d.find_elements(By.CSS_SELECTOR, '.day-cell')) >= 35)
        click(driver, '#create-button')
        wait_for(driver, lambda d: d.find_element(By.ID, 'event-dialog').get_attribute('open') is not None)
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        wait_for(driver, lambda d: d.find_element(By.ID, 'event-dialog').get_attribute('open') is None)
        assert driver.switch_to.active_element.get_attribute('id') == 'create-button'
        click(driver, '#create-button')
        driver.save_screenshot(str(SHOTS / 'event-form.png'))
        set_value(driver, '#event-name', 'Недельная встреча')
        set_value(driver, '#event-date', '2027-01-04')
        set_value(driver, '#event-time', '09:30')
        set_value(driver, '#event-repeat', 'weekly')
        click(driver, '#save-event')
        wait_for(driver, lambda d: 'Январь 2027' in d.find_element(By.ID, 'month-title').text and len(d.find_elements(By.CSS_SELECTOR, '.cell-event')) >= 4)
        day_event(driver, 11)
        click(driver, '#event-detail .detail-actions button:first-child')
        set_value(driver, '#rename-name', 'Встреча команды')
        click(driver, '#save-rename')
        wait_for(driver, lambda d: 'Встреча команды' in d.find_element(By.ID, 'day-list').text)
        day_event(driver, 18)
        click(driver, '#event-detail .detail-actions button:nth-child(2)')
        assert 'только это повторение' in driver.find_element(By.ID, 'delete-copy').text
        click(driver, '#confirm-delete')
        wait_for(driver, lambda d: 'В этот день событий нет' in d.find_element(By.ID, 'day-list').text)
        day_event(driver, 25)
        click(driver, '#event-detail .detail-actions button:nth-child(3)')
        assert 'все последующие' in driver.find_element(By.ID, 'delete-copy').text
        click(driver, '#confirm-delete')
        wait_for(driver, lambda d: 'В этот день событий нет' in d.find_element(By.ID, 'day-list').text)
        click(driver, '.day-cell:has(.day-number[aria-label="11 января 2027"]) .day-number')
        wait_for(driver, lambda d: 'Встреча команды' in d.find_element(By.ID, 'day-list').text)
        driver.execute_script('window.scrollTo(0, 0)')
        driver.get_full_page_screenshot_as_file(str(SHOTS / 'calendar-desktop.png'))
        driver.refresh()
        wait_for(driver, lambda d: len(d.find_elements(By.CSS_SELECTOR, '.day-cell')) >= 35)
        # Reload resets navigation to today; use the create dialog's date selection only for new events,
        # so navigate to January 2027 via the month controls.
        for _ in range(2): click(driver, '#next-month')
        wait_for(driver, lambda d: 'Январь 2027' in d.find_element(By.ID, 'month-title').text and len(d.find_elements(By.CSS_SELECTOR, '.cell-event')) > 0)
        click(driver, '.day-cell:has(.day-number[aria-label="11 января 2027"]) .day-number')
        assert 'Встреча команды' in driver.find_element(By.ID, 'day-list').text
        for day in (18, 25):
            click(driver, f'.day-cell:has(.day-number[aria-label="{day} января 2027"]) .day-number')
            assert 'В этот день событий нет' in driver.find_element(By.ID, 'day-list').text
        click(driver, '#next-month')
        wait_for(driver, lambda d: 'Февраль 2027' in d.find_element(By.ID, 'month-title').text)
        assert not driver.find_elements(By.CSS_SELECTOR, '.cell-event')
        driver.execute_script('window.__originalFetch=window.fetch; const realFetch=window.fetch.bind(window); let delay=true; window.fetch=(url, options)=>{if(delay && String(url).includes("/events/range/")){delay=false; return new Promise(resolve=>setTimeout(()=>resolve(realFetch(url, {...options, signal:undefined})), 600));} return realFetch(url, options)}')
        click(driver, '#prev-month')
        click(driver, '#next-month')
        wait_for(driver, lambda d: 'Февраль 2027' in d.find_element(By.ID, 'month-title').text)
        time.sleep(.8)
        assert 'Февраль 2027' in driver.find_element(By.ID, 'month-title').text
        assert not driver.find_elements(By.CSS_SELECTOR, '.cell-event')
        driver.set_window_size(390, 844)
        click(driver, '#prev-month')
        wait_for(driver, lambda d: 'Январь 2027' in d.find_element(By.ID, 'month-title').text)
        width = driver.execute_script('return [document.documentElement.scrollWidth, window.innerWidth]')
        assert width[0] <= width[1], f'horizontal overflow: {width}'
        driver.get_full_page_screenshot_as_file(str(SHOTS / 'calendar-mobile.png'))
        driver.execute_script('window.fetch=window.__originalFetch')
        # A failed refresh after a successful create must not look like a failed POST.
        driver.execute_script('window.__addPosts=0; let fail=true; window.fetch=(url, options)=>{if(String(url).endsWith("/add/") && options?.method==="POST") window.__addPosts++; if(fail && String(url).includes("/events/range/")){fail=false; return Promise.reject(new Error("offline"));} return window.__originalFetch(url, options)}')
        click(driver, '#create-button')
        set_value(driver, '#event-name', 'Проверка после сбоя чтения')
        set_value(driver, '#event-date', '2027-01-06')
        set_value(driver, '#event-time', '10:00')
        click(driver, '#save-event')
        wait_for(driver, lambda d: d.find_element(By.ID, 'event-dialog').get_attribute('open') is None)
        wait_for(driver, lambda d: 'Изменение сохранено, но календарь не удалось обновить' in d.find_element(By.ID, 'status-message').text)
        click(driver, '#retry-load')
        wait_for(driver, lambda d: 'Проверка после сбоя чтения' in d.find_element(By.ID, 'day-list').text)
        assert driver.find_element(By.ID, 'day-count').text == '1'
        assert driver.execute_script('return window.__addPosts') == 1
        driver.execute_script('window.fetch=window.__originalFetch; delete window.__addPosts')
        print('Firefox browser flow PASS; screenshots:', ', '.join(str(p) for p in sorted(SHOTS.glob('*.png'))))
    finally:
        if driver: driver.quit()
        server.terminate(); server.wait(timeout=5)
