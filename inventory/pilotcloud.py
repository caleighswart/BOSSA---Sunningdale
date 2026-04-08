"""
Bossa Sunningdale — Pilot Cloud Automated Login & Report Download
=================================================================
Uses a headless Chromium browser (Playwright) to log into
cloud.pilotlive.co.za and download the Theoretical Stock On Hand
Excel report for processing by the analysis engine.

Credentials are read from environment variables:
  PILOTLIVE_USERNAME — your Pilot Cloud email / username
  PILOTLIVE_PASSWORD — your Pilot Cloud password
"""

import os
import tempfile
import time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

BASE_URL = "https://cloud.pilotlive.co.za"
DEBUG    = os.getenv("PILOTLIVE_DEBUG", "").lower() in ("1", "true", "yes")


def _screenshot(page, name):
    """Save a debug screenshot when PILOTLIVE_DEBUG=1."""
    if DEBUG:
        path = os.path.join(tempfile.gettempdir(), f"pilotcloud_{name}.png")
        page.screenshot(path=path)
        print(f"    [debug] screenshot → {path}")


def download_stock_report(username: str, password: str) -> str:
    """
    Log into Pilot Cloud, navigate to Theoretical Stock On Hand report,
    export it as Excel, and return the local file path.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not DEBUG)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # ── Step 1: Open login page ────────────────────────────────────────────
        print("  Opening Pilot Cloud login page...")
        page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
        _screenshot(page, "01_login_page")

        # ── Step 2: Fill credentials ───────────────────────────────────────────
        print("  Entering credentials...")
        # Try common selector patterns for username/email field
        for sel in ['input[name="username"]', 'input[name="email"]',
                    'input[type="email"]', 'input[id="username"]',
                    'input[id="email"]', 'input[placeholder*="email" i]',
                    'input[placeholder*="username" i]']:
            if page.locator(sel).count() > 0:
                page.fill(sel, username)
                break
        else:
            _screenshot(page, "ERROR_no_username_field")
            raise RuntimeError(
                "Could not find username/email input on Pilot Cloud login page. "
                "Enable PILOTLIVE_DEBUG=1 to capture a screenshot for diagnosis."
            )

        # Password field
        for sel in ['input[type="password"]', 'input[name="password"]',
                    'input[id="password"]']:
            if page.locator(sel).count() > 0:
                page.fill(sel, password)
                break
        else:
            _screenshot(page, "ERROR_no_password_field")
            raise RuntimeError("Could not find password input on Pilot Cloud login page.")

        _screenshot(page, "02_credentials_filled")

        # ── Step 3: Submit login ───────────────────────────────────────────────
        print("  Submitting login...")
        for sel in ['button[type="submit"]', 'input[type="submit"]',
                    'button:has-text("Login")', 'button:has-text("Sign in")',
                    'button:has-text("Log in")']:
            if page.locator(sel).count() > 0:
                page.click(sel)
                break
        else:
            # Last resort: press Enter on the password field
            page.keyboard.press("Enter")

        page.wait_for_load_state("networkidle", timeout=30_000)
        _screenshot(page, "03_after_login")

        # Check we're not still on the login page
        if "login" in page.url.lower() or "signin" in page.url.lower():
            _screenshot(page, "ERROR_login_failed")
            raise RuntimeError(
                "Login appears to have failed — still on login page after submit. "
                "Check PILOTLIVE_USERNAME and PILOTLIVE_PASSWORD GitHub Secrets."
            )
        print(f"  Logged in. Current page: {page.url}")

        # ── Step 4: Navigate to Stock Reports ─────────────────────────────────
        print("  Navigating to stock report...")

        # Try direct URL paths first (common Pilot Cloud patterns)
        report_found = False
        for path in ["/reports/stock", "/reports/theoretical-stock",
                     "/stock/report", "/inventory/report"]:
            try:
                page.goto(BASE_URL + path, wait_until="networkidle", timeout=15_000)
                if page.url.startswith(BASE_URL + path):
                    report_found = True
                    break
            except PWTimeoutError:
                continue

        if not report_found:
            # Fall back: look for a "Reports" or "Stock" nav link
            _screenshot(page, "04_dashboard")
            for text in ["Reports", "Stock", "Inventory", "Theoretical"]:
                loc = page.get_by_role("link", name=text, exact=False)
                if loc.count() > 0:
                    loc.first.click()
                    page.wait_for_load_state("networkidle", timeout=15_000)
                    _screenshot(page, f"05_nav_{text.lower()}")
                    report_found = True
                    break

        if not report_found:
            _screenshot(page, "ERROR_no_reports_nav")
            raise RuntimeError(
                "Could not find the stock reports section on Pilot Cloud. "
                "Enable PILOTLIVE_DEBUG=1 and check the screenshot for navigation hints."
            )

        _screenshot(page, "06_reports_page")
        print(f"  On reports page: {page.url}")

        # ── Step 5: Look for "Theoretical Stock On Hand" specifically ─────────
        for text in ["Theoretical Stock On Hand", "Theoretical Stock", "Stock On Hand"]:
            loc = page.get_by_text(text, exact=False)
            if loc.count() > 0:
                loc.first.click()
                page.wait_for_load_state("networkidle", timeout=15_000)
                _screenshot(page, "07_theoretical_stock")
                break

        # ── Step 6: Download / Export ──────────────────────────────────────────
        print("  Triggering export...")
        _screenshot(page, "08_before_export")

        tmp_dir = tempfile.mkdtemp()

        # Try to find and click an Export/Download button, then catch the download
        exported = False
        for sel in [
            'button:has-text("Export")', 'button:has-text("Download")',
            'a:has-text("Export")',      'a:has-text("Download")',
            'button:has-text("Excel")',  'a:has-text("Excel")',
            '[title*="Export" i]',       '[title*="Download" i]',
        ]:
            if page.locator(sel).count() > 0:
                with page.expect_download(timeout=60_000) as dl_info:
                    page.click(sel)
                download = dl_info.value
                fname = download.suggested_filename or "theoretical_stock.xlsx"
                out_path = os.path.join(tmp_dir, fname)
                download.save_as(out_path)
                exported = True
                break

        if not exported:
            _screenshot(page, "ERROR_no_export_button")
            raise RuntimeError(
                "Could not find an Export/Download button on the Pilot Cloud report page. "
                "Enable PILOTLIVE_DEBUG=1 to capture screenshots and identify the correct selector."
            )

        browser.close()
        print(f"  Report saved to: {out_path}")
        return out_path
