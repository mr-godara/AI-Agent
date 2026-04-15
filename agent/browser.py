from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ActionInput = Union[str, Dict[str, Any]]


class BrowserController:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._context: Optional[Any] = None
        self.page: Optional[Any] = None

    def start(self) -> None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=self.headless)
        context = browser.new_context()

        self._playwright = pw
        self._browser = browser
        self._context = context
        self.page = context.new_page()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def snapshot(self) -> Dict[str, Any]:
        page = self.page
        if page is None:
            return {"url": "", "title": "", "hints": {}}

        hints = {}
        for text in [
            "Login",
            "Dashboard",
            "Users",
            "Create User",
            "Reset Password",
            "Delete User",
            "Password reset",
            "Created user",
            "User not found",
            "User already exists",
        ]:
            hints[text] = page.get_by_text(text, exact=False).count() > 0

        return {
            "url": page.url,
            "title": page.title(),
            "hints": hints,
        }

    def execute(self, action: str, action_input: ActionInput) -> str:
        page = self.page
        if page is None:
            raise RuntimeError("Browser has not been started.")

        if action == "navigate":
            url = self._extract_value(action_input, "url")
            page.goto(url, wait_until="domcontentloaded")
            return f"Navigated to {url}"

        if action == "click":
            text = self._extract_value(action_input, "text")
            self._click_by_text(text)
            return f"Clicked '{text}'"

        if action == "type":
            field = self._extract_value(action_input, "field")
            value = self._extract_value(action_input, "value")
            self._type_by_placeholder_or_label(field, value)
            return f"Typed '{value}' into '{field}'"

        if action == "read":
            text = self._extract_value(action_input, "text")
            count = page.get_by_text(text, exact=False).count()
            if count > 0:
                return f"FOUND: text '{text}' appears {count} time(s)."
            return f"NOT_FOUND: text '{text}' is not visible."

        if action == "wait":
            seconds_raw = self._extract_value(action_input, "seconds")
            seconds = float(seconds_raw)
            page.wait_for_timeout(int(seconds * 1000))
            return f"Waited for {seconds} second(s)"

        if action == "done":
            result = self._extract_value(action_input, "result")
            return f"DONE: {result}"

        return f"Unknown action '{action}'."

    def _click_by_text(self, text: str) -> None:
        page = self.page
        if page is None:
            raise RuntimeError("Browser has not been started.")

        click_attempts = [
            lambda: page.get_by_role("button", name=text, exact=True).first.click(timeout=1200),
            lambda: page.get_by_role("link", name=text, exact=True).first.click(timeout=1200),
            lambda: page.get_by_text(text, exact=True).first.click(timeout=1200),
            lambda: page.get_by_text(text, exact=False).first.click(timeout=1200),
        ]

        for attempt in click_attempts:
            try:
                attempt()
                return
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        raise RuntimeError(f"Could not click visible text '{text}'.")

    def _type_by_placeholder_or_label(self, field: str, value: str) -> None:
        page = self.page
        if page is None:
            raise RuntimeError("Browser has not been started.")

        # Try placeholder first because it most closely mirrors human form usage.
        placeholder = page.get_by_placeholder(field)
        if placeholder.count() > 0:
            placeholder.first.fill(value)
            return

        labeled = page.get_by_label(field, exact=True)
        if labeled.count() > 0:
            try:
                labeled.first.fill(value)
                return
            except Exception:
                try:
                    labeled.first.select_option(value)
                    return
                except Exception as exc:
                    raise RuntimeError(
                        f"Found field '{field}' but could not fill/select value."
                    ) from exc

        labeled_partial = page.get_by_label(field, exact=False)
        if labeled_partial.count() > 0:
            try:
                labeled_partial.first.fill(value)
                return
            except Exception:
                try:
                    labeled_partial.first.select_option(value)
                    return
                except Exception as exc:
                    raise RuntimeError(
                        f"Found field '{field}' (partial label) but could not fill/select value."
                    ) from exc

        raise RuntimeError(
            f"Could not find input/select field by placeholder or label: '{field}'."
        )

    @staticmethod
    def _extract_value(action_input: ActionInput, key: str) -> str:
        if isinstance(action_input, dict):
            value = action_input.get(key)
            if value is None:
                if key == "result":
                    return json.dumps(action_input)
                raise ValueError(f"Missing key '{key}' in action input: {action_input}")
            return str(value)

        if isinstance(action_input, str):
            return action_input

        raise ValueError(f"Unsupported action input: {action_input}")
