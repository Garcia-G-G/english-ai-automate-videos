#!/usr/bin/env python3
"""Screenshot every dashboard page and time it, in a light and a dark OS theme.

    streamlit run src/admin.py --server.headless true --server.port 8601 &
    python3 tools/ui/shoot_pages.py --port 8601 --out _audit/stills/ui [--dark] [Page ...]

Needs `pip install playwright && python3 -m playwright install chromium` (free).
Prints seconds until the page stops running and how many exceptions it shows;
that is the number STEP 57 asks for, measured in a real browser, not AppTest.
"""
import argparse, asyncio, time
from pathlib import Path

PAGES = ["Dashboard", "Generate", "Queue", "Review", "Upload", "Library",
         "Topics", "Manim", "Scheduler", "Settings", "Logs"]


async def main(args):
    from playwright.async_api import async_playwright
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900},
                                      color_scheme="dark" if args.dark else "light")
        for name in args.pages or PAGES:
            t = time.time()
            await page.goto(f"http://localhost:{args.port}/?page={name}", wait_until="networkidle")
            await page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=60000)
            await page.wait_for_function(
                "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120000)
            seconds = time.time() - t
            await page.wait_for_timeout(800)
            tag = "dark_" if args.dark else ""
            await page.screenshot(path=str(out / f"{tag}{name}.png"), full_page=True)
            errors = await page.locator('[data-testid="stException"]').count()
            print(f"{name:10s} {seconds:5.1f}s  exceptions={errors}")
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--port", default="8601")
    ap.add_argument("--out", default="_audit/stills/ui")
    ap.add_argument("--dark", action="store_true")
    asyncio.run(main(ap.parse_args()))
