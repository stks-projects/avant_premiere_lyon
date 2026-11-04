import re
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

PATHE_BASE_URL = "https://www.pathe.fr"
PATHE_LYON_URL = "https://www.pathe.fr/cinemas/ville/lyon"

PATHE_CINEMAS = [
    {"name": "Pathé Bellecour", "slug": "cinema-pathe-bellecour"},
    {"name": "Pathé Vaise", "slug": "cinema-pathe-vaise"},
    {"name": "Pathé Carré de Soie", "slug": "cinema-pathe-carre-de-soie"},
]

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def parse_pathe_datetime(text: str):
    """
    Extrait la date et l'heure depuis des chaînes comme :
    'Jeu. 05 novembre à 20:30' ou 'Vendredi 13 novembre à 19:45'
    """
    date_match = re.search(r"(\d{1,2})\s+([a-zéû]+)(?:\s+(\d{4}))?", text.lower())
    time_match = re.search(r"\b([0-2]?[0-9][h:][0-5][0-9])\b", text)

    time_str = time_match.group(1).replace("h", ":") if time_match else "20:00"
    if len(time_str) == 4:
        time_str = f"0{time_str}"

    if date_match:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        year = date_match.group(3) or str(datetime.now().year)
        month = MOIS.get(month_name)
        if month:
            return f"{year}-{month}-{day:02d}", time_str

    # Date par défaut si non précisée
    return datetime.now().strftime("%Y-%m-%d"), time_str

def scrape():
    screenings = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR"
        )
        page = context.new_page()

        for cine in PATHE_CINEMAS:
            cinema_name = cine["name"]
            url = f"{PATHE_BASE_URL}/cinemas/{cine['slug']}"
            print(f"[Pathé] Chargement de {cinema_name} ({url})...")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)

                # Gestion de la bannière cookies si affichée
                try:
                    cookie_btn = page.locator("#didomi-notice-agree-button, button:has-text('Continuer sans accepter'), button:has-text('Accepter')").first
                    if cookie_btn.is_visible(timeout=2000):
                        cookie_btn.click()
                        page.wait_for_timeout(800)
                except Exception:
                    pass

                # Clic optionnel sur un onglet "Événements" s'il existe
                try:
                    event_tab = page.locator("a:has-text('Événements'), button:has-text('Événements')").first
                    if event_tab.is_visible(timeout=1500):
                        event_tab.click()
                        page.wait_for_timeout(1500)
                except Exception:
                    pass

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Extraction des cartes ou blocs contenant la mention 'avant-première'
                cards = soup.find_all(lambda t: t.name in ["article", "div", "li"] and 
                                      any(cls in " ".join(t.get("class", [])) for cls in ["card", "film", "event", "show"]) and
                                      "avant-première" in t.get_text().lower())

                # Recherche complémentaire si les conteneurs ont des classes spécifiques
                if not cards:
                    text_matches = soup.find_all(string=re.compile(r"avant-premi[eè]re", re.I))
                    for tm in text_matches:
                        parent = tm.find_parent(["article", "li", "div"])
                        if parent and parent not in cards:
                            cards.append(parent)

                found_for_cinema = 0
                seen_keys = set()

                for card in cards:
                    text = card.get_text(separator=" ", strip=True)
                    if "avant-première" not in text.lower():
                        continue

                    # Titre
                    title_tag = card.find(["h2", "h3", "h4", "strong"])
                    raw_title = title_tag.get_text(strip=True) if title_tag else ""
                    if not raw_title or len(raw_title) < 2:
                        continue

                    # Nettoyage du titre (ex: retirer les préfixes "Avant-première avec équipe : ")
                    clean_title = re.sub(r"^(avant-premi[eè]re|séance spéciale)\s*(avec équipe)?\s*[:|]\s*", "", raw_title, flags=re.I).strip().lower()

                    # Détection présence équipe
                    has_cast = 1 if ("équipe" in text.lower() or "en présence" in text.lower()) else 0

                    # Date et heure
                    date_iso, time_str = parse_pathe_datetime(text)

                    # Lien réservation / fiche
                    link_tag = card.find("a", href=True)
                    booking_url = url
                    if link_tag and link_tag.get("href"):
                        href = link_tag["href"]
                        booking_url = href if href.startswith("http") else f"{PATHE_BASE_URL}{href}"

                    # Affiche
                    img_tag = card.find("img")
                    poster_url = None
                    if img_tag:
                        poster_url = img_tag.get("src") or img_tag.get("data-src")

                    key = (cinema_name, clean_title, date_iso, time_str)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    screenings.append({
                        "cinema": cinema_name,
                        "title": clean_title,
                        "date": date_iso,
                        "time": time_str,
                        "url": booking_url,
                        "description": "",
                        "poster_url": poster_url,
                        "has_cast": has_cast
                    })
                    found_for_cinema += 1

                print(f" -> {found_for_cinema} avant-première(s) trouvée(s) pour {cinema_name}")

            except Exception as e:
                print(f"[Pathé] Erreur sur {cinema_name} : {e}")

        browser.close()

    return screenings

if __name__ == "__main__":
    results = scrape()
    print(f"\nTotal : {len(results)} séances Pathé récupérées.")
    for r in results:
        print(f"[{r['cinema']}] {r['title']} ({r['date']} à {r['time']}) - Équipe: {r['has_cast']}")