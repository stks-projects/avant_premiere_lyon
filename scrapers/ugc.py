import re
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

UGC_BASE_URL = "https://www.ugc.fr"

# Les cinémas UGC de la Métropole de Lyon
UGC_CINEMAS = [
    {"name": "UGC Part-Dieu", "id": "58"},
    {"name": "UGC Confluence", "id": "59"},
    {"name": "UGC Cité Internationale", "id": "32"},
    {"name": "UGC Astoria", "id": "33"},
]

MOIS_FR = {
    "janv": "01", "févr": "02", "mars": "03", "avril": "04", "mai": "05", "juin": "06",
    "juil": "07", "août": "08", "sept": "09", "oct": "10", "nov": "11", "déc": "12"
}

def parse_ugc_date(tile_element):
    """
    Extrait la vraie date de projection affichée dans la tuile (ex: 'Ven. 6 nov.', '15 nov.').
    Si introuvable, regarde dans les boutons/onglets de date actifs du bloc.
    """
    text = tile_element.get_text(" ", strip=True).lower()
    
    # 1. Recherche d'un motif textuel comme "6 nov" ou "15 novembre"
    match = re.search(r"\b(\d{1,2})\s+([a-zéû]{3,8})\b", text)
    if match:
        day = int(match.group(1))
        month_txt = match.group(2)[:4] # Prendre les 3-4 premières lettres
        for m_key, m_val in MOIS_FR.items():
            if m_key in month_txt:
                current_year = datetime.now().year
                return f"{current_year}-{m_val}-{day:02d}"

    # 2. Recherche d'un format JJ/MM
    match_slash = re.search(r"\b(\d{1,2})/(\d{2})\b", text)
    if match_slash:
        day = int(match_slash.group(1))
        month = match_slash.group(2)
        return f"{datetime.now().year}-{month}-{day:02d}"

    # Fallback : date du jour si introuvable
    return datetime.now().strftime("%Y-%m-%d")

def scrape_cinema(page, cinema: dict):
    url = f"{UGC_BASE_URL}/cinema.html?id={cinema['id']}"
    print(f"[UGC] Chargement de {cinema['name']}...")

    try:
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"[UGC] Erreur chargement {cinema['name']}: {e}")
        return []

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    screenings = []
    seen_titles = set()

    # Sélection de toutes les tuiles de films UGC
    tiles = soup.find_all("div", class_=re.compile(r"component--film-tile", re.I))

    for tile in tiles:
        # Vérification de la présence du badge Avant-première
        tag = tile.find(class_=re.compile(r"film-tag", re.I))
        if not tag:
            continue
        tag_text = tag.get_text(strip=True).lower()
        if "avant-première" not in tag_text and "avant premiere" not in tag_text:
            continue

        # Extraction de l'affiche
        img = tile.find("img")
        poster_url = None
        if img:
            poster_url = img.get("src") or img.get("data-src")
            if poster_url and not poster_url.startswith("http"):
                poster_url = f"{UGC_BASE_URL}/{poster_url.lstrip('/')}"

        # Extraction du titre et du lien de réservation
        links = tile.find_all("a")
        title = None
        movie_url = url
        
        for a in links:
            txt = a.get_text(strip=True)
            href = a.get("href", "")
            txt_lower = txt.lower()

            # Identification du lien de réservation direct
            if txt_lower in ["je réserve", "réserver", "voir la bande annonce"]:
                if href:
                    movie_url = href if href.startswith("http") else f"{UGC_BASE_URL}/{href.lstrip('/')}"
            # Exclusion explicite de "séances" pour ne pas l'attribuer comme titre
            elif txt_lower == "séances":
                if href and movie_url == url:
                    movie_url = href if href.startswith("http") else f"{UGC_BASE_URL}/{href.lstrip('/')}"
            # Premier texte valide retenu comme titre
            elif txt and len(txt) > 1 and not title:
                title = txt
                if href and movie_url == url:
                    movie_url = href if href.startswith("http") else f"{UGC_BASE_URL}/{href.lstrip('/')}"

        # Fallback 1 : balises de titres HTML standard
        if not title or title.lower() in ["séances", "avant-première"]:
            heading = tile.find(["h2", "h3", "h4", "h5"])
            if heading and heading.get_text(strip=True).lower() not in ["séances", "avant-première"]:
                title = heading.get_text(strip=True)

        # Fallback 2 : déduction du titre depuis le slug de l'URL du film
        if (not title or title.lower() in ["séances", "avant-première"]) and "film_" in movie_url:
            slug_match = re.search(r"film_([a-zA-Z0-9\-]+)_\d+", movie_url)
            if slug_match:
                title = slug_match.group(1).replace("-", " ").replace("_", " ").upper()

        if not title or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Extraction de l'heure
        full_text = tile.get_text(" ", strip=True)
        time_matches = re.findall(r"\b([0-2]?[0-9][h:][0-5][0-9])\b", full_text)
        screen_time = time_matches[0].replace("h", ":") if time_matches else "20:00"

        date_iso = parse_ugc_date(tile)

        screenings.append({
            "cinema": cinema["name"],
            "title": title,
            "date": date_iso,
            "time": screen_time,
            "url": movie_url,
            "description": f"{tag.get_text(strip=True)} à l'{cinema['name']}.",
            "poster_url": poster_url
        })

    return screenings

def scrape():
    all_screenings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="fr-FR",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        for cinema in UGC_CINEMAS:
            items = scrape_cinema(page, cinema)
            print(f" -> {len(items)} avant-première(s) trouvée(s) pour {cinema['name']}")
            all_screenings.extend(items)

        browser.close()

    return all_screenings

if __name__ == "__main__":
    results = scrape()
    print(f"\nTotal : {len(results)} séances UGC récupérées.")
    for s in results:
        print(f"[{s['cinema']}] {s['title']} ({s['time']}) -> {s['url']}")