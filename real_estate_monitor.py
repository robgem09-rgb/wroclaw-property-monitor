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

# KLASA WYMUSZAJĄCA POPRAWNE RENDEROWANIE HTML
class MyHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path == "/" or self.path.endswith(".html"):
            self.send_header("Content-Type", "text/html; charset=utf-8")
        super().end_headers()

class RealEstateMonitor:
    def __init__(self):
        # 1. Definicja parametrów bazowych
        self.db_path = 'properties.db'
        self.port = int(os.environ.get('PORT', 10000))
        
        # 2. Konfiguracja z interwałem
        self.config = {
            'update_interval': 1800,  # 30 minut
            'criteria': {
                'min_price': 300000,
                'max_price': 1000000,
                'min_area': 20,
                'max_area': 150
            }
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # 3. Inicjalizacja bazy
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portal TEXT, title TEXT, price REAL, area REAL, 
                    price_per_m2 REAL, location TEXT, url TEXT UNIQUE, 
                    first_seen TEXT, last_seen TEXT
                )
            ''')

    def scrape_otodom(self) -> List[Dict]:
        print("🔍 Pobieranie danych z Otodom...", flush=True)
        found = []
        url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/dolnoslaskie/wroclaw/wroclaw/wroclaw?limit=36&by=DEFAULT&direction=DESC"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.content, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if not script: return []
            
            data = json.loads(script.string)
            items = data['props']['pageProps']['data']['searchAds']['items']
            
            for item in items:
                price = float(item.get('totalPrice', {}).get('value') or 0)
                
                # POPRAWKA METRAŻU: Szukamy w charakterystyce
                area = 0.0
                for char in item.get('characteristics', []):
                    if char.get('key') == 'm':
                        try: area = float(char.get('value').replace(',', '.'))
                        except: pass
                
                if area == 0: # Backup
                    area = float(item.get('area', {}).get('value') or 0)

                found.append({
                    'portal': 'otodom', 'title': item.get('title', ''),
                    'price': price, 'area': area,
                    'price_per_m2': round(price/area, 2) if area > 0 else 0,
                    'location': 'Wrocław',
                    'url': f"https://www.otodom.pl/pl/oferta/{item.get('slug', '')}"
                })
        except Exception as e: print(f"❌ Otodom Error: {e}", flush=True)
        return found

    def scrape_olx(self) -> List[Dict]:
        print("🔍 Pobieranie danych z OLX...", flush=True)
        found = []
        url = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/wroclaw/?search[order]=created_at:desc"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.content, 'html.parser')
            cards = soup.find_all('div', {'data-testid': 'ad-card'})
            for card in cards:
                link = card.find('a', href=True)
                if not link or 'promoted' in link['href']: continue
                full_url = link['href'] if link['href'].startswith('http') else f"https://www.olx.pl{link['href']}"
                price_text = card.find('p', {'data-testid': 'ad-price'}).get_text() if card.find('p', {'data-testid': 'ad-price'}) else "0"
                price = float("".join(filter(str.isdigit, price_text.split(',')[0])))
                found.append({
                    'portal': 'olx', 'title': card.find('h6').get_text() if card.find('h6') else "",
                    'price': price, 'area': 0, 'price_per_m2': 0, 'location': 'Wrocław', 'url': full_url
                })
        except Exception as e: print(f"❌ OLX Error: {e}", flush=True)
        return found

    def save_and_filter(self, properties: List[Dict]):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_ones = []
        with sqlite3.connect(self.db_path) as conn:
            for p in properties:
                if not (self.config['criteria']['min_price'] <= p['price'] <= self.config['criteria']['max_price']):
                    continue
                try:
                    conn.execute('''INSERT INTO properties (portal, title, price, area, price_per_m2, location, url, first_seen, last_seen)
                                    VALUES (?,?,?,?,?,?,?,?,?)''', 
                                    (p['portal'], p['title'], p['price'], p['area'], p['price_per_m2'], p['location'], p['url'], now, now))
                    new_ones.append(p)
                except sqlite3.IntegrityError:
                    conn.execute('UPDATE properties SET last_seen = ? WHERE url = ?', (now, p['url']))
        return new_ones

    def generate_dashboard(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM properties ORDER BY first_seen DESC LIMIT 60').fetchall()
        
        cards = ""
        for r in rows:
            color = "#00b54b" if r['portal'] == 'otodom' else "#002f34"
            cards += f"""
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100 shadow-sm border-0">
                    <div class="card-header bg-white border-0 pt-3 d-flex justify-content-between">
                        <span class="badge" style="background-color: {color}; color: white;">{r['portal'].upper()}</span>
                        <small class="text-muted">#{r['id']}</small>
                    </div>
                    <div class="card-body">
                        <h6 class="card-title fw-bold text-dark">{r['title'][:70]}</h6>
                        <div class="my-2">
                            <span class="h4 text-danger fw-bold">{r['price']:,} zł</span><br>
                            <small class="text-muted">({r['price_per_m2']:,} zł/m²)</small>
                        </div>
                        <p class="mb-1 small"><strong>Powierzchnia:</strong> {r['area']} m²</p>
                        <p class="small text-muted"><i class="bi bi-geo-alt"></i> Wrocław</p>
                    </div>
                    <div class="card-footer bg-light border-0 py-3">
                        <div class="row g-0 text-center small mb-3">
                            <div class="col-6 border-end">DODANO<br><strong>{r['first_seen'][5:16]}</strong></div>
                            <div class="col-6">WIDZIANO<br><strong>{r['last_seen'][5:16]}</strong></div>
                        </div>
                        <a href="{r['url']}" target="_blank" class="btn btn-dark btn-sm w-100">Zobacz ofertę</a>
                    </div>
                </div>
            </div>"""

        html = f"""<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/bootstrap.min.css" rel="stylesheet">
        <title>Wrocław Property</title>
        <style>body{{background-color:#f8f9fa;}} .card{{transition: 0.2s;}} .card:hover{{transform:translateY(-5px);}}</style>
        </head><body><div class="container py-5">
        <h2 class="mb-5 fw-bold text-center">🏠 Wrocław Property Monitor</h2>
        <div class="row">{cards}</div></div></body></html>"""
        
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)

    def run_server(self):
        server_address = ('', self.port)
        httpd = HTTPServer(server_address, MyHandler) # UŻYCIE POPRAWIONEGO HANDLERA
        print(f"🚀 Serwer działa na porcie {self.port}", flush=True)
        httpd.serve_forever()

    def start_monitoring(self):
        while True:
            all_offers = self.scrape_otodom() + self.scrape_olx()
            new_ones = self.save_and_filter(all_offers)
            print(f"✨ Znaleziono {len(all_offers)} ofert, {len(new_ones)} nowych.", flush=True)
            self.generate_dashboard()
            
            interval = self.config.get('update_interval', 1800)
            next_run = datetime.now() + timedelta(seconds=interval)
            print(f"💤 Następny start: {next_run.strftime('%H:%M:%S')}", flush=True)
            time.sleep(interval)

if __name__ == "__main__":
    monitor = RealEstateMonitor()
    threading.Thread(target=monitor.run_server, daemon=True).start()
    monitor.start_monitoring()