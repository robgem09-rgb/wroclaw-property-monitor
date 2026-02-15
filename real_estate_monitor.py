import os
import time
import sqlite3
import requests
import threading
import json
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup
from http.server import HTTPServer, SimpleHTTPRequestHandler

class RealEstateMonitor:
    def __init__(self):
        self.db_path = 'properties.db'
        self.port = int(os.environ.get('PORT', 10000))
        self.config = {
            'criteria': {
                'min_price': 300000,
                'max_price': 900000,
                'min_area': 30,
                'max_area': 100
            }
        }
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
        url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie,rynek-wtorny/wiele-lokalizacji?limit=36&ownerTypeSingleSelect=ALL&priceMin=350000&priceMax=450000&roomsNumber=%5BONE%2CTWO%5D&locations=%5Bdolnoslaskie%2Fwroclaw%2Fwroclaw%2Fwroclaw%2Fsrodmiescie%2Cdolnoslaskie%2Fwroclaw%2Fwroclaw%2Fwroclaw%2Fstare-miasto%5D&pricePerMeterMin=11000&pricePerMeterMax=15000&by=DEFAULT&direction=DESC"
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
            rows = conn.execute('SELECT * FROM properties ORDER BY first_seen DESC LIMIT 50').fetchall()
        
        table_content = ""
        for r in rows:
            table_content += f"""
            <tr>
                <td><span class="badge {'bg-success' if r['portal']=='otodom' else 'bg-primary'}">{r['portal']}</span></td>
                <td><a href="{r['url']}" target="_blank">{r['title'][:60]}...</a></td>
                <td><strong>{r['price']:,} zł</strong></td>
                <td>{r['area']} m²</td>
                <td>{r['location']}</td>
                <td><small>{r['first_seen'][:16]}</small></td>
            </tr>"""

        html = f"""<!DOCTYPE html><html><head>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/bootstrap.min.css" rel="stylesheet">
            <title>Wroclaw Property Monitor</title></head>
            <body class="container py-4">
                <h2 class="mb-4">Wrocław Property Monitor</h2>
                <table class="table table-striped">
                    <thead><tr><th>Portal</th><th>Tytuł</th><th>Cena</th><th>m²</th><th>Lok.</th><th>Dodano</th></tr></thead>
                    <tbody>{table_content}</tbody>
                </table>
            </body></html>"""
        
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)

    def run_server(self):
        server_address = ('', self.port)
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        print(f"🚀 Server running on port {self.port}", flush=True)
        httpd.serve_forever()

    def start_monitoring(self):
        while True:
            print(f"\n--- Cycle Start: {datetime.now().strftime('%H:%M:%S')} ---", flush=True)
            all_offers = self.scrape_olx() + self.scrape_otodom()
            new_ones = self.save_and_filter(all_offers)
            print(f"✨ Found {len(all_offers)} offers, {len(new_ones)} are NEW.", flush=True)
            self.generate_dashboard()
            time.sleep(1800) # 30 min

if __name__ == "__main__":
    monitor = RealEstateMonitor()
    # Wątek 1: Serwer HTTP
    threading.Thread(target=monitor.run_server, daemon=True).start()
    # Wątek 2: Pętla główna (wątek główny)
    monitor.start_monitoring()