import os
import json
import sqlite3
from scrapers import comoedia, ugc

DB_NAME = "avp_lyon.db"
OUTPUT_DIR = "public"
TEMPLATE_PATH = "templates/index.html"

SCRAPERS = [
    comoedia.scrape,
    ugc.scrape,
]

def init_db():
    """Initialise la table SQLite et gère les migrations de colonnes si existante."""
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
                has_cast INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cinema, title, date, time)
            )
        """)
        cursor.execute("PRAGMA table_info(screenings)")
        cols = [c[1] for c in cursor.fetchall()]
        if "poster_url" not in cols:
            cursor.execute("ALTER TABLE screenings ADD COLUMN poster_url TEXT")
        if "has_cast" not in cols:
            cursor.execute("ALTER TABLE screenings ADD COLUMN has_cast INTEGER DEFAULT 0")
        conn.commit()

def scrape_and_update():
    init_db()
    all_screenings = []
    
    for scrape_fn in SCRAPERS:
        items = scrape_fn()
        all_screenings.extend(items)

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        for s in all_screenings:
            # 1. Titre standardisé en minuscules
            clean_title = s['title'].strip().lower()

            # 2. Détection de la présence de l'équipe
            # Recherche dans la description ou les métadonnées fournies
            desc = (s.get('description') or "").lower()
            raw_has_cast = s.get('has_cast')
            
            if raw_has_cast is not None:
                has_cast = 1 if raw_has_cast else 0
            else:
                has_cast = 1 if ("avec équipe" in desc or "en présence" in desc) else 0

            cursor.execute("""
                INSERT INTO screenings (cinema, title, date, time, url, description, poster_url, has_cast, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cinema, title, date, time) DO UPDATE SET
                    url = excluded.url,
                    description = excluded.description,
                    poster_url = excluded.poster_url,
                    has_cast = excluded.has_cast,
                    updated_at = CURRENT_TIMESTAMP
            """, (s['cinema'], clean_title, s['date'], s['time'], s['url'], s['description'], s['poster_url'], has_cast))
        conn.commit()

def generate_static_site():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT cinema, title, date, time, url, description, poster_url, has_cast FROM screenings ORDER BY date ASC, time ASC")
        screenings = [dict(r) for r in cursor.fetchall()]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    screenings_json = json.dumps(screenings, ensure_ascii=False)
    cinemas = sorted(list({s["cinema"] for s in screenings}))
    cinema_options = "".join([f'<option value="{c}">{c}</option>' for c in cinemas])

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("/*__SCREENINGS_DATA__*/", screenings_json)
    html = html.replace("<!--__CINEMA_OPTIONS__-->", cinema_options)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Site généré ({len(screenings)} séances).")

if __name__ == "__main__":
    scrape_and_update()
    generate_static_site()