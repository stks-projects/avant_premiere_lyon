import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

URL_AVP = "https://www.cinemas-lumiere.com/avant-premieres"
BASE_URL = "https://www.cinemas-lumiere.com"

MOIS = {
    "janvier": "01", "février": "02", "fevrier": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "août": "08", "aout": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "décembre": "12", "decembre": "12"
}

def parse_date_lumiere(raw_str: str):
    """Extrait la date ISO et l'heure depuis un texte type 'Mercredi 25 novembre 2026 à 20h30' ou '25/11 à 20:30'."""
    text = raw_str.lower()
    
    # Extraction de l'heure (ex: 20h30, 20:30, 20h)
    time_match = re.search(r"\b(\d{1,2})[h:](\d{2})?\b", text)
    time_str = "20:00"
    if time_match:
        hour = int(time_match.group(1))
        minute = time_match.group(2) or "00"
        time_str = f"{hour:02d}:{minute}"

    # Format littéral : "25 novembre" ou "25 novembre 2026"
    date_match = re.search(r"(\d{1,2})\s+([a-zéû]+)(?:\s+(\d{4}))?", text)
    if date_match:
        day = int(date_match.group(1))
        month_str = date_match.group(2)
        year = date_match.group(3) or str(datetime.now().year)
        month = MOIS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}", time_str

    # Format numérique : "25/11" ou "25/11/2026"
    num_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if num_match:
        day = int(num_match.group(1))
        month = int(num_match.group(2))
        year = num_match.group(3) or str(datetime.now().year)
        if len(year) == 2:
            year = f"20{year}"
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}", time_str

    return None, None

def detect_cinema(text: str) -> str:
    """Identifie la salle du réseau Lumière mentionnée dans la carte."""
    t = text.lower()
    if "terreaux" in t:
        return "Lumière Terreaux"
    if "bellecour" in t:
        return "Lumière Bellecour"
    if "fourmi" in t:
        return "Lumière Fourmi"
    return "Cinémas Lumière"

def scrape():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9"
    }
    try:
        resp = httpx.get(URL_AVP, headers=headers, follow_redirects=True, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Cinémas Lumière] Erreur chargement : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []
    seen = set()

    # On cible les conteneurs d'articles/cartes contenant un titre (h2, h3, h4)
    title_tags = soup.find_all(["h2", "h3", "h4"])

    for title_tag in title_tags:
        title_raw = title_tag.get_text(" ", strip=True)
        if not title_raw or len(title_raw) < 2:
            continue

        # Remonte jusqu'à la carte englobante
        card = (
            title_tag.find_parent("article")
            or title_tag.find_parent("div", class_=re.compile(r"event|evenement|film|movie|card|item|post|bloc", re.I))
            or title_tag.find_parent("div")
        )
        if not card:
            continue

        full_text = card.get_text(" ", strip=True)

        # Extraction date & heure
        date_iso, time_str = parse_date_lumiere(full_text)
        if not date_iso:
            continue

        # Nettoyage du titre
        title = title_raw.lower()
        title = re.sub(r"^(avant-premi[eè]re\s*[:\-–]\s*|avp\s*[:\-–]\s*|séance spéciale\s*[:\-–]\s*)", "", title).strip()

        # Identification du cinéma (Bellecour, Terreaux, Fourmi)
        cinema = detect_cinema(full_text)

        # Lien vers la fiche ou réservation
        link_tag = card.find("a", href=True)
        booking_url = link_tag["href"] if link_tag else URL_AVP
        if not booking_url.startswith("http"):
            booking_url = f"{BASE_URL}/{booking_url.lstrip('/')}"

        # Affiche du film
        img_tag = card.find("img")
        poster_url = None
        if img_tag:
            poster_url = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src")
            if poster_url and not poster_url.startswith("http"):
                poster_url = f"{BASE_URL}/{poster_url.lstrip('/')}"

        # Détection présence d'équipe / invités
        t_lower = full_text.lower()
        has_cast = 1 if any(k in t_lower for k in ["en présence", "rencontre avec", "suivi d'un échange", "suivie d'un débat", "avec l'équipe"]) else 0

        # Extraction d'une éventuelle description courte (hors titre)
        desc_tag = card.find("p")
        description = desc_tag.get_text(" ", strip=True) if desc_tag else ""
        if description.lower() == title:
            description = ""

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
            "description": description,
            "poster_url": poster_url,
            "has_cast": has_cast
        })

    return screenings

if __name__ == "__main__":
    results = scrape()
    print(f"[Cinémas Lumière] {len(results)} avant-première(s) trouvée(s).")
    for s in results:
        print(f"[{s['cinema']}] {s['title']} ({s['date']} {s['time']}) - Équipe: {s['has_cast']} -> {s['url']}")
