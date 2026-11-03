import sqlite3
import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

URL = "https://www.cinema-comoedia.com/httpswwwboxofficeprocom/"
BASE_URL = "https://www.cinema-comoedia.com"
DB_NAME = "avp_lyon.db"

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def init_db():
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cinema, title, date, time)
            )
        """)
        conn.commit()

def parse_date_heure(raw_date_str: str):
    pattern = r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})\s+à\s+(\d{2}:\d{2})"
    match = re.search(pattern, raw_date_str.lower())
    if not match:
        return None, None

    day, month_fr, year, time_str = match.groups()
    month = MOIS.get(month_fr)
    if not month:
        return None, None

    date_iso = f"{year}-{month}-{int(day):02d}"
    return date_iso, time_str

def scrape_and_save():
    init_db()
    
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AVP-Lyon-Bot/1.0)"}
    response = httpx.get(URL, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    entries_saved = 0

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        for h2 in soup.find_all("h2"):
            parent_card = h2.find_parent("div")
            if not parent_card:
                continue

            container = parent_card.find_parent("div")
            title = h2.get_text(strip=True)

            date_span = parent_card.find(lambda tag: tag.name == "span" and "à" in tag.text)
            date_iso, time_str = (None, None)
            if date_span:
                date_iso, time_str = parse_date_heure(date_span.get_text(strip=True))

            if not date_iso or not time_str:
                continue

            link_tag = container.find("a", href=re.compile(r"^/events/")) if container else None
            event_url = f"{BASE_URL}{link_tag['href']}" if link_tag else None

            desc_div = parent_card.find_next_sibling("div")
            description = desc_div.get_text(strip=True) if desc_div else ""

            # Insertion avec mise à jour en cas d'existence préalable
            cursor.execute("""
                INSERT INTO screenings (cinema, title, date, time, url, description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cinema, title, date, time) DO UPDATE SET
                    url = excluded.url,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            """, ("Le Comoedia", title, date_iso, time_str, event_url, description))
            
            entries_saved += 1
            
        conn.commit()
        
    print(f"Extraction terminée : {entries_saved} séances traitées dans '{DB_NAME}'.")

if __name__ == "__main__":
    scrape_and_save()