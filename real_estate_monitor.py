#!/usr/bin/env python3
"""
System monitorowania rynku nieruchomości - Wrocław
Śledzi ogłoszenia z Otodom, OLX i Gratka
"""

import requests
from bs4 import BeautifulSoup
import json
import sqlite3
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hashlib
import re
from typing import List, Dict, Optional
import schedule
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import os

def start_http_server():
    """Uruchamia prosty serwer HTTP dla dashboard (dla Render.com)"""
    port = int(os.getenv('PORT', 8000))
    
    class CustomHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # Serwuj pliki z bieżącego katalogu
            super().__init__(*args, directory=os.getcwd(), **kwargs)
        
        def log_message(self, format, *args):
            # Cichszy logging
            pass
    
    try:
        server = HTTPServer(('0.0.0.0', port), CustomHandler)
        print(f"🌐 Dashboard HTTP serwer uruchomiony na porcie {port}", flush=True)
        print(f"   Dostęp: http://localhost:{port}/dashboard.html", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"⚠️  Nie udało się uruchomić serwera HTTP: {e}")

class RealEstateMonitor:
    def __init__(self, config_file='config.json'):
        """Inicjalizacja monitora"""
        self.load_config(config_file)
        print("DEBUG: Skrypt wystartował 1", flush=True)
        self.init_database()
        print("DEBUG: Skrypt wystartował 2", flush=True)
        self.session = requests.Session()
        print("DEBUG: Skrypt wystartował 3", flush=True)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def load_config(self, config_file):
        """Ładuje konfigurację z pliku JSON lub zmiennych środowiskowych"""
        import os
        
        # Sprawdź czy są zmienne środowiskowe (Render.com, Railway, itp.)
        if os.getenv('EMAIL_SENDER'):
            print("📡 Używam konfiguracji ze zmiennych środowiskowych (Cloud)", flush=True)
            self.config = {
                "criteria": {
                    "min_price": int(os.getenv('MIN_PRICE', '200000')),
                    "max_price": int(os.getenv('MAX_PRICE', '500000')),
                    "min_area": float(os.getenv('MIN_AREA', '35')),
                    "max_area": float(os.getenv('MAX_AREA', '70')),
                    "city": "Wrocław",
                    "districts": []
                },
                "notifications": {
                    "email": {
                        "enabled": True,
                        "smtp_server": "smtp.gmail.com",
                        "smtp_port": 587,
                        "sender": os.getenv('EMAIL_SENDER'),
                        "password": os.getenv('EMAIL_PASSWORD'),
                        "recipients": [r.strip() for r in os.getenv('EMAIL_RECIPIENT', os.getenv('EMAIL_SENDER')).split(',')]
                    },
                    "telegram": {
                        "enabled": os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true',
                        "bot_token": os.getenv('TELEGRAM_BOT_TOKEN', ''),
                        "chat_id": os.getenv('TELEGRAM_CHAT_ID', '')
                    }
                },
                "check_interval_minutes": int(os.getenv('CHECK_INTERVAL', '60')),
                "portals": os.getenv('PORTALS', 'otodom,olx,gratka').split(',')
            }
        else:
            # Używa pliku config.json (lokalnie)
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except FileNotFoundError:
                print(f"Brak pliku {config_file}. Tworzę domyślną konfigurację...", flush=True)
                self.config = self.create_default_config()
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def create_default_config(self):
        """Tworzy domyślną konfigurację"""
        return {
            "criteria": {
                "min_price": 200000,
                "max_price": 500000,
                "min_area": 35,
                "max_area": 70,
                "city": "Wrocław",
                "districts": []  # puste = wszystkie dzielnice
            },
            "notifications": {
                "email": {
                    "enabled": True,
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "sender": "twoj_email@gmail.com",
                    "password": "twoje_haslo_aplikacji",
                    "recipients": ["twoj_email@gmail.com"]
                },
                "telegram": {
                    "enabled": False,
                    "bot_token": "your_bot_token",
                    "chat_id": "your_chat_id"
                }
            },
            "check_interval_minutes": 30,
            "portals": ["otodom", "olx", "gratka"]
        }
    
    def init_database(self):
        """Inicjalizuje bazę danych SQLite"""
        self.conn = sqlite3.connect('properties.db')
        self.cursor = self.conn.cursor()
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id TEXT PRIMARY KEY,
                portal TEXT,
                title TEXT,
                price REAL,
                area REAL,
                price_per_m2 REAL,
                location TEXT,
                url TEXT,
                description TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                image_url TEXT,
                is_active INTEGER DEFAULT 1,
                price_history TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id TEXT,
                notification_type TEXT,
                sent_at TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        ''')
        
        self.conn.commit()
    
    def generate_property_id(self, portal: str, url: str) -> str:
        """Generuje unikalny ID dla nieruchomości"""
        return hashlib.md5(f"{portal}:{url}".encode()).hexdigest()
    
    def extract_price(self, text: str) -> Optional[float]:
        """Wyciąga cenę z tekstu"""
        if not text:
            return None
        # Usuwa wszystko oprócz cyfr
        price_str = re.sub(r'[^\d]', '', text)
        try:
            return float(price_str) if price_str else None
        except ValueError:
            return None
    
    def extract_area(self, text: str) -> Optional[float]:
        """Wyciąga metraż z tekstu"""
        if not text:
            return None
        # Szuka wzorca typu "45 m²" lub "45m2"
        match = re.search(r'(\d+[.,]?\d*)\s*m', text.lower())
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                return None
        return None
    def scrape_otodom(self) -> List[Dict]:
        """Zbiera oferty z Otodom"""
        properties = []
        criteria = self.config.get('criteria', {
            'min_price': 0, 'max_price': 99999999, 
            'min_area': 0, 'max_area': 999
        })
        
        print(f"🔍 Szukam na Otodom...", flush=True)
        
        try:
            # URL dla Wrocławia, sortowanie od najnowszych
            base_url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/dolnoslaskie/wroclaw/wroclaw/wroclaw?limit=36&ownerTypeSingleSelect=ALL&by=DEFAULT&direction=DESC&viewType=listing"
            
            response = self.session.get(base_url, timeout=15)
            print(f"  DEBUG: Status odpowiedzi Otodom: {response.status_code}", flush=True)
            
            if response.status_code != 200:
                print(f"  ✗ Otodom zablokował zapytanie (Status: {response.status_code})", flush=True)
                return []
    
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # METODA 1: Szukanie po selektorach danych (data-cy)
            listings = soup.find_all('li', {'data-cy': 'listing-item'})
            print(f"  DEBUG: Znaleziono li[data-cy]: {len(listings)}", flush=True)
    
            # METODA 2: Jeśli Metoda 1 zawiedzie, szukamy w skrypcie JSON (najbardziej stabilne)
            if not listings:
                print("  DEBUG: Próbuję metody JSON fallback...", flush=True)
                import json
                next_data = soup.find('script', id='__NEXT_DATA__')
                if next_data:
                    data = json.loads(next_data.string)
                    # Ścieżka do ofert w JSON Otodom może być głęboka, to jest uproszczony schemat:
                    try:
                        items = data['props']['pageProps']['data']['searchAds']['items']
                        print(f"  DEBUG: Znaleziono {len(items)} ofert w JSON", flush=True)
                        # Tutaj musiałbyś przemapować JSON na swój format słownika
                    except KeyError:
                        pass
    
            for listing in listings:
                try:
                    # Wyciąganie linku - kluczowe dla Otodom
                    link_elem = listing.find('a', {'data-cy': 'listing-item-link'})
                    if not link_elem: continue
                    
                    url = 'https://www.otodom.pl' + link_elem['href']
                    
                    # Cena
                    price_elem = listing.find('span', {'data-cy': 'listing-item-price'})
                    price_text = price_elem.get_text(strip=True) if price_elem else "0"
                    price = self.extract_price(price_text)
                    
                    # Tytuł i Metraż
                    title_elem = listing.find('p', {'data-cy': 'listing-item-title'})
                    title = title_elem.get_text(strip=True) if title_elem else "Brak tytułu"
                    
                    # Metraż w Otodom często jest w osobnym span
                    area_elem = listing.find('span', {'data-cy': 'listing-item-area'})
                    if area_elem:
                        area = self.extract_area(area_elem.get_text())
                    else:
                        area = self.extract_area(title)
    
                    # Filtrowanie
                    if price and criteria['min_price'] <= price <= criteria['max_price']:
                        if not criteria['min_area'] or (area and area >= criteria['min_area']):
                            properties.append({
                                'portal': 'otodom',
                                'title': title,
                                'price': price,
                                'area': area if area else 0,
                                'price_per_m2': round(price / area, 2) if area and area > 0 else 0,
                                'location': 'Wrocław',
                                'url': url,
                                'description': '',
                                'image_url': ''
                            })
    
                    if len(properties) >= 30: break
    
                except Exception as e:
                    print(f"    ⚠️ Błąd przy ofercie Otodom: {e}", flush=True)
                    continue
    
            print(f"  ✓ Sukces! Znaleziono {len(properties)} ofert z Otodom", flush=True)
    
        except Exception as e:
            print(f"  ✗ Błąd krytyczny scrape_otodom: {e}", flush=True)
        
        return properties
            
    def scrape_olx(self) -> List[Dict]:
        """Zbiera oferty z OLX"""
        properties = []
        # Pobieranie kryteriów z obsługą błędów, jeśli klucze nie istnieją
        criteria = self.config.get('criteria', {
            'min_price': 0, 'max_price': 99999999, 
            'min_area': 0, 'max_area': 999
        })
        
        print(f"🔍 Szukam na OLX...", flush=True)
        
        try:
            # URL OLX dla Wrocławia - dodajemy sortowanie po najnowszych, by szybciej widzieć zmiany
            base_url = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/wroclaw/?search[order]=created_at:desc"
            
            # Ustawienie timeout i sprawdzenie statusu
            response = self.session.get(base_url, timeout=15)
            print(f"  DEBUG: Status odpowiedzi OLX: {response.status_code}", flush=True)
            
            if response.status_code != 200:
                print(f"  ✗ OLX zablokował zapytanie (Status: {response.status_code})", flush=True)
                return []
    
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # AKTUALIZACJA: OLX używa teraz głównie data-testid="ad-card"
            listings = soup.find_all('div', {'data-testid': 'ad-card'})
            
            # Jeśli nie znaleziono przez testid, spróbujmy przez ogólny kontener (fallback)
            if not listings:
                listings = soup.select('div[data-cy="l-card"]')
    
            print(f"  DEBUG: Znaleziono surowych kontenerów: {len(listings)}", flush=True)
            
            for listing in listings:
                try:
                    # Szukamy linku i tytułu (tytuł jest zazwyczaj w h6 lub h3)
                    link_elem = listing.find('a', href=True)
                    title_elem = listing.find('h6') or listing.find('h3')
                    price_elem = listing.find('p', {'data-testid': 'ad-price'})
                    
                    if not all([link_elem, price_elem]):
                        continue
                    
                    url = link_elem['href']
                    if not url.startswith('http'):
                        url = 'https://www.olx.pl' + url
                    
                    # Omijamy "Wyróżnione" (często duplikaty lub reklamy spoza Wrocławia)
                    if 'promoted' in url:
                        continue
    
                    title = title_elem.get_text(strip=True) if title_elem else "Brak tytułu"
                    raw_price = price_elem.get_text(strip=True)
                    price = self.extract_price(raw_price)
                    
                    # Wyciąganie metrażu - jeśli nie ma w tytule, szukamy w dodatkowych tagach p
                    area = self.extract_area(title)
                    if not area:
                        # Szukamy tekstu typu "60 m²" wewnątrz ogłoszenia
                        details_text = listing.get_text(" ")
                        area = self.extract_area(details_text)
    
                    # Logika filtracji
                    if price and criteria['min_price'] <= price <= criteria['max_price']:
                        # Jeśli nie udało się znaleźć metrażu, przypisujemy 1, żeby nie dzielić przez zero
                        # lub by nie odrzucać oferty (zależnie od Twojej strategii)
                        valid_area = (area and criteria['min_area'] <= area <= criteria['max_area'])
                        
                        if valid_area or area is None: 
                            properties.append({
                                'portal': 'olx',
                                'title': title,
                                'price': price,
                                'area': area if area else 0,
                                'price_per_m2': round(price / area, 2) if area else 0,
                                'location': 'Wrocław',
                                'url': url,
                                'description': '',
                                'image_url': ''
                            })
                            
                    if len(properties) >= 20: break # Limit na jeden przebieg
    
                except Exception as e:
                    # Logujemy błąd konkretnej oferty, ale lecimy dalej
                    print(f"    ⚠️ Błąd przy ofercie: {e}", flush=True)
                    continue
                    
            print(f"  ✓ Sukces! Znaleziono {len(properties)} ofert spełniających kryteria", flush=True)
    
        except Exception as e:
            print(f"  ✗ Błąd krytyczny scrape_olx: {e}", flush=True)
        
        return properties
  
    def scrape_gratka(self) -> List[Dict]:
        """Zbiera oferty z Gratka"""
        properties = []
        criteria = self.config['criteria']
        
        print(f"🔍 Szukam na Gratka...")
        
        try:
            base_url = "https://gratka.pl/nieruchomosci/mieszkania/dolnoslaskie/wroclaw/sprzedaz"
            
            response = self.session.get(base_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                listings = soup.find_all('article', class_='teaserUnified')
                
                for listing in listings[:20]:
                    try:
                        title_elem = listing.find('h2')
                        price_elem = listing.find('span', class_='teaserUnified__price')
                        link_elem = listing.find('a', href=True)
                        params = listing.find_all('li', class_='teaserUnified__param')
                        
                        if not all([title_elem, price_elem, link_elem]):
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        url = link_elem['href']
                        
                        # Szuka metrażu w parametrach
                        area = None
                        for param in params:
                            if 'm²' in param.get_text():
                                area = self.extract_area(param.get_text())
                                break
                        
                        if not url.startswith('http'):
                            url = 'https://gratka.pl' + url
                        
                        if price and price >= criteria['min_price'] and price <= criteria['max_price']:
                            if area and area >= criteria['min_area'] and area <= criteria['max_area']:
                                properties.append({
                                    'portal': 'gratka',
                                    'title': title,
                                    'price': price,
                                    'area': area,
                                    'price_per_m2': round(price / area, 2) if area else 0,
                                    'location': 'Wrocław',
                                    'url': url,
                                    'description': '',
                                    'image_url': ''
                                })
                    except Exception as e:
                        print(f"  ⚠️  Błąd parsowania oferty: {e}")
                        continue
                
                print(f"  ✓ Znaleziono {len(properties)} ofert z Gratka")
        
        except Exception as e:
            print(f"  ✗ Błąd Gratka: {e}")
        
        return properties
    
    def save_properties(self, properties: List[Dict]):
        """Zapisuje oferty do bazy danych bez błędów datetime"""
        if not properties:
            return

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_count = 0
        updated_count = 0

        for prop in properties:
            try:
                self.cursor.execute('SELECT id, price FROM properties WHERE url = ?', (prop['url'],))
                result = self.cursor.fetchone()

                if result:
                    prop_id, old_price = result
                    if float(prop['price']) != float(old_price):
                        # Zmiana ceny
                        self.cursor.execute('''
                            UPDATE properties 
                            SET price = ?, last_seen = ?, price_per_m2 = ?
                            WHERE id = ?
                        ''', (prop['price'], now_str, prop['price_per_m2'], prop_id))
                        updated_count += 1
                    else:
                        # Tylko aktualizacja czasu widoczności
                        self.cursor.execute('UPDATE properties SET last_seen = ? WHERE id = ?', (now_str, prop_id))
                else:
                    # Nowy wpis
                    self.cursor.execute('''
                        INSERT INTO properties (
                            portal, title, price, area, price_per_m2, 
                            location, url, first_seen, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        prop['portal'], prop['title'], prop['price'], prop['area'], 
                        prop['price_per_m2'], prop['location'], prop['url'], 
                        now_str, now_str
                    ))
                    new_count += 1
            except Exception as e:
                print(f"  ⚠️ Błąd zapisu SQL: {e}", flush=True)

        self.conn.commit()
        print(f"  💾 DB: +{new_count} nowych, ~{updated_count} zmian cen", flush=True) 
    
    def send_email_notification(self, properties: List[Dict]):
        """Wysyła powiadomienie email o nowych ofertach"""
        if not properties or not self.config['notifications']['email']['enabled']:
            return
        
        email_config = self.config['notifications']['email']
        
        # Tworzy HTML email
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .property {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }}
                .property h3 {{ margin: 0 0 10px 0; color: #2c3e50; }}
                .price {{ color: #27ae60; font-size: 20px; font-weight: bold; }}
                .details {{ color: #7f8c8d; }}
                a {{ color: #3498db; text-decoration: none; }}
            </style>
        </head>
        <body>
            <h2>🏠 Znaleziono {len(properties)} nowych ofert we Wrocławiu!</h2>
        """
        
        for prop in properties:
            html_content += f"""
            <div class="property">
                <h3>{prop['title']}</h3>
                <p class="price">{prop['price']:,.0f} zł</p>
                <p class="details">
                    📐 {prop['area']} m² • 
                    💰 {prop['price_per_m2']:,.0f} zł/m² • 
                    📍 {prop['location']} • 
                    🌐 {prop['portal'].upper()}
                </p>
                <p><a href="{prop['url']}" target="_blank">Zobacz ogłoszenie →</a></p>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🏠 {len(properties)} nowych mieszkań we Wrocławiu"
            msg['From'] = email_config['sender']
            msg['To'] = ', '.join(email_config['recipients'])
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['sender'], email_config['password'])
                server.send_message(msg)
            
            print(f"  ✓ Wysłano email do {len(email_config['recipients'])} odbiorców")
            
            # Zapisuje powiadomienie
            for prop in properties:
                prop_id = self.generate_property_id(prop['portal'], prop['url'])
                self.cursor.execute(
                    'INSERT INTO notifications (property_id, notification_type, sent_at) VALUES (?, ?, ?)',
                    (prop_id, 'email', datetime.now())
                )
            self.conn.commit()
            
        except Exception as e:
            print(f"  ✗ Błąd wysyłania email: {e}")
    
    def send_telegram_notification(self, properties: List[Dict]):
        """Wysyła powiadomienie przez Telegram"""
        if not properties or not self.config['notifications']['telegram']['enabled']:
            return
        
        telegram_config = self.config['notifications']['telegram']
        
        for prop in properties[:5]:  # Max 5 ofert na raz
            message = f"""
🏠 *Nowa oferta we Wrocławiu!*

{prop['title']}

💰 Cena: *{prop['price']:,.0f} zł*
📐 Metraż: {prop['area']} m²
💵 Za m²: {prop['price_per_m2']:,.0f} zł
📍 {prop['location']}
🌐 Portal: {prop['portal'].upper()}

[Zobacz ogłoszenie]({prop['url']})
            """
            
            try:
                url = f"https://api.telegram.org/bot{telegram_config['bot_token']}/sendMessage"
                data = {
                    'chat_id': telegram_config['chat_id'],
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                requests.post(url, data=data)
                time.sleep(1)  # Opóźnienie między wiadomościami
            except Exception as e:
                print(f"  ✗ Błąd wysyłania Telegram: {e}")
    
    def generate_dashboard_html(self, properties: List[Dict] = None):
        """Generuje plik HTML dashboardu na podstawie listy ofert"""
        # Jeśli nie przekazano listy, pobieramy ją z bazy jako fallback
        if properties is None:
            properties = self.get_recent_properties(limit=100)

        print(f"DEBUG: Generowanie HTML dla {len(properties)} ofert", flush=True)

        html_template = """
        <!DOCTYPE html>
        <html lang="pl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Monitor Nieruchomości Wrocław</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background-color: #f8f9fa; }
                .portal-olx { color: #002f34; font-weight: bold; }
                .portal-otodom { color: #00b54b; font-weight: bold; }
                .price-tag { font-size: 1.2rem; color: #d32f2f; font-weight: bold; }
                .table-container { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            </style>
        </head>
        <body>
            <div class="container mt-5">
                <h1 class="mb-4">Monitor Nieruchomości Wrocław</h1>
                <p class="text-muted">Ostatnia aktualizacja: {last_update}</p>
                
                <div class="table-container">
                    <table class="table table-hover">
                        <thead class="table-light">
                            <tr>
                                <th>Portal</th>
                                <th>Tytuł</th>
                                <th>Cena</th>
                                <th>Metraż</th>
                                <th>Cena/m²</th>
                                <th>Lokalizacja</th>
                                <th>Akcja</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

        rows = ""
        for p in properties:
            portal_class = f"portal-{p['portal'].lower()}"
            rows += f"""
            <tr>
                <td><span class="{portal_class}">{p['portal'].upper()}</span></td>
                <td>{p['title']}</td>
                <td><span class="price-tag">{p['price']:,} zł</span></td>
                <td>{p['area']} m²</td>
                <td>{p['price_per_m2']:,} zł</td>
                <td>{p['location']}</td>
                <td><a href="{p['url']}" target="_blank" class="btn btn-sm btn-primary">Zobacz</a></td>
            </tr>
            """

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_html = html_template.replace("{last_update}", now_str).replace("{table_rows}", rows)

        try:
            output_path = 'dashboard.html'
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_html)
            print(f"✅ Dashboard zapisany pomyślnie!", flush=True)
        except Exception as e:
            print(f"❌ Błąd zapisu pliku HTML: {e}", flush=True) 
    def check_properties(self):
        """Główny proces: pobierz, zapisz i odśwież dashboard"""
        print(f"\n{'='*60}", flush=True)
        print(f"🔄 Sprawdzam oferty - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print(f"{'='*60}\n", flush=True)

        # 1. Pobieranie danych z portali
        olx_data = self.scrape_olx()
        otodom_data = self.scrape_otodom()
        
        # Łączymy listy dla celów logowania
        all_found = olx_data + otodom_data
        print(f"\n📊 Łącznie znaleziono w sieci: {len(all_found)} ofert", flush=True)

        # 2. Zapis do bazy (aktualizuje ceny i daty)
        self.save_properties(all_found)

        # 3. Pobranie ŚWIEŻEJ listy z bazy (komplet danych z historią)
        # To gwarantuje, że dashboard pokaże to, co faktycznie jest w bazie
        properties_to_show = self.get_recent_properties(limit=100)
        
        # 4. Generowanie dashboardu
        if properties_to_show:
            self.generate_dashboard_html(properties_to_show)
            print(f"✅ Dashboard zaktualizowany o {len(properties_to_show)} ofert.", flush=True)
        else:
            print("⚠️ Brak ofert do wyświetlenia w dashboardzie.", flush=True)
    
    def get_recent_properties(self, limit: int = 100) -> List[Dict]:
        """Pobiera dane z bazy, mapując je na słowniki"""
        try:
            self.cursor.execute('PRAGMA table_info(properties)')
            columns = [col[1] for col in self.cursor.fetchall()]
            
            self.cursor.execute('SELECT * FROM properties ORDER BY first_seen DESC LIMIT ?', (limit,))
            rows = self.cursor.fetchall()
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"  ✗ Błąd odczytu bazy: {e}", flush=True)
            return []
    
    def run_once(self):
        """Jednorazowe sprawdzenie"""
        self.check_properties()
    
    def run_continuous(self):
        """Ciągłe monitorowanie"""
        interval = self.config['check_interval_minutes']
        print("DEBUG: RUN CONT 1", flush=True)
        # Uruchom HTTP serwer w osobnym wątku (dla dashboard)
        if os.getenv('PORT'):  # Tylko jeśli jest zmienna PORT (Render, Railway)
            http_thread = threading.Thread(target=start_http_server, daemon=True)
            http_thread.start()
        print("DEBUG: RUN CONT 2", flush=True)
        print(f"🚀 Uruchamiam monitor (sprawdzanie co {interval} minut)")
        print(f"📧 Powiadomienia email: {'✓' if self.config['notifications']['email']['enabled'] else '✗'}")
        print(f"📱 Powiadomienia Telegram: {'✓' if self.config['notifications']['telegram']['enabled'] else '✗'}")
        print(f"🌐 Portale: {', '.join(self.config['portals'])}\n")

        print("DEBUG: RUN CONT 3", flush=True)
        
        # Pierwsze sprawdzenie od razu
        self.check_properties()

        print("DEBUG: RUN CONT 4", flush=True)
        
        # Planuje kolejne
        schedule.every(interval).minutes.do(self.check_properties)
        
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == '__main__':
    import sys
    print("DEBUG: Skrypt wystartował", flush=True)
    monitor = RealEstateMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        print("DEBUG: Skrypt wystartował RUN ONCE", flush=True)
        monitor.run_once()
    else:      
        print("DEBUG: Skrypt wystartował RUN CONT", flush=True)
        monitor.run_continuous()
