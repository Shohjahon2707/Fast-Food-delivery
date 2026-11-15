"""Exercise the local customer flow. Start Django on port 8000 first.

Creates a uniquely named test customer and a cancelled test order in the local DB.
Uses Chromium from CHROMIUM_PATH (or the Playwright-managed browser).
"""

import json
import os
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8000"


def main():
    with sync_playwright() as playwright:
        executable = os.getenv("CHROMIUM_PATH")
        browser = playwright.chromium.launch(
            headless=True, **({"executable_path": executable} if executable else {})
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ru-RU")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        expect(page.locator(".restaurant-card")).to_have_count(6)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.screenshot(path=str(ROOT / "docs/images/web-marketplace-home.png"), full_page=True)
        page.get_by_role("link", name="Умный обед").last.click()
        page.select_option("#id_category", label="Горячие блюда")
        page.fill("#id_min_price", "40000")
        page.fill("#id_max_price", "70000")
        page.get_by_role("button", name="Подобрать").click()
        expect(page.locator(".product-card")).to_have_count(5)
        names = set(page.locator(".product-restaurant").all_text_contents())
        assert len(names) == 4, names
        page.screenshot(path=str(ROOT / "docs/images/web-smart-lunch.png"), full_page=True)
        filtered_url = page.url
        for language, heading in [
            ("en", "Smart lunch"),
            ("uz", "Aqlli tushlik"),
            ("ru", "Умный обед"),
        ]:
            page.select_option("#language", language)
            expect(page.locator("h1")).to_contain_text(heading)
            expect(page.locator("#id_min_price")).to_have_value("40000")
        page.goto(BASE + "/users/register/")
        suffix = uuid.uuid4().hex[:10]
        username = "browser_" + suffix
        for field, value in {
            "first_name": "Тестовый покупатель",
            "username": username,
            "email": username + "@example.invalid",
            "phone": "+998901234567",
            "password1": "Smoke-test-" + suffix + "-79!",
            "password2": "Smoke-test-" + suffix + "-79!",
        }.items():
            page.fill(f"#id_{field}", value)
        page.locator(".auth-form button[type=submit], .auth-form form button").click()
        page.wait_for_url("**/menu/")
        page.goto(filtered_url)
        cards = page.locator(".product-card")
        cards.nth(0).locator("button.add-button").click()
        expect(page.locator("[data-cart-count]").first).to_have_text("1")
        # A different restaurant asks before replacement. Cancelling keeps the original basket.
        page.once("dialog", lambda dialog: dialog.dismiss())
        cards.nth(1).locator("button.add-button").click()
        expect(cards.nth(1).locator("button.add-button")).to_be_enabled()
        page.goto(BASE + "/cart/")
        expect(page.locator(".cart-row-name h3")).to_have_text("Казан-кебаб")
        page.get_by_role("link", name="К оформлению").click()
        page.fill("#id_address", "Ташкент, тестовая улица 25, кв. 7")
        page.fill("#id_comment", "Браузерная проверка, не выполнять доставку")
        page.locator("form[data-submit-once] button[type=submit]").click()
        page.wait_for_url("**/success/*") if "/success/" not in page.url else None
        expect(page.get_by_role("link", name="Следить за заказом")).to_be_visible()
        page.get_by_role("link", name="Следить за заказом").click()
        order_url = page.url
        expect(page.locator(".sum-total")).to_contain_text("80 000")
        expect(page.locator(".status").first).to_have_text("Принят")
        page.locator("details.support summary").click()
        page.fill("#cancel-reason", "Проверка завершена, тестовый заказ")
        page.get_by_role("button", name="Отменить заказ", exact=True).click()
        expect(page.locator(".status").first).to_have_text("Отменён")
        # Independent session cannot read another customer's order.
        guest = browser.new_context(locale="ru-RU")
        guest_page = guest.new_page()
        guest_page.goto(order_url)
        assert "/users/login/" in guest_page.url
        guest.close()
        for width in [390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 900})
            for path in [
                "/",
                "/smart-lunch/?min_price=40000&max_price=70000",
                "/users/profile/",
                "/orders/",
                "/cart/",
            ]:
                response = page.goto(BASE + path, wait_until="networkidle")
                assert response.status == 200, (width, path, response.status)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (
                    width,
                    path,
                    "overflow",
                )
            if width == 390:
                page.goto(BASE, wait_until="networkidle")
                page.screenshot(
                    path=str(ROOT / "docs/images/web-narrow-screen.png"), full_page=True
                )
        no_js = browser.new_context(java_script_enabled=False, locale="ru-RU")
        no_js_page = no_js.new_page()
        no_js_page.goto(BASE + "/smart-lunch/")
        no_js_page.fill("#id_min_price", "40000")
        no_js_page.fill("#id_max_price", "70000")
        no_js_page.get_by_role("button", name="Подобрать").click()
        expect(no_js_page.locator(".product-card")).to_have_count(12)
        no_js.close()
        assert not errors, errors
        print(
            json.dumps(
                {
                    "result": "passed",
                    "customer": username,
                    "order": order_url,
                    "widths": [390, 768, 1440],
                    "languages": ["ru", "uz", "en"],
                    "javascript_errors": errors,
                },
                ensure_ascii=False,
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
