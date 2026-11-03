import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

EVENTS_URL = "https://www.ugc.fr/evenements.html"
BASE_URL = "https://www.ugc.fr"

LYON_CINEMAS = {
    "part-dieu": "UGC Part-Dieu",
    "confluence": "UGC Confluence",
    "internationale": "UGC Cité Internationale",
    "astoria": "UGC Astoria"
}

def scrape():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9"
    }
    try:
        resp = httpx.get(EVENTS_URL, headers=headers, follow_redirects=True, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[UGC] Erreur : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []

    avp_heading = soup.find(lambda t: t.name in ["h2", "h3", "div"] and "Avant-Premières" in t.get_text())
    if not avp_heading:
        return []

    section = avp_heading.find_parent("section") or avp_heading.find_parent("div")
    if not section:
        return []

    unique_films = {}
    for a in section.find_all("a", href=re.compile(r"film\.html\?id=")):
        title = a.get_text(strip=True)
        if title and title.lower() not in ["séances", "voir la bande annonce"]:
            unique_films[title] = a["href"]

    for title, link in unique_films.items():
        film_url = f"{BASE_URL}/{link.lstrip('/')}"
        try:
            film_resp = httpx.get(film_url, headers=headers, timeout=15)
            film_soup = BeautifulSoup(film_resp.text, "html.parser")
        except Exception:
            continue

        img_tag = film_soup.find("img", src=re.compile(r"poster|upload|film", re.I))
        poster_url = img_tag["src"] if img_tag else None
        text_page = film_soup.get_text(separator=" ", strip=True)

        for key, cinema_name in LYON_CINEMAS.items():
            if key in text_page.lower():
                screenings.append({
                    "cinema": cinema_name,
                    "title": title,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "time": "20:00",
                    "url": film_url,
                    "description": f"Avant-première programmée à l'{cinema_name}.",
                    "poster_url": poster_url
                })
    return screenings

if __name__ == "__main__":
    results = scrape()
    print(f"{len(results)} séances trouvées pour UGC Lyon")