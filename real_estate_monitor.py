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
        print(f"🌐 Dashboard HTTP serwer uruchomiony na porcie {port}")
        print(f"   Dostęp: http://localhost:{port}/dashboard.html")
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
            print("📡 Używam konfiguracji ze zmiennych środowiskowych (Cloud)")
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
                print(f"Brak pliku {config_file}. Tworzę domyślną konfigurację...")
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
        criteria = self.config['criteria']
        
        # Buduje URL z filtrami
        base_url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/dolnoslaskie/wroclaw"
        params = {
            'priceMin': criteria['min_price'],
            'priceMax': criteria['max_price'],
            'areaMin': criteria['min_area'],
            'areaMax': criteria['max_area']
        }
        
        print(f"🔍 Szukam na Otodom...")
        
        try:
            # Otodom używa API - to przykładowy endpoint
            # W praktyce może wymagać dodatkowej analizy
            response = self.session.get(base_url, params=params, timeout=10)
            print(f"DEBUG: Status odpowiedzi z {url}: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Znajduje listingi (struktura HTML może się zmienić)
                listings = soup.find_all('article', {'data-cy': 'listing-item'})
                
                for listing in listings[:20]:  # Limit 20 ofert na skan
                    try:
                        title_elem = listing.find('h3')
                        price_elem = listing.find('span', text=re.compile(r'zł'))
                        area_elem = listing.find('span', text=re.compile(r'm²'))
                        link_elem = listing.find('a', href=True)
                        location_elem = listing.find('p', {'data-cy': 'listing-item-location'})
                        
                        if not all([title_elem, price_elem, link_elem]):
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        area = self.extract_area(area_elem.get_text() if area_elem else '')
                        url = link_elem['href']
                        location = location_elem.get_text(strip=True) if location_elem else ''
                        
                        if not url.startswith('http'):
                            url = 'https://www.otodom.pl' + url
                        
                        if price and area:
                            properties.append({
                                'portal': 'otodom',
                                'title': title,
                                'price': price,
                                'area': area,
                                'price_per_m2': round(price / area, 2),
                                'location': location,
                                'url': url,
                                'description': '',
                                'image_url': ''
                            })
                    except Exception as e:
                        print(f"  ⚠️  Błąd parsowania oferty: {e}")
                        continue
                
                print(f"  ✓ Znaleziono {len(properties)} ofert z Otodom")
        
        except Exception as e:
            print(f"  ✗ Błąd Otodom: {e}")
        
        return properties
    
    def scrape_olx(self) -> List[Dict]:
        """Zbiera oferty z OLX"""
        properties = []
        criteria = self.config['criteria']
        
        print(f"🔍 Szukam na OLX...")
        
        try:
            # URL OLX dla Wrocławia
            base_url = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/wroclaw/"
            
            # OLX ma bardziej dynamiczną strukturę
            # W praktyce może wymagać selenium lub API
            response = self.session.get(base_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Znajduje ogłoszenia
                listings = soup.find_all('div', {'data-cy': 'l-card'})
                
                for listing in listings[:20]:
                    try:
                        title_elem = listing.find('h6')
                        price_elem = listing.find('p', {'data-testid': 'ad-price'})
                        link_elem = listing.find('a', href=True)
                        
                        if not all([title_elem, price_elem, link_elem]):
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        url = link_elem['href']
                        
                        # OLX często ma metraż w tytule
                        area = self.extract_area(title)
                        
                        if not url.startswith('http'):
                            url = 'https://www.olx.pl' + url
                        
                        # Filtruje według kryteriów
                        if price and price >= criteria['min_price'] and price <= criteria['max_price']:
                            if area and area >= criteria['min_area'] and area <= criteria['max_area']:
                                properties.append({
                                    'portal': 'olx',
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
                
                print(f"  ✓ Znaleziono {len(properties)} ofert z OLX")
        
        except Exception as e:
            print(f"  ✗ Błąd OLX: {e}")
        
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
    
    def save_properties(self, properties: List[Dict]) -> List[Dict]:
        """Zapisuje nieruchomości do bazy, zwraca nowe oferty"""
        new_properties = []
        now = datetime.now()
        
        for prop in properties:
            prop_id = self.generate_property_id(prop['portal'], prop['url'])
            
            # Sprawdza czy oferta już istnieje
            self.cursor.execute('SELECT id, price FROM properties WHERE id = ?', (prop_id,))
            existing = self.cursor.fetchone()
            
            if existing:
                # Aktualizuje last_seen i sprawdza zmianę ceny
                old_price = existing[1]
                if old_price != prop['price']:
                    # Zmiana ceny!
                    self.cursor.execute('''
                        UPDATE properties 
                        SET price = ?, price_per_m2 = ?, last_seen = ?
                        WHERE id = ?
                    ''', (prop['price'], prop['price_per_m2'], now, prop_id))
                    print(f"  💰 Zmiana ceny: {prop['title'][:50]}... ({old_price} → {prop['price']})")
                else:
                    self.cursor.execute('UPDATE properties SET last_seen = ? WHERE id = ?', (now, prop_id))
            else:
                # Nowa oferta!
                self.cursor.execute('''
                    INSERT INTO properties 
                    (id, portal, title, price, area, price_per_m2, location, url, 
                     description, first_seen, last_seen, image_url, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''', (
                    prop_id, prop['portal'], prop['title'], prop['price'], 
                    prop['area'], prop['price_per_m2'], prop['location'], 
                    prop['url'], prop['description'], now, now, prop['image_url']
                ))
                new_properties.append(prop)
                print(f"  ✨ Nowa oferta: {prop['title'][:60]}...")
        
        self.conn.commit()
        return new_properties
    
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
    
    def generate_dashboard_html(self):
        """Generuje dashboard HTML z ofertami"""
        self.cursor.execute('''
            SELECT portal, title, price, area, price_per_m2, location, url, first_seen
            FROM properties 
            WHERE is_active = 1 
            ORDER BY first_seen DESC 
            LIMIT 100
        ''')
        
        properties = self.cursor.fetchall()
        
        html = f"""
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitor Nieruchomości - Wrocław</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f5f7fa;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{ font-size: 32px; margin-bottom: 10px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #667eea; }}
        .stat-label {{ color: #718096; margin-top: 5px; }}
        .filters {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .property-grid {{
            display: grid;
            gap: 20px;
        }}
        .property-card {{
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .property-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.15);
        }}
        .property-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 15px;
        }}
        .property-title {{
            font-size: 18px;
            font-weight: 600;
            color: #2d3748;
            flex: 1;
        }}
        .portal-badge {{
            background: #edf2f7;
            color: #4a5568;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .portal-badge.otodom {{ background: #fef5e7; color: #d68910; }}
        .portal-badge.olx {{ background: #e8f8f5; color: #16a085; }}
        .portal-badge.gratka {{ background: #fdecea; color: #e74c3c; }}
        .property-price {{
            font-size: 28px;
            font-weight: bold;
            color: #27ae60;
            margin: 15px 0;
        }}
        .property-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin: 15px 0;
        }}
        .detail-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            color: #4a5568;
        }}
        .detail-icon {{ font-size: 18px; }}
        .property-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e2e8f0;
        }}
        .property-date {{
            color: #a0aec0;
            font-size: 14px;
        }}
        .property-link {{
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: background 0.2s;
        }}
        .property-link:hover {{
            background: #5568d3;
        }}
        .updated {{ 
            text-align: center; 
            color: #a0aec0; 
            margin-top: 30px;
            font-size: 14px;
        }}
        input, select {{
            padding: 10px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            margin-right: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏠 Monitor Nieruchomości</h1>
            <p>Mieszkania na sprzedaż we Wrocławiu</p>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{len(properties)}</div>
                <div class="stat-label">Aktywnych ofert</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len([p for p in properties if p[0] == 'otodom'])}</div>
                <div class="stat-label">Otodom</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len([p for p in properties if p[0] == 'olx'])}</div>
                <div class="stat-label">OLX</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len([p for p in properties if p[0] == 'gratka'])}</div>
                <div class="stat-label">Gratka</div>
            </div>
        </div>
        
        <div class="property-grid">
"""
        
        for prop in properties:
            portal, title, price, area, price_per_m2, location, url, first_seen = prop
            date_str = datetime.fromisoformat(str(first_seen)).strftime('%d.%m.%Y %H:%M')
            
            html += f"""
            <div class="property-card">
                <div class="property-header">
                    <div class="property-title">{title}</div>
                    <span class="portal-badge {portal}">{portal}</span>
                </div>
                <div class="property-price">{price:,.0f} zł</div>
                <div class="property-details">
                    <div class="detail-item">
                        <span class="detail-icon">📐</span>
                        <span>{area} m²</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">💰</span>
                        <span>{price_per_m2:,.0f} zł/m²</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-icon">📍</span>
                        <span>{location}</span>
                    </div>
                </div>
                <div class="property-footer">
                    <span class="property-date">Dodano: {date_str}</span>
                    <a href="{url}" target="_blank" class="property-link">Zobacz →</a>
                </div>
            </div>
"""
        
        html += f"""
        </div>
        <p class="updated">Ostatnia aktualizacja: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
    </div>
</body>
</html>
"""
        
        with open('dashboard.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        print("  ✓ Dashboard zaktualizowany: dashboard.html")
    
    def check_properties(self):
        """Główna funkcja sprawdzająca oferty"""
        print(f"\n{'='*60}")
        print(f"🔄 Sprawdzam oferty - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        all_properties = []
        
        # Zbiera z wszystkich portali
        if 'otodom' in self.config['portals']:
            all_properties.extend(self.scrape_otodom())
        
        if 'olx' in self.config['portals']:
            all_properties.extend(self.scrape_olx())
        
        if 'gratka' in self.config['portals']:
            all_properties.extend(self.scrape_gratka())
        
        print(f"\n📊 Łącznie znaleziono: {len(all_properties)} ofert")
        
        # Zapisuje do bazy
        new_properties = self.save_properties(all_properties)
        
        if new_properties:
            print(f"✨ Nowych ofert: {len(new_properties)}")
            # Wysyła powiadomienia
            self.send_email_notification(new_properties)
            self.send_telegram_notification(new_properties)
        else:
            print("ℹ️  Brak nowych ofert")
        
        # Generuje dashboard
        self.generate_dashboard_html()
        
        print(f"\n{'='*60}\n")
    
    def run_once(self):
        """Jednorazowe sprawdzenie"""
        self.check_properties()
    
    def run_continuous(self):
        """Ciągłe monitorowanie"""
        interval = self.config['check_interval_minutes']
        
        # Uruchom HTTP serwer w osobnym wątku (dla dashboard)
        if os.getenv('PORT'):  # Tylko jeśli jest zmienna PORT (Render, Railway)
            http_thread = threading.Thread(target=start_http_server, daemon=True)
            http_thread.start()
        
        print(f"🚀 Uruchamiam monitor (sprawdzanie co {interval} minut)")
        print(f"📧 Powiadomienia email: {'✓' if self.config['notifications']['email']['enabled'] else '✗'}")
        print(f"📱 Powiadomienia Telegram: {'✓' if self.config['notifications']['telegram']['enabled'] else '✗'}")
        print(f"🌐 Portale: {', '.join(self.config['portals'])}\n")
        
        # Pierwsze sprawdzenie od razu
        self.check_properties()
        
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
