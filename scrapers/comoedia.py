import re
import httpx
from bs4 import BeautifulSoup

URL = "https://www.cinema-comoedia.com/httpswwwboxofficeprocom/"
BASE_URL = "https://www.cinema-comoedia.com"

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

def parse_date(raw_str: str):
    pattern = r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})\s+à\s+(\d{2}:\d{2})"
    match = re.search(pattern, raw_str.lower())
    if not match:
        return None, None
    day, month_fr, year, time_str = match.groups()
    month = MOIS.get(month_fr)
    return (f"{year}-{month}-{int(day):02d}", time_str) if month else (None, None)

def find_card(h2):
    curr = h2
    while curr and curr.name != '[document]':
        curr = curr.parent
        if curr and curr.find("a", href=re.compile(r"^/events/")) and curr.find("img"):
            return curr
    return None

def scrape():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AVP-Lyon-Bot/1.0)"}
    try:
        resp = httpx.get(URL, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Comœdia] Erreur : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    screenings = []

    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        card = find_card(h2) or h2.find_parent("div").find_parent("div")
        if not card:
            continue

        date_span = card.find(lambda t: t.name == "span" and "à" in t.text)
        if not date_span:
            continue
        date_iso, time_str = parse_date(date_span.get_text(strip=True))
        if not date_iso or not time_str:
            continue

        link = card.find("a", href=re.compile(r"^/events/"))
        img = card.find("img")
        parent_div = h2.find_parent("div")
        desc_div = parent_div.find_next_sibling("div") if parent_div else None

        screenings.append({
            "cinema": "Le Comoedia",
            "title": title,
            "date": date_iso,
            "time": time_str,
            "url": f"{BASE_URL}{link['href']}" if link else None,
            "description": desc_div.get_text(strip=True) if desc_div else "",
            "poster_url": img.get("src") if img else None
        })
    return screenings

if __name__ == "__main__":
    # Test autonome rapide
    results = scrape()
    print(f"{len(results)} séances trouvées pour Comœdia")