"""Exercise the calendar at exact 360/390 CSS-pixel Firefox BiDi viewports."""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "screenshots"
SHOTS.mkdir(exist_ok=True)
LONG_NAME = "Очень длинное название рабочей встречи с обсуждением планов, задач и итогов команды на следующую неделю"
MONTHS = {3: "марта", 4: "апреля"}


def wait(driver, callback):
    return WebDriverWait(driver, 10).until(callback)


def set_value(driver, selector, value):
    driver.execute_script(
        'const e=document.querySelector(arguments[0]); e.value=arguments[1]; e.dispatchEvent(new Event("input",{bubbles:true})); e.dispatchEvent(new Event("change",{bubbles:true}));',
        selector,
        value,
    )


def metrics(driver):
    return driver.execute_script(
        "return {innerWidth:window.innerWidth,clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,innerHeight:window.innerHeight}"
    )


def assert_width(driver, expected, stage):
    value = metrics(driver)
    assert value["innerWidth"] == expected and value["scrollWidth"] <= value["clientWidth"], (
        stage,
        value,
    )
    print(json.dumps({"width": expected, "stage": stage, **value}, ensure_ascii=False), flush=True)


def click(driver, selector):
    element = driver.find_element(By.CSS_SELECTOR, selector)
    driver.execute_script('arguments[0].scrollIntoView({block:"center"})', element)
    element.click()


with tempfile.TemporaryDirectory(prefix="recurring-mobile-") as tmp:
    target = Path(tmp)
    shutil.copy2(ROOT / "manage.py", target / "manage.py")
    for folder in ("config", "events"):
        shutil.copytree(
            ROOT / folder, target / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=target,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = 30000 + __import__("os").getpid() % 10000
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "--noreload", f"127.0.0.1:{port}"],
        cwd=target,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    options = Options()
    options.add_argument("-headless")
    options.set_capability("webSocketUrl", True)
    driver = None
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("server did not start")
        driver = webdriver.Firefox(options=options)
        driver.set_window_size(1000, 900)
        for width, month in ((360, 3), (390, 4)):
            driver.browsing_context.set_viewport(
                context=driver.current_window_handle, viewport={"width": width, "height": 740}
            )
            driver.get(base + "/")
            wait(driver, lambda d: len(d.find_elements(By.CSS_SELECTOR, ".day-cell")) >= 35)
            assert_width(driver, width, "main-empty")
            click(driver, "#create-button")
            wait(
                driver,
                lambda d: d.find_element(By.ID, "event-dialog").get_attribute("open") is not None,
            )
            set_value(driver, "#event-name", LONG_NAME)
            set_value(driver, "#event-date", f"2027-{month:02d}-10")
            set_value(driver, "#event-time", "21:45")
            set_value(driver, "#event-repeat", "custom")
            set_value(driver, "#event-period", "0")
            click(driver, "#save-event")
            assert driver.find_element(By.ID, "event-error").is_displayed()
            assert driver.find_element(By.ID, "event-name").get_attribute("value") == LONG_NAME
            assert_width(driver, width, "form-error")
            driver.save_screenshot(str(SHOTS / f"calendar-{width}-form-error.png"))
            # A short viewport approximates the space left by a software keyboard; Firefox does not open one.
            driver.browsing_context.set_viewport(
                context=driver.current_window_handle, viewport={"width": width, "height": 360}
            )
            for selector in (
                "#event-name",
                "#event-date",
                "#event-time",
                "#event-repeat",
                "#event-period",
                "#event-error",
                "#event-dialog .secondary-button",
                "#save-event",
            ):
                element = driver.find_element(By.CSS_SELECTOR, selector)
                driver.execute_script('arguments[0].scrollIntoView({block:"center"})', element)
                rect = driver.execute_script(
                    "const r=arguments[0].getBoundingClientRect(); return [r.top,r.bottom]", element
                )
                assert 0 <= rect[0] < rect[1] <= 360, (width, selector, rect)
            assert_width(driver, width, "form-short-height")
            driver.save_screenshot(str(SHOTS / f"calendar-{width}-short-height.png"))
            driver.browsing_context.set_viewport(
                context=driver.current_window_handle, viewport={"width": width, "height": 740}
            )
            set_value(driver, "#event-period", "7")
            click(driver, "#save-event")
            wait(
                driver,
                lambda d: (
                    f"2027" in d.find_element(By.ID, "month-title").text
                    and len(d.find_elements(By.CSS_SELECTOR, ".cell-event")) > 0
                ),
            )
            stamp = int(datetime(2027, month, 10, 12, 0, tzinfo=timezone.utc).timestamp())
            for index in range(5):
                payload = {
                    "name": f"Дополнительное событие {index + 1}",
                    "start_at": stamp,
                    "period": None,
                }
                request = Request(
                    base + "/add/",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    assert response.status == 201
            click(driver, "#next-month")
            click(driver, "#prev-month")
            wait(driver, lambda d: d.find_elements(By.CSS_SELECTOR, ".more-button"))
            day_label = f"10 {MONTHS[month]} 2027"
            cell = driver.find_element(
                By.CSS_SELECTOR, f'.day-cell:has(.day-number[aria-label="{day_label}"])'
            )
            more = cell.find_element(By.CSS_SELECTOR, ".more-button")
            assert "Ещё 4" in more.text
            more.click()
            wait(driver, lambda d: d.find_element(By.ID, "day-count").text == "6")
            assert LONG_NAME in driver.find_element(By.ID, "day-list").text
            assert_width(driver, width, "day-with-six-events")
            driver.execute_script("window.scrollTo(0,0)")
            driver.get_full_page_screenshot_as_file(str(SHOTS / f"calendar-{width}-main.png"))
            first = driver.find_element(By.CSS_SELECTOR, ".day-item")
            first.click()
            click(driver, "#event-detail .detail-actions button:nth-child(2)")
            copy = driver.find_element(By.ID, "delete-copy").text
            assert LONG_NAME in copy and day_label in copy and "только это повторение" in copy
            assert_width(driver, width, "delete-confirmation")
            driver.save_screenshot(str(SHOTS / f"calendar-{width}-delete.png"))
            click(driver, "#confirm-delete")
            wait(driver, lambda d: d.find_element(By.ID, "day-count").text == "5")
            assert_width(driver, width, "after-delete")
        print("Exact viewport checks PASS", flush=True)
    finally:
        if driver:
            driver.quit()
        server.terminate()
        server.wait(timeout=5)
