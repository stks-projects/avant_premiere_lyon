import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

URL_EVENEMENTS = "https://www.cinemas-lumiere.com/evenements/"
BASE_URL = "https://www.cinemas-lumiere.com"

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def parse_date_lumiere(raw_str: str):
    """Extrait la date et l'heure depuis des textes comme 'Mercredi 12 novembre à 20h30'"""
    date_match = re.search(r"(\d{1,2})\s+([a-zéû]+)(?:\s+(\d{4}))?", raw_str.lower())
    time_match = re.search(r"(\d{1,2})[h:](\d{2})", raw_str.lower())

    time_str = "20:00"
    if time_match:
        time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    if date_match:
        day = int(date_match.group(1))
        month_str = date_match.group(2)
        year = date_match.group(3) or str(datetime.now().year)
        month = MOIS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}", time_str

    return None, None

def scrape():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AVP-Lyon-Bot/1.0)"}
    try:
        resp = httpx.get(URL_EVENEMENTS, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Cinémas Lumière] Erreur chargement : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []
    seen = set()

    # Chaque événement est contenu dans une carte d'article ou div d'événement
    events = soup.find_all(["article", "div"], class_=re.compile(r"event|evenement|post", re.I))

    for ev in events:
        text = ev.get_text(" ", strip=True)
        # On ne garde que les avant-premières
        if "avant-première" not in text.lower() and "avant premiere" not in text.lower():
            continue

        # Titre
        title_tag = ev.find(["h2", "h3", "h4"])
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True).lower()
        title = re.sub(r"^(avant-premi[eè]re\s*:\s*|séance spéciale\s*:\s*)", "", title).strip()

        # Salle Lumière spécifique (Bellecour, Terreaux, Fourmi)
        cinema = "Cinéma Lumière"
        if "terreaux" in text.lower():
            cinema = "Lumière Terreaux"
        elif "bellecour" in text.lower():
            cinema = "Lumière Bellecour"
        elif "fourmi" in text.lower():
            cinema = "Lumière Fourmi"

        # Date et heure
        date_iso, time_str = parse_date_lumiere(text)
        if not date_iso:
            continue

        # Lien et affiche
        link_tag = ev.find("a", href=True)
        booking_url = link_tag["href"] if link_tag else URL_EVENEMENTS
        if not booking_url.startswith("http"):
            booking_url = f"{BASE_URL}/{booking_url.lstrip('/')}"

        img_tag = ev.find("img")
        poster_url = None
        if img_tag:
            poster_url = img_tag.get("src") or img_tag.get("data-src")

        has_cast = 1 if ("en présence" in text.lower() or "rencontre avec" in text.lower()) else 0

        key = (cinema, title, date_iso, time_str)
        if key in seen:
            continue
        seen.add(key)

        screenings.append({
            "cinema": cinema,
            "title": title,
            "date": date_iso,
            "time": time_str,
            "url": booking_url,
            "description": "",
            "poster_url": poster_url,
            "has_cast": has_cast
        })

    return screenings

if __name__ == "__main__":
    items = scrape()
    print(f"[Cinémas Lumière] {len(items)} avant-première(s) trouvée(s).")
    for s in items:
        print(f"[{s['cinema']}] {s['title']} ({s['date']} {s['time']}) - Équipe: {s['has_cast']}")