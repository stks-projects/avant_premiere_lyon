import os
import re
import json
import sqlite3
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

DB_NAME = "avp_lyon.db"
OUTPUT_DIR = "public"
TEMPLATE_PATH = "templates/index.html"

# Configuration Comœdia
COMOEDIA_URL = "https://www.cinema-comoedia.com/httpswwwboxofficeprocom/"
COMOEDIA_BASE = "https://www.cinema-comoedia.com"

# Les 4 cinémas UGC de la Métropole de Lyon
UGC_CINEMAS = [
    {"name": "UGC Part-Dieu", "id": "58"},
    {"name": "UGC Confluence", "id": "59"},
    {"name": "UGC Cité Internationale", "id": "32"},
    {"name": "UGC Astoria", "id": "33"},
]
UGC_BASE_URL = "https://www.ugc.fr"

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def init_db():
    """Initialise la table SQLite et ajoute la colonne poster_url si nécessaire."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screenings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cinema TEXT NOT NULL,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                url TEXT,
                description TEXT,
                poster_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cinema, title, date, time)
            )
        """)
        cursor.execute("PRAGMA table_info(screenings)")
        cols = [c[1] for c in cursor.fetchall()]
        if "poster_url" not in cols:
            cursor.execute("ALTER TABLE screenings ADD COLUMN poster_url TEXT")
        conn.commit()

# --- 1. Scraper Le Comœdia ---

def parse_date_comoedia(raw_date_str: str):
    pattern = r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})\s+à\s+(\d{2}:\d{2})"
    match = re.search(pattern, raw_date_str.lower())
    if not match:
        return None, None
    day, month_fr, year, time_str = match.groups()
    month = MOIS.get(month_fr)
    if not month:
        return None, None
    return f"{year}-{month}-{int(day):02d}", time_str

def find_comoedia_card(h2_tag):
    """Remonte dans le DOM pour trouver le conteneur englobant l'image et les infos."""
    curr = h2_tag
    while curr and curr.name != '[document]':
        curr = curr.parent
        if not curr:
            break
        if curr.find("a", href=re.compile(r"^/events/")) and curr.find("img"):
            return curr
    return None

def scrape_comoedia():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AVP-Lyon-Bot/1.0)"}
    try:
        resp = httpx.get(COMOEDIA_URL, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erreur Comœdia : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []

    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        card = find_comoedia_card(h2) or h2.find_parent("div").find_parent("div")

        date_span = card.find(lambda t: t.name == "span" and "à" in t.text)
        if not date_span:
            continue
        date_iso, time_str = parse_date_comoedia(date_span.get_text(strip=True))
        if not date_iso or not time_str:
            continue

        link_tag = card.find("a", href=re.compile(r"^/events/"))
        event_url = f"{COMOEDIA_BASE}{link_tag['href']}" if link_tag else None

        img_tag = card.find("img")
        poster_url = img_tag.get("src") if img_tag else None

        parent_div = h2.find_parent("div")
        desc_div = parent_div.find_next_sibling("div") if parent_div else None
        description = desc_div.get_text(strip=True) if desc_div else ""

        screenings.append({
            "cinema": "Le Comoedia",
            "title": title,
            "date": date_iso,
            "time": time_str,
            "url": event_url,
            "description": description,
            "poster_url": poster_url
        })
    return screenings

# --- 2. Scraper UGC ---

def scrape_single_ugc(cinema_name: str, cinema_id: str):
    url = f"{UGC_BASE_URL}/cinema.html?id={cinema_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9"
    }
    try:
        resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erreur UGC {cinema_name} : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []

    film_titles = soup.find_all(["h2", "h3"])
    for title_tag in film_titles:
        container = title_tag.find_parent("article") or title_tag.find_parent("div", class_=re.compile(r"film|card", re.I))
        if not container:
            continue

        text_content = container.get_text(separator=" ", strip=True)
        if "avant-première" not in text_content.lower():
            continue

        title = title_tag.get_text(strip=True)
        if not title:
            continue

        img_tag = container.find("img")
        poster_url = img_tag.get("src") or img_tag.get("data-src") if img_tag else None

        link_tag = container.find("a", href=re.compile(r"film\.html\?id="))
        movie_url = f"{UGC_BASE_URL}/{link_tag['href'].lstrip('/')}" if link_tag else url

        time_matches = re.findall(r"\b([0-2]?[0-9][h:][0-5][0-9])\b", text_content)
        screen_time = time_matches[0].replace("h", ":") if time_matches else "20:00"
        date_iso = datetime.now().strftime("%Y-%m-%d")

        screenings.append({
            "cinema": cinema_name,
            "title": title,
            "date": date_iso,
            "time": screen_time,
            "url": movie_url,
            "description": f"Avant-première programmée à l'{cinema_name}.",
            "poster_url": poster_url
        })
    return screenings

# --- 3. Pipeline global de Scraping & Mise à jour SQLite ---

def scrape_and_update():
    init_db()
    all_screenings = []

    # Scraping Comœdia
    comoedia_items = scrape_comoedia()
    print(f"Comœdia : {len(comoedia_items)} séances trouvées.")
    all_screenings.extend(comoedia_items)

    # Scraping des cinémas UGC
    for ugc in UGC_CINEMAS:
        ugc_items = scrape_single_ugc(ugc["name"], ugc["id"])
        print(f"{ugc['name']} : {len(ugc_items)} séances trouvées.")
        all_screenings.extend(ugc_items)

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        for s in all_screenings:
            cursor.execute("""
                INSERT INTO screenings (cinema, title, date, time, url, description, poster_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cinema, title, date, time) DO UPDATE SET
                    url = excluded.url,
                    description = excluded.description,
                    poster_url = excluded.poster_url,
                    updated_at = CURRENT_TIMESTAMP
            """, (s['cinema'], s['title'], s['date'], s['time'], s['url'], s['description'], s['poster_url']))
        conn.commit()

# --- 4. Génération de la page statique via templates/index.html ---

def generate_static_site():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT cinema, title, date, time, url, description, poster_url FROM screenings ORDER BY date ASC, time ASC")
        screenings = [dict(r) for r in cursor.fetchall()]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    screenings_json = json.dumps(screenings, ensure_ascii=False)

    cinemas = sorted(list({s["cinema"] for s in screenings}))
    cinema_options = "".join([f'<option value="{c}">{c}</option>' for c in cinemas])

    # Lecture du template HTML externe
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Remplacement des balises cibles
    html_content = html_content.replace("/*__SCREENINGS_DATA__*/", screenings_json)
    html_content = html_content.replace("<!--__CINEMA_OPTIONS__-->", cinema_options)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Génération terminée dans '{OUTPUT_DIR}/index.html' ({len(screenings)} séances au total).")

if __name__ == "__main__":
    scrape_and_update()
    generate_static_site()