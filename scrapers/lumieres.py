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
    """Extrait la date ISO et l'heure depuis un texte type 'Mardi 24 novembre à 18h45'."""
    text = raw_str.lower().replace("\xa0", " ")

    time_match = re.search(r"\b(\d{1,2})[h:](\d{2})\b", text)
    time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}" if time_match else "20:00"

    date_match = re.search(r"(\d{1,2})\s+([a-zéû]+)(?:\s+(\d{4}))?", text)
    if date_match:
        day = int(date_match.group(1))
        month_str = date_match.group(2)
        year = date_match.group(3) or str(datetime.now().year)
        month = MOIS.get(month_str)
        if month:
            return f"{year}-{month}-{day:02d}", time_str

    return None, None

def detect_cinema(header_text: str) -> str:
    """Identifie le cinéma Lumière depuis le bandeau d'en-tête."""
    t = header_text.lower()
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
    main = soup.find("main", id="main-content") or soup
    screenings = []
    seen = set()

    for section in main.find_all("section"):
        wysiwyg = section.find("div", class_="wysiwyg")
        if not wysiwyg:
            continue

        paragraphs = wysiwyg.find_all("p")
        if len(paragraphs) < 2:
            continue

        # 1. En-tête : Date, heure, salle et mention "Séance présentée"
        header_text = paragraphs[0].get_text(" ", strip=True).replace("\xa0", " ")
        date_iso, time_str = parse_date_lumiere(header_text)
        if not date_iso:
            continue

        cinema = detect_cinema(header_text)

        # 2. Titre du film (dans le 2e paragraphe, premier <strong>)
        title_p = paragraphs[1]
        strong_tag = title_p.find("strong")
        title_raw = strong_tag.get_text(" ", strip=True) if strong_tag else title_p.get_text(" ", strip=True)
        title = title_raw.replace("\xa0", " ").strip().lower()
        if not title:
            continue

        # 3. Synopsis (premier paragraphe descriptif hors métadonnées/billetterie)
        description = ""
        for p in paragraphs[2:]:
            p_txt = p.get_text(" ", strip=True).replace("\xa0", " ")
            if not p_txt or len(p_txt) < 40:
                continue
            if any(skip in p_txt.lower() for skip in ["achat conseillé", "lire la suite", "remerciements à", "prix de la mise", "sélection officielle", "quinzaine des"]):
                continue
            description = p_txt
            break

        # 4. Lien de réservation direct (cotecine.fr) ou fiche film
        booking_url = URL_AVP
        cotecine_link = wysiwyg.find("a", href=re.compile(r"cotecine\.fr", re.I))
        film_link = wysiwyg.find("a", href=re.compile(r"/film/"))
        if cotecine_link:
            booking_url = cotecine_link["href"]
        elif film_link:
            href = film_link["href"]
            booking_url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"

        # 5. Affiche du film
        img_tag = section.find("img")
        poster_url = None
        if img_tag:
            poster_url = img_tag.get("src") or img_tag.get("data-src")
            if poster_url and not poster_url.startswith("http"):
                poster_url = f"{BASE_URL}/{poster_url.lstrip('/')}"

        # 6. Détection présence d'équipe / séance présentée
        full_lower = wysiwyg.get_text(" ", strip=True).lower()
        has_cast = 1 if any(k in full_lower for k in ["séance présentée", "en présence", "rencontre avec", "suivi d'un échange", "avec l'équipe"]) else 0

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