import os
import re
import json
import sqlite3
import httpx
from bs4 import BeautifulSoup

URL = "https://www.cinema-comoedia.com/httpswwwboxofficeprocom/"
BASE_URL = "https://www.cinema-comoedia.com"
DB_NAME = "avp_lyon.db"
OUTPUT_DIR = "public"

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            DROP TABLE IF EXISTS screenings
        """)
        conn.execute("""
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

def parse_date_heure(raw_date_str: str):
    pattern = r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})\s+à\s+(\d{2}:\d{2})"
    match = re.search(pattern, raw_date_str.lower())
    if not match:
        return None, None
    day, month_fr, year, time_str = match.groups()
    month = MOIS.get(month_fr)
    if not month:
        return None, None
    return f"{year}-{month}-{int(day):02d}", time_str

def scrape_and_update():
    init_db()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AVP-Lyon-Bot/1.0)"}
    resp = httpx.get(URL, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        for h2 in soup.find_all("h2"):
            parent_card = h2.find_parent("div")
            if not parent_card:
                continue
            container = parent_card.find_parent("div")
            title = h2.get_text(strip=True)

            date_span = parent_card.find(lambda t: t.name == "span" and "à" in t.text)
            date_iso, time_str = (None, None)
            if date_span:
                date_iso, time_str = parse_date_heure(date_span.get_text(strip=True))

            if not date_iso or not time_str:
                continue

            link_tag = container.find("a", href=re.compile(r"^/events/")) if container else None
            event_url = f"{BASE_URL}{link_tag['href']}" if link_tag else None

            desc_div = parent_card.find_next_sibling("div")
            description = desc_div.get_text(strip=True) if desc_div else ""

            # Extraction optionnelle de l'affiche
            img_tag = container.find("img") if container else None
            poster_url = img_tag.get("src") if img_tag else None

            cursor.execute("""
                INSERT INTO screenings (cinema, title, date, time, url, description, poster_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cinema, title, date, time) DO UPDATE SET
                    url = excluded.url,
                    description = excluded.description,
                    poster_url = excluded.poster_url,
                    updated_at = CURRENT_TIMESTAMP
            """, ("Le Comoedia", title, date_iso, time_str, event_url, description, poster_url))
        conn.commit()

def generate_static_site():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT cinema, title, date, time, url, description, poster_url FROM screenings ORDER BY date ASC, time ASC")
        screenings = [dict(r) for r in cursor.fetchall()]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    screenings_json = json.dumps(screenings, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Avant-Premières Lyon</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen py-10 px-4 font-sans">
    <div class="max-w-3xl mx-auto">
        <header class="mb-10 text-center">
            <h1 class="text-4xl font-extrabold text-amber-400 tracking-tight">Avant-Premières Lyon</h1>
            <p class="text-zinc-400 mt-2">Toutes les AVP projetées au Comœdia (Lyon 7)</p>
        </header>

        <!-- Filtre par date -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 mb-8 shadow-lg flex flex-wrap gap-4 items-center justify-between">
            <div class="flex items-center gap-3">
                <label for="date-filter" class="text-sm font-medium text-zinc-300">Filtrer par date :</label>
                <input type="date" id="date-filter" class="bg-zinc-800 border border-zinc-700 text-white rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400">
            </div>
            <button id="reset-btn" class="text-sm text-zinc-400 hover:text-amber-400 transition hidden underline">
                Afficher toutes les dates
            </button>
        </div>

        <!-- Liste des séances -->
        <div id="screenings-list" class="space-y-4"></div>
        <p id="empty-state" class="text-center text-zinc-500 py-12 hidden">Aucune avant-première trouvée pour cette date.</p>
    </div>

    <script>
        const screenings = {screenings_json};
        const listEl = document.getElementById('screenings-list');
        const emptyEl = document.getElementById('empty-state');
        const dateInput = document.getElementById('date-filter');
        const resetBtn = document.getElementById('reset-btn');

        function formatDateFr(isoDate) {{
            const [y, m, d] = isoDate.split('-');
            const date = new Date(y, m - 1, d);
            return date.toLocaleDateString('fr-FR', {{ weekday: 'long', day: 'numeric', month: 'long' }});
        }}

        function render(items) {{
            listEl.innerHTML = '';
            if (items.length === 0) {{
                emptyEl.classList.remove('hidden');
                return;
            }}
            emptyEl.classList.add('hidden');

            items.forEach(s => {{
                const card = document.createElement('article');
                card.className = "bg-zinc-900 border border-zinc-800 rounded-2xl p-5 hover:border-zinc-700 transition flex gap-5 items-start";
                
                const posterHtml = s.poster_url 
                    ? `<img src="${{s.poster_url}}" alt="${{s.title}}" class="w-20 h-28 object-cover rounded-lg shrink-0 border border-zinc-800">`
                    : '';

                card.innerHTML = `
                    ${{posterHtml}}
                    <div class="flex-1">
                        <div class="flex items-center justify-between gap-4">
                            <span class="text-xs font-semibold uppercase tracking-wider text-amber-400">
                                ${{s.cinema}} • ${{formatDateFr(s.date)}} à ${{s.time}}
                            </span>
                            ${{s.url ? `<a href="${{s.url}}" target="_blank" rel="noopener" class="text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 px-3 py-1.5 rounded-lg whitespace-nowrap transition">Détails ↗</a>` : ''}}
                        </div>
                        <h2 class="text-xl font-bold text-white mt-1">${{s.title}}</h2>
                        ${{s.description ? `<p class="mt-2 text-sm text-zinc-300 leading-relaxed">${{s.description}}</p>` : ''}}
                    </div>
                `;
                listEl.appendChild(card);
            }});
        }}

        dateInput.addEventListener('change', (e) => {{
            const val = e.target.value;
            if (val) {{
                resetBtn.classList.remove('hidden');
                const filtered = screenings.filter(s => s.date === val);
                render(filtered);
            }} else {{
                resetBtn.classList.add('hidden');
                render(screenings);
            }}
        }});

        resetBtn.addEventListener('click', () => {{
            dateInput.value = '';
            resetBtn.classList.add('hidden');
            render(screenings);
        }});

        // Affichage initial complet
        render(screenings);
    </script>
</body>
</html>"""

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Site statique généré avec succès dans '{OUTPUT_DIR}/index.html' ({len(screenings)} séances).")

if __name__ == "__main__":
    scrape_and_update()
    generate_static_site()