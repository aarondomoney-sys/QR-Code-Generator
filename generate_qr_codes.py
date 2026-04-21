#!/usr/bin/env python3
"""
Hugo Cars QR Code Generator
Scrapes hugocars.ie and generates QR codes with make/model/year/reg data.

Usage:
    python generate_qr_codes.py           # New cars only
    python generate_qr_codes.py --reset   # Regenerate everything
    python generate_qr_codes.py --quick   # Fast pass (check for new only)
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

BASE_URL    = "https://www.hugocars.ie"
LISTINGS_URL = f"{BASE_URL}/used-cars/"

DATA_DIR   = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
OUTPUT_DIR = DATA_DIR / "qr_codes"
STATE_FILE = DATA_DIR / "seen_cars.json"

# Common Irish car makes for parsing
KNOWN_MAKES = [
    "Audi","BMW","Citroën","Citroen","Dacia","DS","Fiat","Ford","Honda","Hyundai",
    "Jaguar","Jeep","Kia","Land Rover","Lexus","Mazda","Mercedes","Mercedes-Benz",
    "Mini","Mitsubishi","Nissan","Opel","Peugeot","Porsche","Renault","SEAT","Seat",
    "Skoda","Škoda","Subaru","Suzuki","Tesla","Toyota","Vauxhall","Volkswagen","Volvo",
]
# Longest first so "Land Rover" matches before "Land"
KNOWN_MAKES.sort(key=len, reverse=True)

# Irish plate pattern: 211-D-1234 / 21 D 12345 / 211D1234
IRISH_REG = re.compile(r'\b(\d{2,3})[\s\-]?([A-Z]{1,2})[\s\-]?(\d{1,6})\b')


def load_seen_cars() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_seen_cars(seen: dict):
    STATE_FILE.write_text(json.dumps(seen, indent=2))


def safe_filename(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:80]

def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    # This specifically targets patterns like "A 3", "X 5", "Q 7" and removes the space
    name = re.sub(r"\b([A-Z])\s+(\d)\b", r"\1\2", name)
    return name



def parse_car(name: str, card_text: str = "") -> dict:
    """Extract year, make, model, reg from a car name and optional full card text."""
    name = clean_name(name)

    year  = ""
    make  = ""
    model = ""
    reg   = ""

    # Year: 4-digit number 1990–2030
    m = re.search(r'\b(19[9]\d|20[0-3]\d)\b', name)
    year = m.group(1) if m else ""

    # Make
    for mk in KNOWN_MAKES:
        if re.search(rf'\b{re.escape(mk)}\b', name, re.IGNORECASE):
            make = mk
            break

    # Model: everything after make (and year)
    if make:
        after = re.sub(rf'^.*?\b{re.escape(make)}\b\s*', '', name, flags=re.IGNORECASE).strip()
        model = re.sub(r'^\d{4}\s*', '', after).strip()
    elif year:
        model = re.sub(rf'^\s*{year}\s*', '', name).strip()

    # Registration — check card text first, fall back to name
    for text in [card_text, name]:
        m = IRISH_REG.search(text.upper())
        if m:
            reg = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            break

    return {"year": year, "make": make or "Other", "model": model or name, "reg": reg, "name": name}


def extract_cars_from_page(page) -> list[dict]:
    anchors = page.query_selector_all(
        "a[href*='car-details'], a[href*='/cars/'], a[href*='/stock/'], a[href*='vehicle']"
    )
    results = []
    seen_hrefs: set[str] = set()

    for a in anchors:
        href = a.get_attribute("href") or ""
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        full_url = href if href.startswith("http") else BASE_URL + href

        name       = ""
        card_text  = ""
        try:
            card = a.evaluate_handle(
                "el => el.closest('.car-card,.vehicle-card,.listing-card,article,.item,li,.col') || el.parentElement"
            )
            name      = (page.evaluate("el => el.querySelector('h2,h3,h4,h5')?.innerText || ''", card) or "").strip()
            card_text = (page.evaluate("el => el.innerText || ''", card) or "").strip()
        except Exception:
            pass

        if not name:
            name = (a.inner_text() or "").strip()
        if not name:
            m = re.search(r"[=\/]([^=\/\?&]+)$", href)
            name = m.group(1).replace("+", " ").replace("-", " ") if m else href

        car = parse_car(name, card_text)
        car["url"] = full_url
        results.append(car)

    return results


def scrape_car_listings(quick: bool = False) -> list[dict]:
    """Return list of car dicts for all cars on hugocars.ie."""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--mute-audio",
            ],
        )
        context = browser.new_context()
        context.set_default_timeout(30000)
        page = context.new_page()

        # Block images, fonts and media — we only need HTML/JSON data
        page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_()
        )

        api_cars: list[dict] = []
        api_done = {"found": False}

        def handle_response(response):
            if api_done["found"]:
                return
            url = response.url
            if not any(k in url for k in ["api","stock","inventory","vehicle","cars","search"]):
                return
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                data = response.json()
            except Exception:
                return
            items = None
            if isinstance(data, list) and len(data) > 5:
                items = data
            elif isinstance(data, dict):
                for key in ("data","results","vehicles","cars","stock","items","listings"):
                    if isinstance(data.get(key), list) and len(data[key]) > 5:
                        items = data[key]
                        break
            if not items:
                return
            sample = items[0] if items else {}
            if not any(k in sample for k in ("make","model","title","name","slug","url","href","id")):
                return
            print(f"  [API] {len(items)} cars via {url}")
            api_done["found"] = True
            for item in items:
                item_url = (
                    item.get("url") or item.get("href") or item.get("link") or
                    item.get("permalink") or item.get("slug") or ""
                )
                if item_url and not item_url.startswith("http"):
                    item_url = BASE_URL + ("" if item_url.startswith("/") else "/") + item_url
                if not item_url:
                    iid = item.get("id") or item.get("stockId") or item.get("stock_id") or ""
                    item_url = f"{BASE_URL}/car-details/?{iid}" if iid else ""
                if not item_url:
                    continue

                raw_name = (
                    item.get("title") or item.get("name") or
                    " ".join(filter(None, [
                        str(item.get("year", "")), item.get("make",""),
                        item.get("model",""), item.get("variant","") or item.get("trim",""),
                    ])).strip()
                )
                car = parse_car(raw_name)
                # Override with structured API fields if present
                if item.get("make"):  car["make"]  = item["make"]
                if item.get("model"): car["model"] = item["model"]
                if item.get("year"):  car["year"]  = str(item["year"])
                for rk in ("registration","reg","regNo","plate","vrm"):
                    if item.get(rk):
                        car["reg"] = str(item[rk])
                        break
                car["url"] = item_url
                api_cars.append(car)

        page.on("response", handle_response)
        print(f"Loading {LISTINGS_URL} ...")
        page.goto(LISTINGS_URL, wait_until="domcontentloaded", timeout=60000)

        if quick:
            time.sleep(2)
            sh = page.evaluate("document.body.scrollHeight")
            for pos in range(0, sh + 500, 600):
                page.evaluate(f"window.scrollTo(0,{pos})")
                time.sleep(0.1)
            time.sleep(2)
        else:
            prev, stale = 0, 0
            while stale < 4:
                sh = page.evaluate("document.body.scrollHeight")
                for pos in range(0, sh + 1000, 400):
                    page.evaluate(f"window.scrollTo(0,{pos})")
                    time.sleep(0.15)
                time.sleep(1.5)
                for sel in [
                    "button:text-matches('load more','i')", "a:text-matches('load more','i')",
                    "button:text-matches('show more','i')", ".load-more", ".show-more",
                ]:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            btn.scroll_into_view_if_needed()
                            btn.click()
                            page.wait_for_load_state("networkidle", timeout=10000)
                            time.sleep(1)
                            break
                    except Exception:
                        pass
                cur = len(extract_cars_from_page(page))
                stale = stale + 1 if cur == prev else 0
                if cur != prev:
                    print(f"  Cars visible: {cur}")
                prev = cur

        cars = api_cars if api_cars else extract_cars_from_page(page)
        browser.close()

    seen_urls: set[str] = set()
    unique: list[dict] = []
    for c in cars:
        if c["url"] not in seen_urls:
            seen_urls.add(c["url"])
            unique.append(c)

    print(f"\nTotal cars found: {len(unique)}")
    return unique


def make_qr(car: dict, output_path: Path):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(car["url"])
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    parts = list(filter(None, [car.get("year",""), car.get("make",""), car.get("model","")]))
    caption = " ".join(parts) or car.get("name", "")
    if car.get("reg"):
        caption += f"  |  {car['reg']}"

    qr_w, qr_h = qr_img.size
    canvas = Image.new("RGB", (qr_w, qr_h + 54), "white")
    canvas.paste(qr_img, (0, 0))
    draw  = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), caption, font=font)
    x = max((qr_w - (bbox[2] - bbox[0])) // 2, 4)
    draw.text((x, qr_h + 10), caption, fill="#111111", font=font)
    canvas.save(output_path, "PNG")


def process_new_cars(cars: list[dict], seen: dict) -> int:
    """Generate QR codes for cars not already in seen. Returns count of new ones."""
    new_cars = [c for c in cars if c["url"] not in seen]
    if not new_cars:
        return 0

    def process_one(car):
        filename = safe_filename(f"{car.get('year','')}_{car.get('make','')}_{car.get('model','')}")
        if not filename.strip("_"):
            filename = safe_filename(car["url"])
        out = OUTPUT_DIR / f"{filename}.png"
        counter = 1
        while out.exists() and seen.get(car["url"], {}).get("file") != str(out):
            out = OUTPUT_DIR / f"{filename}_{counter}.png"
            counter += 1
        make_qr(car, out)
        return car["url"], {**car, "file": str(out)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        for url, info in pool.map(process_one, new_cars):
            seen[url] = info
            print(f"  QR: {info['name']}")

    return len(new_cars)


def main():
    reset = "--reset" in sys.argv
    quick = "--quick" in sys.argv

    if reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("State reset.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seen  = load_seen_cars()
    cars  = scrape_car_listings(quick=quick)
    count = process_new_cars(cars, seen)
    save_seen_cars(seen)
    print(f"\nDone. {count} new QR code(s) in: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
