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
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hashlib
import re
from typing import List, Dict, Optional
import schedule

class RealEstateMonitor:
    def __init__(self, config_file='config.json'):
        """Inicjalizacja monitora"""
        self.load_config(config_file)
        self.init_database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def load_config(self, config_file):
        """Ładuje konfigurację z pliku JSON lub zmiennych środowiskowych"""
        # Sprawdź czy są zmienne środowiskowe (Render.com)
        if os.getenv('EMAIL_SENDER'):
            print("📡 Używam konfiguracji ze zmiennych środowiskowych (Render)")
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
                        "recipients": [os.getenv('EMAIL_RECIPIENT', os.getenv('EMAIL_SENDER'))]
                    },
                    "telegram": {
                        "enabled": False,
                        "bot_token": "",
                        "chat_id": ""
                    }
                },
                "check_interval_minutes": int(os.getenv('CHECK_INTERVAL', '60')),
                "portals": ["otodom", "olx", "gratka"]
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
                "districts": []
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
        return hashlib.md5(f"{portal}:{url}".encode()).hexdigest()

    def extract_price(self, text: str) -> Optional[float]:
        if not text: return None
        price_str = re.sub(r'[^\d]', '', text)
        try:
            return float(price_str) if price_str else None
        except ValueError:
            return None

    def extract_area(self, text: str) -> Optional[float]:
        if not text: return None
        match = re.search(r'(\d+[.,]?\d*)\s*m', text.lower())
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                return None
        return None

    def scrape_otodom(self) -> List[Dict]:
        properties = []
        criteria = self.config['criteria']
        base_url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/dolnoslaskie/wroclaw"
        params = {
            'priceMin': criteria['min_price'],
            'priceMax': criteria['max_price'],
            'areaMin': criteria['min_area'],
            'areaMax': criteria['max_area']
        }
        print(f"🔍 Szukam na Otodom...")
        try:
            response = self.session.get(base_url, params=params, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = soup.find_all('article', {'data-cy': 'listing-item'})
                for listing in listings[:20]:
                    try:
                        title_elem = listing.find('h3')
                        price_elem = listing.find('span', string=re.compile(r'zł'))
                        area_elem = listing.find('span', string=re.compile(r'm²'))
                        link_elem = listing.find('a', href=True)
                        if not all([title_elem, price_elem, link_elem]): continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        area = self.extract_area(area_elem.get_text() if area_elem else '')
                        url = link_elem['href']
                        if not url.startswith('http'): url = 'https://www.otodom.pl' + url
                        
                        if price and area:
                            properties.append({
                                'portal': 'otodom', 'title': title, 'price': price,
                                'area': area, 'price_per_m2': round(price / area, 2),
                                'location': 'Wrocław', 'url': url, 'description': '', 'image_url': ''
                            })
                    except Exception as e:
                        continue
                print(f"  ✓ Znaleziono {len(properties)} ofert")
        except Exception as e:
            print(f"  ✗ Błąd Otodom: {e}")
        return properties

    def scrape_olx(self) -> List[Dict]:
        properties = []
        criteria = self.config['criteria']
        print(f"🔍 Szukam na OLX...")
        try:
            base_url = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/wroclaw/"
            response = self.session.get(base_url, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = soup.find_all('div', {'data-cy': 'l-card'})
                for listing in listings[:20]:
                    try:
                        title_elem = listing.find('h6')
                        price_elem = listing.find('p', {'data-testid': 'ad-price'})
                        link_elem = listing.find('a', href=True)
                        if not all([title_elem, price_elem, link_elem]): continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        url = link_elem['href']
                        area = self.extract_area(title)
                        if not url.startswith('http'): url = 'https://www.olx.pl' + url
                        
                        if price and criteria['min_price'] <= price <= criteria['max_price']:
                            properties.append({
                                'portal': 'olx', 'title': title, 'price': price,
                                'area': area or 0, 'price_per_m2': round(price / area, 2) if area else 0,
                                'location': 'Wrocław', 'url': url, 'description': '', 'image_url': ''
                            })
                    except Exception: continue
                print(f"  ✓ Znaleziono {len(properties)} ofert")
        except Exception as e:
            print(f"  ✗ Błąd OLX: {e}")
        return properties

    def scrape_gratka(self) -> List[Dict]:
        properties = []
        criteria = self.config['criteria']
        print(f"🔍 Szukam na Gratka...")
        try:
            base_url = "https://gratka.pl/nieruchomosci/mieszkania/dolnoslaskie/wroclaw/sprzedaz"
            response = self.session.get(base_url, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = soup.find_all('article', class_='teaserUnified')
                for listing in listings[:20]:
                    try:
                        title_elem = listing.find('h2')
                        price_elem = listing.find('span', class_='teaserUnified__price')
                        link_elem = listing.find('a', href=True)
                        if not all([title_elem, price_elem, link_elem]): continue
                        
                        title = title_elem.get_text(strip=True)
                        price = self.extract_price(price_elem.get_text())
                        url = link_elem['href']
                        area = self.extract_area(listing.get_text())
                        
                        if price and criteria['min_price'] <= price <= criteria['max_price']:
                            properties.append({
                                'portal': 'gratka', 'title': title, 'price': price,
                                'area': area or 0, 'price_per_m2': round(price / area, 2) if area else 0,
                                'location': 'Wrocław', 'url': url, 'description': '', 'image_url': ''
                            })
                    except Exception: continue
                print(f"  ✓ Znaleziono {len(properties)} ofert")
        except Exception as e:
            print(f"  ✗ Błąd Gratka: {e}")
        return properties

    def save_properties(self, properties: List[Dict]) -> List[Dict]:
        new_properties = []
        now = datetime.now()
        for prop in properties:
            prop_id = self.generate_property_id(prop['portal'], prop['url'])
            self.cursor.execute('SELECT id, price FROM properties WHERE id = ?', (prop_id,))
            existing = self.cursor.fetchone()
            if existing:
                if existing[1] != prop['price']:
                    self.cursor.execute('UPDATE properties SET price=?, last_seen=? WHERE id=?', (prop['price'], now, prop_id))
                else:
                    self.cursor.execute('UPDATE properties SET last_seen=? WHERE id=?', (now, prop_id))
            else:
                self.cursor.execute('''INSERT INTO properties (id, portal, title, price, area, price_per_m2, location, url, first_seen, last_seen, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''', 
                    (prop_id, prop['portal'], prop['title'], prop['price'], prop['area'], prop['price_per_m2'], prop['location'], prop['url'], now, now))
                new_properties.append(prop)
        self.conn.commit()
        return new_properties

    def send_email_notification(self, properties: List[Dict]):
        if not properties or not self.config['notifications']['email']['enabled']: return
        email_config = self.config['notifications']['email']
        if not email_config['password']: return

        html_content = "<html><body><h2>Nowe oferty Wrocław</h2>"
        for prop in properties:
            html_content += f"<p><b>{prop['title']}</b><br>Cena: {prop['price']} zł<br><a href='{prop['url']}'>Link</a></p><hr>"
        html_content += "</body></html>"

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🏠 {len(properties)} nowych ofert"
            msg['From'] = email_config['sender']
            msg['To'] = ', '.join(email_config['recipients'])
            msg.attach(MIMEText(html_content, 'html'))
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['sender'], email_config['password'])
                server.send_message(msg)
            print("  ✓ E-mail wysłany")
        except Exception as e:
            print(f"  ✗ Błąd e-mail: {e}")

    def check_properties(self):
        print(f"\n🔄 Skanowanie: {datetime.now().strftime('%H:%M:%S')}")
        all_props = []
        if 'otodom' in self.config['portals']: all_props.extend(self.scrape_otodom())
        if 'olx' in self.config['portals']: all_props.extend(self.scrape_olx())
        if 'gratka' in self.config['portals']: all_props.extend(self.scrape_gratka())
        
        new_props = self.save_properties(all_props)
        if new_props:
            print(f"  ✨ Nowe oferty: {len(new_props)}")
            self.send_email_notification(new_props)
        else:
            print("  ℹ Brak nowych ofert")

    def run_continuous(self):
        interval = self.config['check_interval_minutes']
        print(f"🚀 Monitor startuje (co {interval} min)")
        self.check_properties()
        schedule.every(interval).minutes.do(self.check_properties)
        while True:
            schedule.run_pending()
            time.sleep(1)

if __name__ == '__main__':
    # --- DODAJ TO, ABY OSZUKAĆ RENDERA ---
    import http.server
    import socketserver
    import threading

    def run_dummy_server():
        port = int(os.environ.get("PORT", 10000))
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"✅ Dummy server running on port {port}")
            httpd.serve_forever()

    # Uruchom serwer w osobnym wątku
    threading.Thread(target=run_dummy_server, daemon=True).start()
    # -------------------------------------

    monitor = RealEstateMonitor()
    monitor.run_continuous()
