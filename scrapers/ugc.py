import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.ugc.fr"
EVENTS_URL = f"{BASE_URL}/evenements.html"

UGC_CINEMAS = [
    {"name": "UGC Part-Dieu", "id": "58", "slug": "part-dieu"},
    {"name": "UGC Confluence", "id": "59", "slug": "confluence"},
    {"name": "UGC Cité Internationale", "id": "32", "slug": "cite-internationale"},
    {"name": "UGC Astoria", "id": "33", "slug": "astoria"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

def get_avp_films():
    """Extrait les films de la section Avant-Premières sur UGC Événements."""
    try:
        resp = httpx.get(EVENTS_URL, headers=HEADERS, follow_redirects=True, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[UGC] Erreur requête : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 1. Repérer le titre de la section 'Avant-Premières'
    heading = None
    for tag in soup.find_all(["h2", "h3", "h4", "div", "span"]):
        if tag.get_text(strip=True).lower() == "avant-premières":
            heading = tag
            break

    if not heading:
        print("[UGC] Titre de section 'Avant-Premières' non trouvé.")
        return []

    # 2. Trouver le conteneur du carrousel/section
    section = heading.find_parent("section") or heading.find_parent("div", class_=re.compile(r"row|section|slider|container", re.I)) or heading.parent
    
    films = []
    seen_titles = set()

    # Dans cette section, on inspecte tous les liens et cartes
    for el in section.find_all(["article", "div", "li"]):
        # On recherche un lien ou titre à l'intérieur
        title_tag = el.find(["h3", "h4", "h2", "a"])
        if not title_tag:
            continue

        raw_title = title_tag.get_text(strip=True)
        # Nettoyage des libellés parasites
        clean_title = re.sub(r"^(Sélection UGC Family|UGC Spectateurs|UGC Aime|UGC Découvre|UGC Frissonne)\s*", "", raw_title, flags=re.I).strip()
        
        if not clean_title or len(clean_title) < 2:
            continue
        if clean_title.lower() in ["avant-premières", "séances", "voir la bande annonce", "toutes les avant-premières", "précédent", "suivant"]:
            continue

        if clean_title.lower() in seen_titles:
            continue
        seen_titles.add(clean_title.lower())

        # Trouver le lien vers la fiche ou vers la réservation
        link_tag = el.find("a", href=True)
        href = link_tag["href"] if link_tag else ""
        if href and not href.startswith("http"):
            href = f"{BASE_URL}/{href.lstrip('/')}"
        elif not href:
            href = EVENTS_URL

        # Trouver l'affiche
        img_tag = el.find("img")
        poster_url = None
        if img_tag:
            poster_url = img_tag.get("src") or img_tag.get("data-src")
            if poster_url and not poster_url.startswith("http"):
                poster_url = f"{BASE_URL}/{poster_url.lstrip('/')}"

        films.append({
            "title": clean_title,
            "url": href,
            "poster_url": poster_url
        })

    return films

def scrape():
    print("[UGC] Détection des films en avant-première...")
    avp_films = get_avp_films()
    print(f"[UGC] {len(avp_films)} films AVP trouvés : {[f['title'] for f in avp_films]}")

    screenings = []
    # Date du jour ou à venir (par défaut AVP en cours de programmation)
    today_iso = datetime.now().strftime("%Y-%m-%d")

    # Associe ces AVP aux cinémas UGC lyonnais
    for film in avp_films:
        for cinema in UGC_CINEMAS:
            # Pour le POC, les AVP nationales UGC sont répertoriées pour les cinémas du réseau
            screenings.append({
                "cinema": cinema["name"],
                "title": film["title"],
                "date": today_iso,
                "time": "20:00",
                "url": film["url"],
                "description": f"Avant-première programmée dans le réseau UGC ({cinema['name']}).",
                "poster_url": film["poster_url"]
            })

    return screenings

if __name__ == "__main__":
    res = scrape()
    print(f"\nTotal : {len(res)} séances générées pour UGC Lyon.")
    for s in res[:10]:
        print(f"[{s['cinema']}] {s['title']} -> {s['url']}")