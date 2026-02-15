import os
import time
import sqlite3
import requests
import threading
import json
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
from http.server import HTTPServer, SimpleHTTPRequestHandler

class MyHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Wymuszamy kodowanie UTF-8 i typ HTML dla głównej strony
        if self.path == "/" or self.path.endswith(".html"):
            self.send_header("Content-Type", "text/html; charset=utf-8")
        super().end_headers()

class RealEstateMonitor:
    def __init__(self):
        # 1. Najpierw definiujemy ścieżki i parametry podstawowe
        self.db_path = 'properties.db'
        self.port = int(os.environ.get('PORT', 10000))
        
        # 2. Definiujemy konfigurację (w tym interwał aktualizacji)
        self.config = {
            'update_interval': 1800,  # 30 minut w sekundach
            'criteria': {
                'min_price': 300000,
                'max_price': 900000,
                'min_area': 30,
                'max_area': 100
            }
        }
        
        # 3. Inicjalizujemy sesję i bazę danych (teraz self.db_path już istnieje)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'pl-PL,pl;q=0.9'
        })
        
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portal TEXT,
                    title TEXT,
                    price REAL,
                    area REAL,
                    price_per_m2 REAL,
                    location TEXT,
                    url TEXT UNIQUE,
                    first_seen TEXT,
                    last_seen TEXT
                )
            ''')

    def extract_price(self, text: str) -> float:
        try:
            cleaned = "".join(filter(str.isdigit, text.replace(',', '.').split('.')[0]))
            return float(cleaned) if cleaned else 0.0
        except: return 0.0

    def scrape_olx(self) -> List[Dict]:
        print("🔍 Scrapping OLX...", flush=True)
        found = []
        url = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/wroclaw/?search[order]=created_at:desc"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.content, 'html.parser')
            # Nowy selektor OLX 2026
            cards = soup.find_all('div', {'data-testid': 'ad-card'})
            for card in cards:
                link = card.find('a', href=True)
                if not link or 'promoted' in link['href']: continue
                
                full_url = link['href'] if link['href'].startswith('http') else f"https://www.olx.pl{link['href']}"
                title = card.find('h6').get_text(strip=True) if card.find('h6') else ""
                price = self.extract_price(card.find('p', {'data-testid': 'ad-price'}).get_text() if card.find('p', {'data-testid': 'ad-price'}) else "0")
                
                # Uproszczone area (OLX rzadko ma to na liście, bierzemy 0 jeśli brak)
                found.append({
                    'portal': 'olx', 'title': title, 'price': price, 
                    'area': 0, 'price_per_m2': 0, 'location': 'Wrocław', 'url': full_url
                })
        except Exception as e: print(f"❌ OLX Error: {e}", flush=True)
        return found

    def scrape_otodom(self) -> List[Dict]:
        print("🔍 Scrapping Otodom (JSON Method)...", flush=True)
        found = []
        url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie,rynek-wtorny/wiele-lokalizacji?limit=36&ownerTypeSingleSelect=ALL&priceMin=350000&priceMax=450000&roomsNumber=%5BONE%2CTWO%5D&locations=%5Bdolnoslaskie%2Fwroclaw%2Fwroclaw%2Fwroclaw%2Fsrodmiescie%2Cdolnoslaskie%2Fwroclaw%2Fwroclaw%2Fwroclaw%2Fstare-miasto%5D&pricePerMeterMin=11000&pricePerMeterMax=15000&by=DEFAULT&direction=DESC   "
        try:
            res = self.session.get(url, timeout=15)
            if res.status_code != 200:
                print(f"  ❌ Otodom Status: {res.status_code}", flush=True)
                return []

            soup = BeautifulSoup(res.content, 'html.parser')
            script_tag = soup.find('script', id='__NEXT_DATA__')
            
            if not script_tag:
                print("  ❌ Nie znaleziono danych JSON w Otodom", flush=True)
                return []

            json_data = json.loads(script_tag.string)
            
            # Bezpieczne zagłębianie się w strukturę JSON
            try:
                items = json_data['props']['pageProps']['data']['searchAds']['items']
            except (KeyError, TypeError):
                print("  ❌ Błąd struktury JSON w Otodom", flush=True)
                return []
            
            for item in items:
                if not item: continue
                
                # Bezpieczne pobieranie ceny
                price_data = item.get('totalPrice') or {}
                price = float(price_data.get('value') or 0)
                
                # Bezpieczne pobieranie metrażu
                area_data = item.get('area') or {}
                area = float(area_data.get('value') or 0)
                
                # Jeśli cena lub metraż są zerowe, omijamy (często to błędy lub ogłoszenia "Cena do negocjacji")
                if price == 0: continue

                found.append({
                    'portal': 'otodom',
                    'title': item.get('title', 'Brak tytułu'),
                    'price': price,
                    'area': area,
                    'price_per_m2': round(price/area, 2) if area > 0 else 0,
                    'location': 'Wrocław',
                    'url': f"https://www.otodom.pl/pl/oferta/{item.get('slug', '')}"
                })
        except Exception as e: 
            print(f"❌ Otodom Error: {e}", flush=True)
        return found

    def save_and_filter(self, properties: List[Dict]):
        now = datetime.now().isoformat()
        new_items = []
        with sqlite3.connect(self.db_path) as conn:
            for p in properties:
                # Filtracja cenowa
                if not (self.config['criteria']['min_price'] <= p['price'] <= self.config['criteria']['max_price']):
                    continue
                
                cur = conn.execute('SELECT id FROM properties WHERE url = ?', (p['url'],))
                if not cur.fetchone():
                    conn.execute('''
                        INSERT INTO properties (portal, title, price, area, price_per_m2, location, url, first_seen, last_seen)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    ''', (p['portal'], p['title'], p['price'], p['area'], p['price_per_m2'], p['location'], p['url'], now, now))
                    new_items.append(p)
                else:
                    conn.execute('UPDATE properties SET last_seen = ? WHERE url = ?', (now, p['url']))
        return new_items

    def generate_dashboard(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM properties ORDER BY first_seen DESC LIMIT 60').fetchall()
        
        cards_content = ""
        for r in rows:
            # Poprawka formatowania dat, aby uniknąć błędów
            added = r['first_seen'][:16].replace('T', ' ') if r['first_seen'] else "---"
            seen = r['last_seen'][:16].replace('T', ' ') if r['last_seen'] else "---"
            
            portal_bg = "#00b54b" if r['portal'] == 'otodom' else "#002f34"
            
            # Budujemy pojedynczą kolumnę z kartą
            cards_content += f"""
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100 shadow-sm border-0">
                    <div class="card-header d-flex justify-content-between bg-white border-0 pt-3">
                        <span class="badge" style="background-color: {portal_bg}; color: white;">{r['portal'].upper()}</span>
                        <small class="text-muted">ID: #{r['id']}</small>
                    </div>
                    <div class="card-body">
                        <h6 class="card-title fw-bold" style="height: 3rem; overflow: hidden;">{r['title']}</h6>
                        <div class="mb-2">
                            <span class="h4 text-danger fw-bold">{r['price']:,} zł</span><br>
                            <small class="text-muted">({r['price_per_m2']:,} zł/m²)</small>
                        </div>
                        <p class="mb-1 small"><strong>Powierzchnia:</strong> {r['area']} m²</p>
                        <p class="small text-muted"><i class="bi bi-geo-alt"></i> Wrocław</p>
                    </div>
                    <div class="card-footer bg-light border-0">
                        <div class="row g-0 text-center small mb-3">
                            <div class="col-6 border-end">
                                <div class="text-muted" style="font-size: 0.7rem;">DODANO</div>
                                <strong>{added}</strong>
                            </div>
                            <div class="col-6">
                                <div class="text-muted" style="font-size: 0.7rem;">WIDZIANO</div>
                                <strong>{seen}</strong>
                            </div>
                        </div>
                        <a href="{r['url']}" target="_blank" class="btn btn-dark btn-sm w-100">Otwórz ofertę</a>
                    </div>
                </div>
            </div>"""

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Pełny dokument HTML z poprawnym linkowaniem Bootstrapa
        html = f"""<!DOCTYPE html>
        <html lang="pl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/bootstrap.min.css" rel="stylesheet">
            <title>Wrocław Property Monitor</title>
            <style>
                body {{ background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
                .navbar {{ background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
                .card {{ border-radius: 12px; overflow: hidden; transition: all 0.3s ease; }}
                .card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.1) !important; }}
            </style>
        </head>
        <body>
            <nav class="navbar mb-5 py-3">
                <div class="container d-flex justify-content-between align-items-center">
                    <span class="navbar-brand mb-0 h4 fw-bold text-dark">🏠 Property Monitor</span>
                    <span class="badge bg-light text-dark border small">Aktualizacja: {now_str}</span>
                </div>
            </nav>
            <div class="container">
                <div class="row">
                    {cards_content}
                </div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/bootstrap.bundle.min.js"></script>
        </body>
        </html>"""
        
        try:
            with open('index.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"✅ Dashboard generated successfully.", flush=True)
        except Exception as e:
            print(f"❌ HTML Error: {e}", flush=True)

    def run_server(self):
        server_address = ('', self.port)
        # Używamy naszego poprawionego handlera zamiast domyślnego
        httpd = HTTPServer(server_address, MyHandler)
        print(f"🚀 Server running on port {self.port}", flush=True)
        httpd.serve_forever()

    def start_monitoring(self):
        while True:
            print(f"\n--- Start cyklu: {datetime.now().strftime('%H:%M:%S')} ---", flush=True)
            
            all_offers = self.scrape_olx() + self.scrape_otodom()
            new_ones = self.save_and_filter(all_offers)
            
            print(f"✨ Znaleziono {len(all_offers)} ofert, w tym {len(new_ones)} NOWYCH.", flush=True)
            self.generate_dashboard()
            
            # Pobieramy interwał z konfiguracji
            interval = self.config.get('update_interval', 1800)
            next_run = datetime.now() + timedelta(seconds=interval)
            
            print(f"💤 Zasypiam na {interval // 60} minut. Kolejne sprawdzenie o {next_run.strftime('%H:%M:%S')}", flush=True)
            time.sleep(interval)


if __name__ == "__main__":
    monitor = RealEstateMonitor()
    # Wątek 1: Serwer HTTP
    threading.Thread(target=monitor.run_server, daemon=True).start()
    # Wątek 2: Pętla główna (wątek główny)
    monitor.start_monitoring()