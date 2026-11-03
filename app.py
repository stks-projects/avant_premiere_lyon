from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import sqlite3

app = FastAPI()
DB_NAME = "avp_lyon.db"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Avant-Premières Lyon</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen p-6 font-sans">
    <div class="max-w-3xl mx-auto">
        <header class="mb-8">
            <h1 class="text-3xl font-extrabold text-amber-400">Avant-Premières Lyon</h1>
            <p class="text-gray-400">Inspiré de premiereprojo.fr — Cinéma Le Comœdia</p>
        </header>

        <!-- Filtre par date -->
        <form method="get" action="/" class="mb-6 flex gap-3 items-center bg-gray-900 p-4 rounded-xl border border-gray-800">
            <label for="date" class="font-medium">Filtrer par date :</label>
            <input type="date" id="date" name="date" value="{{ current_date }}" 
                   class="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white">
            <button type="submit" class="bg-amber-500 hover:bg-amber-600 text-black font-semibold px-4 py-1.5 rounded-lg transition">
                Filtrer
            </button>
            {% if current_date %}
                <a href="/" class="text-sm text-gray-400 hover:underline">Réinitialiser</a>
            {% endif %}
        </form>

        <!-- Liste des séances -->
        <div class="space-y-4">
            {% if not screenings %}
                <p class="text-gray-500">Aucune avant-première trouvée pour cette date.</p>
            {% endif %}
            
            {% for s in screenings %}
            <article class="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition">
                <div class="flex justify-between items-start gap-4">
                    <div>
                        <span class="inline-block text-xs font-semibold uppercase tracking-wider text-amber-400 mb-1">
                            {{ s['cinema'] }} • {{ s['date'] }} à {{ s['time'] }}
                        </span>
                        <h2 class="text-xl font-bold text-white">{{ s['title'] }}</h2>
                    </div>
                    {% if s['url'] %}
                    <a href="{{ s['url'] }}" target="_blank" class="text-sm bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg border border-gray-700 whitespace-nowrap">
                        Réserver ↗
                    </a>
                    {% endif %}
                </div>
                {% if s['description'] %}
                    <p class="mt-3 text-sm text-gray-300 leading-relaxed">{{ s['description'] }}</p>
                {% endif %}
            </article>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

from jinja2 import Template

@app.get("/", response_class=HTMLResponse)
def index(date: str = None):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if date:
            cursor.execute("""
                SELECT * FROM screenings 
                WHERE date = ? 
                ORDER BY time ASC
            """, (date,))
        else:
            cursor.execute("""
                SELECT * FROM screenings 
                ORDER BY date ASC, time ASC
            """)
            
        rows = [dict(row) for row in cursor.fetchall()]

    template = Template(HTML_TEMPLATE)
    return template.render(screenings=rows, current_date=date or "")