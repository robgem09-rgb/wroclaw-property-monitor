#!/usr/bin/env python3
"""
Skrypt testowy dla monitora nieruchomości
Sprawdza czy wszystko działa prawidłowo
"""

import json
import requests
import smtplib
from email.mime.text import MIMEText
import sqlite3
from datetime import datetime

def test_config():
    """Test pliku konfiguracyjnego"""
    print("\n" + "="*60)
    print("🔧 TEST KONFIGURACJI")
    print("="*60)
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("✓ Plik config.json został wczytany")
        
        # Sprawdź wymagane pola
        required = ['criteria', 'notifications', 'check_interval_minutes', 'portals']
        for field in required:
            if field in config:
                print(f"  ✓ {field}: OK")
            else:
                print(f"  ✗ {field}: BRAK")
                return False
        
        # Sprawdź kryteria
        criteria = config['criteria']
        print(f"\n📊 Kryteria:")
        print(f"  • Cena: {criteria['min_price']:,} - {criteria['max_price']:,} PLN")
        print(f"  • Metraż: {criteria['min_area']} - {criteria['max_area']} m²")
        print(f"  • Miasto: {criteria['city']}")
        
        return True
        
    except FileNotFoundError:
        print("✗ Brak pliku config.json!")
        print("  Uruchom: python setup.py")
        return False
    except json.JSONDecodeError:
        print("✗ Błąd w pliku config.json - nieprawidłowy format JSON")
        return False

def test_database():
    """Test bazy danych"""
    print("\n" + "="*60)
    print("💾 TEST BAZY DANYCH")
    print("="*60)
    
    try:
        conn = sqlite3.connect('properties.db')
        cursor = conn.cursor()
        
        # Sprawdź tabele
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if tables:
            print(f"✓ Baza danych istnieje")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                count = cursor.fetchone()[0]
                print(f"  • Tabela {table[0]}: {count} rekordów")
        else:
            print("ℹ️  Baza jest pusta (to normalne przy pierwszym uruchomieniu)")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Błąd bazy danych: {e}")
        return False

def test_internet():
    """Test połączenia z internetem"""
    print("\n" + "="*60)
    print("🌐 TEST POŁĄCZENIA Z INTERNETEM")
    print("="*60)
    
    sites = [
        ('Otodom', 'https://www.otodom.pl'),
        ('OLX', 'https://www.olx.pl'),
        ('Gratka', 'https://gratka.pl'),
        ('Google', 'https://www.google.com')
    ]
    
    all_ok = True
    for name, url in sites:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {name}: OK ({response.status_code})")
            else:
                print(f"  ⚠️  {name}: {response.status_code}")
                all_ok = False
        except requests.exceptions.Timeout:
            print(f"  ✗ {name}: TIMEOUT")
            all_ok = False
        except Exception as e:
            print(f"  ✗ {name}: {str(e)[:50]}")
            all_ok = False
    
    return all_ok

def test_email():
    """Test połączenia email"""
    print("\n" + "="*60)
    print("📧 TEST POWIADOMIEŃ EMAIL")
    print("="*60)
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        email_config = config['notifications']['email']
        
        if not email_config['enabled']:
            print("⊘ Email wyłączony w konfiguracji")
            return True
        
        print(f"  Serwer: {email_config['smtp_server']}:{email_config['smtp_port']}")
        print(f"  Nadawca: {email_config['sender']}")
        print(f"  Odbiorcy: {', '.join(email_config['recipients'])}")
        
        # Test połączenia SMTP
        try:
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'], timeout=10)
            server.starttls()
            server.login(email_config['sender'], email_config['password'])
            print("  ✓ Połączenie SMTP: OK")
            
            # Wysłanie testowego emaila
            send_test = input("\nCzy wysłać testowy email? (t/n): ").lower() == 't'
            
            if send_test:
                msg = MIMEText("To jest testowa wiadomość z monitora nieruchomości. Jeśli to czytasz, wszystko działa! 🎉")
                msg['Subject'] = "🏠 Test - Monitor Nieruchomości"
                msg['From'] = email_config['sender']
                msg['To'] = ', '.join(email_config['recipients'])
                
                server.send_message(msg)
                print("  ✓ Email testowy wysłany!")
            
            server.quit()
            return True
            
        except smtplib.SMTPAuthenticationError:
            print("  ✗ Błąd autoryzacji - sprawdź login i hasło")
            print("  ℹ️  Dla Gmail użyj hasła aplikacji, nie zwykłego hasła!")
            return False
        except Exception as e:
            print(f"  ✗ Błąd SMTP: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Błąd: {e}")
        return False

def test_telegram():
    """Test połączenia Telegram"""
    print("\n" + "="*60)
    print("📱 TEST POWIADOMIEŃ TELEGRAM")
    print("="*60)
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        telegram_config = config['notifications']['telegram']
        
        if not telegram_config['enabled']:
            print("⊘ Telegram wyłączony w konfiguracji")
            return True
        
        # Test API Telegram
        url = f"https://api.telegram.org/bot{telegram_config['bot_token']}/getMe"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data['ok']:
                print(f"  ✓ Bot: @{data['result']['username']}")
                
                # Wysłanie testowej wiadomości
                send_test = input("\nCzy wysłać testową wiadomość? (t/n): ").lower() == 't'
                
                if send_test:
                    send_url = f"https://api.telegram.org/bot{telegram_config['bot_token']}/sendMessage"
                    message_data = {
                        'chat_id': telegram_config['chat_id'],
                        'text': '🏠 Test - Monitor Nieruchomości\n\nJeśli to czytasz, wszystko działa! 🎉'
                    }
                    resp = requests.post(send_url, data=message_data)
                    if resp.status_code == 200:
                        print("  ✓ Wiadomość testowa wysłana!")
                    else:
                        print(f"  ✗ Błąd wysyłania: {resp.status_code}")
                        return False
                
                return True
            else:
                print("  ✗ Nieprawidłowa odpowiedź API")
                return False
        else:
            print(f"  ✗ Błąd połączenia: {response.status_code}")
            print("  ℹ️  Sprawdź token bota")
            return False
            
    except Exception as e:
        print(f"✗ Błąd: {e}")
        return False

def run_all_tests():
    """Uruchamia wszystkie testy"""
    print("\n" + "="*60)
    print("🧪 TESTY MONITORA NIERUCHOMOŚCI")
    print("="*60)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Konfiguracja", test_config),
        ("Baza danych", test_database),
        ("Internet", test_internet),
        ("Email", test_email),
        ("Telegram", test_telegram)
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Niespodziewany błąd w teście {name}: {e}")
            results.append((name, False))
    
    # Podsumowanie
    print("\n" + "="*60)
    print("📊 PODSUMOWANIE")
    print("="*60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status} - {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\nWynik: {passed}/{total} testów zaliczonych")
    
    if passed == total:
        print("\n🎉 Wszystko działa! Możesz uruchomić monitor:")
        print("   python real_estate_monitor.py")
    else:
        print("\n⚠️  Niektóre testy nie przeszły. Sprawdź błędy powyżej.")
    
    print("="*60 + "\n")

if __name__ == '__main__':
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⊘ Przerwano testy")
