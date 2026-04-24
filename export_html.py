#!/usr/bin/env python3
"""
Hugo Cars — HTML Export
Generates a single self-contained HTML file with all QR codes embedded.
Send this one file to anyone — opens in any browser, no install needed.

Usage:  python3 export_html.py
Output: HugoCars_QR_Codes.html
"""

import base64
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).parent
STATE_FILE = BASE_DIR / "seen_cars.json"
QR_DIR     = BASE_DIR / "qr_codes"
OUT_FILE   = BASE_DIR / "HugoCars_QR_Codes.html"

# Every brand we want shown in the filter bar (even if not in stock)
ALL_BRANDS = sorted([
    "Audi", "BMW", "Citroën", "Dacia", "DS", "Fiat", "Ford", "Honda",
    "Hyundai", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Mazda",
    "Mercedes-Benz", "Mini", "Mitsubishi", "Nissan", "Opel", "Peugeot",
    "Porsche", "Renault", "SEAT", "Skoda", "Subaru", "Suzuki", "Tesla",
    "Toyota", "Volkswagen", "Volvo", "Other",
])

KNOWN_MAKES = sorted([
    "Audi","BMW","Citroën","Citroen","Dacia","DS","Fiat","Ford","Honda","Hyundai",
    "Jaguar","Jeep","Kia","Land Rover","Lexus","Mazda","Mercedes","Mercedes-Benz",
    "Mini","Mitsubishi","Nissan","Opel","Peugeot","Porsche","Renault","SEAT","Seat",
    "Skoda","Škoda","Subaru","Suzuki","Tesla","Toyota","Vauxhall","Volkswagen","Volvo",
], key=len, reverse=True)

IRISH_REG = re.compile(r'\b(\d{2,3})[\s\-]?([A-Z]{1,2})[\s\-]?(\d{1,6})\b')

GITHUB_REPO  = "aarondomoney-sys/QR-Code-Generator"
GITHUB_PAGES = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}/HugoCars_QR_Codes.html"


def fix_model(model: str) -> str:
    """Fix spacing issues in model names.
    'a 3' → 'A3', 'x 5' → 'X5', 'a 3 5' → 'A35', 'c class' → 'C Class'
    """
    model = model.strip().title()
    # Collapse single letter + space + digits: "A 3" → "A3", "X 5" → "X5"
    model = re.sub(r'\b([A-Z]) (\d)', r'\1\2', model)
    # Repeat in case of "A 3 5" → "A35"
    model = re.sub(r'\b([A-Z]\d+) (\d)', r'\1\2', model)
    return model


def parse_name(name: str) -> dict:
    """Extract year/make/model from a raw car name string."""
    name = re.sub(r"\s+", " ", name).strip()
    # Fix spaced-out single letters: "a u d i" → "audi"
    name = re.sub(r"\b([A-Za-z])(?: ([A-Za-z]))+\b",
                  lambda m: m.group(0).replace(" ", ""), name)

    year = ""
    m = re.search(r'\b(19[9]\d|20[0-3]\d)\b', name)
    if m:
        year = m.group(1)

    make = ""
    for mk in KNOWN_MAKES:
        if re.search(rf'\b{re.escape(mk)}\b', name, re.IGNORECASE):
            make = mk
            break
    # Normalise variants
    make = {"Citroen": "Citroën", "Seat": "SEAT", "Skoda": "Skoda",
            "Škoda": "Skoda", "Mercedes": "Mercedes-Benz"}.get(make, make)

    model = ""
    if make:
        after = re.sub(rf'^.*?\b{re.escape(make)}\b\s*', '', name, flags=re.IGNORECASE).strip()
        model = re.sub(r'^\d{4}\s*', '', after).strip()
    elif year:
        model = name.replace(year, "").strip()

    return {
        "year":  year,
        "make":  make or "Other",
        "model": fix_model(model) if model else name.title(),
    }


def load_cars() -> list[dict]:
    if not STATE_FILE.exists():
        print("No seen_cars.json found. Run generate_qr_codes.py first.")
        return []
    data = json.loads(STATE_FILE.read_text())
    cars = []
    for url, info in data.items():
        fp = Path(info.get("file", ""))
        if not fp.exists():
            continue

        # Use stored fields if present (new scraper), else parse from name
        name = info.get("name", "")
        if info.get("make"):
            parsed = {
                "make":  info["make"],
                "model": fix_model(info.get("model", "")),
                "year":  info.get("year", ""),
            }
            # Normalise make name
            parsed["make"] = {
                "Citroen": "Citroën", "Seat": "SEAT",
                "Skoda": "Skoda", "Škoda": "Skoda",
                "Mercedes": "Mercedes-Benz",
            }.get(parsed["make"], parsed["make"])
        else:
            parsed = parse_name(name)

        # Extract stock ID from URL e.g. ?4384138=...
        stock_id = ""
        m = re.search(r'\?(\d+)=', url)
        if m:
            stock_id = m.group(1)

        cars.append({
            "name":     name,
            "make":     parsed["make"],
            "model":    parsed["model"],
            "year":     parsed["year"],
            "reg":      info.get("reg", ""),
            "mileage":  info.get("mileage", ""),
            "colour":   info.get("colour", ""),
            "stock_id": stock_id,
            "url":      url,
            "file":     fp,
        })

    cars.sort(key=lambda c: (c["make"], c["year"], c["model"]))
    return cars


def img_to_b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build_html(cars: list[dict]) -> str:
    groups: dict[str, list] = defaultdict(list)
    for c in cars:
        groups[c["make"]].append(c)

    # Brand filter buttons — all known brands, greyed if not in stock
    in_stock = set(groups.keys())
    brand_btns = '<button class="brand-btn active" onclick="filterBrand(\'all\', this)">All</button>\n'
    for brand in ALL_BRANDS:
        has = brand in in_stock
        cls = "brand-btn" if has else "brand-btn empty"
        brand_btns += f'<button class="{cls}" onclick="filterBrand(\'{brand.lower()}\', this)">{brand}</button>\n'

    # Car sections
    sections_html = ""
    for make in sorted(groups):
        group = groups[make]
        cards_inner = ""
        for c in group:
            b64 = img_to_b64(c["file"])
            year_tag    = f'<span class="tag tag-year">{c["year"]}</span>' if c["year"] else ""
            reg_tag     = f'<span class="tag tag-reg">{c["reg"]}</span>' if c["reg"] else ""
            mileage_tag = f'<span class="tag tag-mileage">{c["mileage"]}</span>' if c["mileage"] else ""
            colour_tag  = f'<span class="tag tag-colour">{c["colour"]}</span>' if c["colour"] else ""
            model_txt   = c["model"] or c["name"]
            cards_inner += f"""
            <div class="card"
                 data-make="{c['make'].lower()}"
                 data-model="{c['model'].lower()}"
                 data-reg="{c['reg'].lower()}"
                 data-year="{c['year']}"
                 data-name="{c['name'].lower()}">
              <div class="card-qr">
                <img src="{b64}" alt="QR {c['name']}" width="130" height="130" loading="lazy"/>
              </div>
              <div class="card-body">
                <div class="card-model">{model_txt}</div>
                <div class="card-meta">{year_tag}{mileage_tag}{colour_tag}{reg_tag}</div>
              </div>
              <div class="card-actions">
                <a href="{c['url']}" target="_blank" class="act-view">View Listing</a>
                <a href="{b64}" download="{c['file'].name}" class="act-dl">Download</a>
              </div>
            </div>"""

        sections_html += f"""
        <div class="make-section" data-make="{make.lower()}">
          <div class="make-header" onclick="toggleMake(this)">
            <span class="make-name">{make}</span>
            <span class="make-count">{len(group)}</span>
            <span class="make-divider"></span>
            <span class="make-toggle">&#x25BE;</span>
          </div>
          <div class="make-body">
            <div class="car-grid">{cards_inner}</div>
          </div>
        </div>"""

    generated = datetime.now().strftime("%-d %b %Y at %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Hugo Cars — QR Codes</title>
  <style>
    :root{{--red:#CC1515;--black:#111111;--grey:#f0f0f0;--border:#e2e2e2;--text:#1a1a1a;--muted:#888}}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif;
          background:var(--grey);color:var(--text)}}

    /* Header */
    header{{background:var(--black);padding:0 28px;display:flex;
            align-items:stretch;justify-content:space-between;gap:16px;flex-wrap:wrap}}
    .logo{{display:flex;align-items:center;gap:14px;padding:16px 0;
           border-right:3px solid var(--red);padding-right:20px}}
    .logo-h{{font-size:2.4rem;font-weight:900;color:var(--red);letter-spacing:-1px;line-height:1}}
    .logo-label{{color:white;font-size:.95rem;font-weight:700;letter-spacing:2px;
                 text-transform:uppercase;line-height:1.3}}
    .logo-label small{{display:block;font-size:.65rem;letter-spacing:1px;
                       color:rgba(255,255,255,.45);font-weight:400}}
    .header-right{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:14px 0}}
    .pill{{background:rgba(255,255,255,.1);color:rgba(255,255,255,.8);border-radius:4px;
           padding:5px 11px;font-size:.78rem;white-space:nowrap}}
    .pill.red{{background:var(--red);color:#fff;font-weight:700}}
    .btn{{display:inline-flex;align-items:center;gap:6px;padding:8px 15px;border-radius:4px;
          font-size:.8rem;font-weight:700;cursor:pointer;border:none;text-decoration:none;
          transition:filter .15s;white-space:nowrap;background:#fff;color:var(--black)}}
    .btn:hover{{filter:brightness(1.1)}}
    .redbar{{height:4px;background:var(--red)}}

    /* Brand filter bar */
    .brand-bar{{background:white;border-bottom:2px solid var(--border);
                padding:12px 20px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
    .brand-bar-label{{font-size:.75rem;font-weight:700;color:var(--muted);
                      text-transform:uppercase;letter-spacing:1px;margin-right:4px;white-space:nowrap}}
    .brand-btn{{padding:5px 12px;border-radius:20px;border:1.5px solid var(--border);
                background:white;color:var(--text);font-size:.75rem;font-weight:600;
                cursor:pointer;transition:all .15s;white-space:nowrap}}
    .brand-btn:hover{{border-color:var(--red);color:var(--red)}}
    .brand-btn.active{{background:var(--red);border-color:var(--red);color:white}}
    .brand-btn.empty{{opacity:.35;cursor:default}}
    .brand-btn.empty:hover{{border-color:var(--border);color:var(--text)}}

    /* Toolbar */
    main{{max-width:1500px;margin:0 auto;padding:22px 20px}}
    .toolbar{{display:flex;align-items:center;gap:12px;margin-bottom:24px;flex-wrap:wrap}}
    .search-wrap{{position:relative;flex:1;min-width:200px;max-width:320px}}
    .search-wrap svg{{position:absolute;left:10px;top:50%;transform:translateY(-50%);
                      opacity:.35;pointer-events:none}}
    .search-wrap input{{width:100%;padding:9px 12px 9px 34px;border:1.5px solid var(--border);
                        border-radius:4px;font-size:.88rem;outline:none;background:#fff;
                        transition:border-color .15s}}
    .search-wrap input:focus{{border-color:var(--red)}}
    .count-label{{font-size:.82rem;color:var(--muted);margin-left:auto}}

    /* Make sections */
    .make-section{{margin-bottom:32px}}
    .make-header{{display:flex;align-items:center;gap:12px;margin-bottom:12px;
                  cursor:pointer;user-select:none}}
    .make-name{{font-size:1.05rem;font-weight:800;color:var(--black);
                text-transform:uppercase;letter-spacing:.5px}}
    .make-count{{background:var(--red);color:#fff;border-radius:3px;
                 padding:2px 8px;font-size:.72rem;font-weight:700}}
    .make-toggle{{margin-left:auto;color:var(--muted);font-size:1.1rem;transition:transform .2s}}
    .make-header.collapsed .make-toggle{{transform:rotate(-90deg)}}
    .make-divider{{flex:1;height:1px;background:var(--border)}}
    .make-body.hidden{{display:none}}

    /* Cards */
    .car-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
    .card{{background:#fff;border-radius:4px;overflow:hidden;
           box-shadow:0 1px 3px rgba(0,0,0,.08);border-top:3px solid transparent;
           display:flex;flex-direction:column;
           transition:border-color .2s,box-shadow .2s,transform .15s}}
    .card:hover{{border-top-color:var(--red);box-shadow:0 5px 16px rgba(0,0,0,.13);transform:translateY(-2px)}}
    .card-qr{{padding:14px;background:#fafafa;display:flex;justify-content:center;
              border-bottom:1px solid var(--border)}}
    .card-qr img{{width:130px;height:130px;object-fit:contain}}
    .card-body{{padding:10px 12px;flex:1;display:flex;flex-direction:column;gap:4px}}
    .card-model{{font-size:.82rem;font-weight:700;color:var(--black);line-height:1.3;
                 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
    .card-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}}
    .tag{{font-size:.68rem;font-weight:600;padding:2px 7px;border-radius:3px}}
    .tag-year{{background:var(--black);color:#fff}}
    .tag-reg{{background:#fff3cd;color:#7a5500;border:1px solid #f0d060;
              font-family:monospace;letter-spacing:.5px}}
    .tag-noreg{{background:#f0f0f0;color:#aaa;font-style:italic}}
    .tag-mileage{{background:#e8f4fd;color:#1a5276;border:1px solid #aed6f1}}
    .tag-colour{{background:#f9f9f9;color:#555;border:1px solid #ddd}}
    .tag-stock{{background:#f0f0f0;color:#999;font-family:monospace;font-size:.65rem}}
    .card-actions{{display:flex;gap:6px;padding:0 10px 10px}}

    /* Refresh modal */
    .modal-bg{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;
               align-items:center;justify-content:center}}
    .modal-bg.show{{display:flex}}
    .modal{{background:#fff;border-radius:8px;padding:28px;width:360px;max-width:92vw;
            box-shadow:0 8px 40px rgba(0,0,0,.25)}}
    .modal h3{{font-size:1rem;font-weight:800;margin-bottom:6px;color:var(--black)}}
    .modal p{{font-size:.82rem;color:var(--muted);margin-bottom:16px;line-height:1.5}}
    .modal input{{width:100%;padding:9px 12px;border:1.5px solid var(--border);border-radius:4px;
                  font-size:.85rem;outline:none;margin-bottom:12px}}
    .modal input:focus{{border-color:var(--red)}}
    .modal-btns{{display:flex;gap:8px}}
    .modal-btns button{{flex:1;padding:9px;border-radius:4px;font-size:.82rem;font-weight:700;
                        cursor:pointer;border:none}}
    .btn-cancel{{background:var(--grey);color:var(--black)}}
    .btn-go{{background:var(--red);color:#fff}}
    .btn-go:disabled{{opacity:.5;cursor:not-allowed}}
    .status-msg{{font-size:.8rem;color:var(--muted);margin-top:10px;min-height:18px;line-height:1.4}}
    .status-msg.ok{{color:#1a7a3a}}
    .status-msg.err{{color:#c0392b}}
    .spinner{{display:inline-block;width:12px;height:12px;border:2px solid currentColor;
              border-top-color:transparent;border-radius:50%;animation:spin .65s linear infinite;
              vertical-align:middle;margin-right:4px}}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
    .card-actions a{{flex:1;text-align:center;padding:6px 4px;border-radius:3px;
                     font-size:.72rem;font-weight:700;text-decoration:none;transition:filter .15s}}
    .card-actions a:hover{{filter:brightness(.9)}}
    .act-view{{background:var(--grey);color:var(--black);border:1px solid var(--border)}}
    .act-dl{{background:var(--red);color:#fff}}
  </style>
</head>
<body>

<header>
  <div class="logo">
    <span class="logo-h">H</span>
    <div class="logo-label">Hugo Cars<small>QR Code Manager</small></div>
  </div>
  <div class="header-right">
    <span class="pill red">{len(cars)} cars</span>
    <span class="pill">Generated: {generated}</span>
    <button class="btn" onclick="downloadAll()">&#x2B07; Download All</button>
    <button class="btn" id="refreshBtn" onclick="openRefresh()" style="background:var(--red);color:#fff">&#x27F3; Refresh QR Codes</button>
  </div>
</header>
<div class="redbar"></div>

<!-- Refresh modal -->
<div class="modal-bg" id="modalBg" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <h3>Refresh QR Codes</h3>
    <p id="modalDesc">This will check hugocars.ie for new cars and update the page for everyone.<br><br>
    Enter the refresh code to continue. <span id="tokenHint"></span></p>
    <input type="password" id="tokenInput" placeholder="Refresh code…" autocomplete="off"/>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
      <input type="checkbox" id="saveToken" checked style="width:auto;margin:0"/>
      <label for="saveToken" style="font-size:.8rem;color:var(--muted);cursor:pointer">Remember on this device</label>
    </div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-go" id="goBtn" onclick="triggerRefresh()">Update Now</button>
    </div>
    <div class="status-msg" id="statusMsg"></div>
  </div>
</div>

<!-- Brand filter -->
<div class="brand-bar">
  <span class="brand-bar-label">Brand</span>
  {brand_btns}
</div>

<main>
  <div class="toolbar">
    <div class="search-wrap">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>
      <input type="text" id="searchInput" placeholder="Search by make, model or year…"
             oninput="doSearch(this.value)"/>
    </div>
    <span class="count-label" id="countLabel">{len(cars)} cars</span>
  </div>

  {sections_html}
</main>

<script>
  var activeBrand = 'all';

  function toggleMake(h) {{
    h.classList.toggle("collapsed");
    h.nextElementSibling.classList.toggle("hidden");
  }}

  function filterBrand(brand, btn) {{
    if (btn.classList.contains("empty")) return;
    activeBrand = brand;
    document.querySelectorAll(".brand-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("searchInput").value = "";
    applyFilters();
  }}

  var _st;
  function doSearch(q) {{
    clearTimeout(_st);
    _st = setTimeout(() => applyFilters(q), 120);
  }}

  function applyFilters(q) {{
    q = (q || document.getElementById("searchInput").value || "").toLowerCase().trim();
    var n = 0;
    document.querySelectorAll(".make-section").forEach(sec => {{
      var secMake = sec.dataset.make;
      var brandMatch = activeBrand === 'all' || secMake === activeBrand;
      if (!brandMatch) {{ sec.style.display = "none"; return; }}
      var sv = 0;
      sec.querySelectorAll(".card").forEach(c => {{
        var ok = !q || c.dataset.name.includes(q) || c.dataset.make.includes(q) ||
                 c.dataset.model.includes(q) || c.dataset.reg.includes(q) || c.dataset.year.includes(q);
        c.style.display = ok ? "" : "none";
        if (ok) {{ n++; sv++; }}
      }});
      sec.style.display = sv ? "" : "none";
      if (sv) {{
        sec.querySelector(".make-body").classList.remove("hidden");
        sec.querySelector(".make-header").classList.remove("collapsed");
      }}
    }});
    document.getElementById("countLabel").textContent = n + " car" + (n !== 1 ? "s" : "");
  }}

  function downloadAll() {{
    var links = document.querySelectorAll(".card:not([style*='none']) .act-dl");
    links.forEach((a, i) => setTimeout(() => a.click(), i * 120));
  }}

  // ── Refresh via GitHub Actions ──────────────────────────────────────────
  var REPO = "{GITHUB_REPO}";
  var PAGES_URL = "{GITHUB_PAGES}";

  function openRefresh() {{
    var saved = localStorage.getItem("hugo_refresh_token");
    if (saved) {{
      document.getElementById("tokenInput").value = saved;
      document.getElementById("tokenHint").textContent = "(saved on this device)";
    }} else {{
      document.getElementById("tokenHint").textContent = "Ask Aaron for the refresh code.";
    }}
    document.getElementById("statusMsg").textContent = "";
    document.getElementById("statusMsg").className = "status-msg";
    document.getElementById("goBtn").disabled = false;
    document.getElementById("goBtn").textContent = "Update Now";
    document.getElementById("modalBg").classList.add("show");
    if (!saved) setTimeout(() => document.getElementById("tokenInput").focus(), 100);
  }}

  function closeModal() {{
    document.getElementById("modalBg").classList.remove("show");
  }}

  function setStatus(msg, cls) {{
    var el = document.getElementById("statusMsg");
    el.innerHTML = msg;
    el.className = "status-msg" + (cls ? " " + cls : "");
  }}

  async function triggerRefresh() {{
    var token = document.getElementById("tokenInput").value.trim();
    if (!token) {{ setStatus("Please enter the refresh code.", "err"); return; }}

    if (document.getElementById("saveToken").checked) {{
      localStorage.setItem("hugo_refresh_token", token);
    }}

    document.getElementById("goBtn").disabled = true;
    document.getElementById("goBtn").innerHTML = '<span class="spinner"></span> Starting…';
    setStatus("");

    try {{
      var res = await fetch(
        "https://api.github.com/repos/" + REPO + "/actions/workflows/update.yml/dispatches",
        {{
          method: "POST",
          headers: {{
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{ref: "main"}})
        }}
      );

      if (res.status === 204) {{
        // Workflow triggered — poll for completion
        setStatus('<span class="spinner"></span> Checking hugocars.ie for new cars… (takes ~2 mins)', "");
        document.getElementById("goBtn").innerHTML = '<span class="spinner"></span> Running…';
        pollWorkflow(token);
      }} else if (res.status === 401) {{
        setStatus("Invalid refresh code. Ask Aaron for the correct one.", "err");
        document.getElementById("goBtn").disabled = false;
        document.getElementById("goBtn").textContent = "Update Now";
      }} else {{
        setStatus("Error " + res.status + ". Try again.", "err");
        document.getElementById("goBtn").disabled = false;
        document.getElementById("goBtn").textContent = "Update Now";
      }}
    }} catch(e) {{
      setStatus("Network error — are you online?", "err");
      document.getElementById("goBtn").disabled = false;
      document.getElementById("goBtn").textContent = "Update Now";
    }}
  }}

  async function pollWorkflow(token) {{
    await new Promise(r => setTimeout(r, 8000)); // wait 8s before first check
    var attempts = 0;
    var maxAttempts = 30; // ~5 mins total
    while (attempts < maxAttempts) {{
      try {{
        var res = await fetch(
          "https://api.github.com/repos/" + REPO + "/actions/runs?per_page=1",
          {{ headers: {{ "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json" }} }}
        );
        var data = await res.json();
        var run = data.workflow_runs && data.workflow_runs[0];
        if (run) {{
          if (run.status === "completed") {{
            if (run.conclusion === "success") {{
              setStatus("✓ Done! Page updated — reloading in 3 seconds…", "ok");
              document.getElementById("goBtn").textContent = "Done!";
              setTimeout(() => {{ window.location.href = PAGES_URL + "?t=" + Date.now(); }}, 3000);
            }} else {{
              setStatus("Update finished but something went wrong (conclusion: " + run.conclusion + ").", "err");
              document.getElementById("goBtn").disabled = false;
              document.getElementById("goBtn").textContent = "Try Again";
            }}
            return;
          }} else {{
            var mins = Math.round(attempts * 10 / 60);
            setStatus('<span class="spinner"></span> Still running… (' + (mins > 0 ? mins + " min" : "under 1 min") + ' so far)', "");
          }}
        }}
      }} catch(e) {{ /* ignore poll errors */ }}
      await new Promise(r => setTimeout(r, 10000)); // poll every 10s
      attempts++;
    }}
    setStatus("Taking longer than expected. Check back in a few minutes.", "err");
    document.getElementById("goBtn").disabled = false;
    document.getElementById("goBtn").textContent = "Try Again";
  }}
</script>
</body>
</html>"""


def main():
    print("Loading car data…")
    cars = load_cars()
    if not cars:
        return
    print(f"Embedding {len(cars)} QR codes…")
    html = build_html(cars)
    OUT_FILE.write_text(html, encoding="utf-8")
    size_mb = OUT_FILE.stat().st_size / 1_000_000
    print(f"\nDone!  →  {OUT_FILE}")
    print(f"Size: {size_mb:.1f} MB  |  Send this file to anyone.")


if __name__ == "__main__":
    main()
