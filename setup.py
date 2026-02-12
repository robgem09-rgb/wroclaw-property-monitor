#!/usr/bin/env python3
"""
Prosty kreator konfiguracji dla monitora nieruchomości
"""

import json

def setup_wizard():
    print("="*60)
    print("🏠 KREATOR KONFIGURACJI - Monitor Nieruchomości")
    print("="*60)
    print()
    
    config = {}
    
    # Kryteria wyszukiwania
    print("📊 KRYTERIA WYSZUKIWANIA\n")
    
    config['criteria'] = {
        'min_price': int(input("Minimalna cena (PLN): ") or "200000"),
        'max_price': int(input("Maksymalna cena (PLN): ") or "500000"),
        'min_area': float(input("Minimalny metraż (m²): ") or "35"),
        'max_area': float(input("Maksymalny metraż (m²): ") or "70"),
        'city': 'Wrocław',
        'districts': []
    }
    
    print("\n✓ Kryteria zapisane!")
    print(f"  Szukam mieszkań {config['criteria']['min_area']}-{config['criteria']['max_area']}m²")
    print(f"  W cenie {config['criteria']['min_price']:,}-{config['criteria']['max_price']:,} PLN")
    
    # Powiadomienia email
    print("\n" + "="*60)
    print("📧 POWIADOMIENIA EMAIL\n")
    
    email_enabled = input("Czy włączyć powiadomienia email? (t/n): ").lower() == 't'
    
    if email_enabled:
        email_sender = input("Twój adres email: ")
        
        print("\nℹ️  Dla Gmail:")
        print("   1. Włącz weryfikację 2-etapową")
        print("   2. Wygeneruj hasło aplikacji: https://myaccount.google.com/apppasswords")
        print("   3. Użyj wygenerowanego hasła (nie swojego hasła do Gmail)")
        
        email_password = input("\nHasło aplikacji email: ")
        email_recipients = input("Email(e) odbiorcy (oddziel przecinkami): ")
        
        config['notifications'] = {
            'email': {
                'enabled': True,
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender': email_sender,
                'password': email_password,
                'recipients': [e.strip() for e in email_recipients.split(',')]
            },
            'telegram': {
                'enabled': False,
                'bot_token': '',
                'chat_id': ''
            }
        }
        print("\n✓ Email skonfigurowany!")
    else:
        config['notifications'] = {
            'email': {
                'enabled': False,
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender': '',
                'password': '',
                'recipients': []
            },
            'telegram': {
                'enabled': False,
                'bot_token': '',
                'chat_id': ''
            }
        }
        print("\n⊘ Email wyłączony")
    
    # Telegram (opcjonalnie)
    print("\n" + "="*60)
    print("📱 POWIADOMIENIA TELEGRAM (opcjonalne)\n")
    
    telegram_enabled = input("Czy włączyć powiadomienia Telegram? (t/n): ").lower() == 't'
    
    if telegram_enabled:
        print("\nℹ️  Instrukcja:")
        print("   1. Znajdź @BotFather na Telegramie")
        print("   2. Wyślij /newbot i postępuj zgodnie z instrukcjami")
        print("   3. Otrzymasz token bota")
        print("   4. Wyślij wiadomość do swojego bota")
        print("   5. Odwiedź: https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("   6. Znajdź swoje chat_id w odpowiedzi")
        
        bot_token = input("\nToken bota: ")
        chat_id = input("Chat ID: ")
        
        config['notifications']['telegram'] = {
            'enabled': True,
            'bot_token': bot_token,
            'chat_id': chat_id
        }
        print("\n✓ Telegram skonfigurowany!")
    
    # Ustawienia monitorowania
    print("\n" + "="*60)
    print("⚙️  USTAWIENIA MONITOROWANIA\n")
    
    interval = int(input("Co ile minut sprawdzać oferty? (30-360): ") or "30")
    
    config['check_interval_minutes'] = max(30, min(360, interval))
    config['portals'] = ['otodom', 'olx', 'gratka']
    
    print(f"\n✓ Sprawdzanie co {config['check_interval_minutes']} minut")
    print(f"✓ Portale: {', '.join(config['portals'])}")
    
    # Zapisz konfigurację
    print("\n" + "="*60)
    print("💾 ZAPISYWANIE KONFIGURACJI\n")
    
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print("✓ Konfiguracja zapisana w pliku: config.json")
    
    # Podsumowanie
    print("\n" + "="*60)
    print("🎉 GOTOWE!\n")
    print("Możesz teraz uruchomić monitor:")
    print("  python real_estate_monitor.py --once    (test)")
    print("  python real_estate_monitor.py           (ciągłe działanie)")
    print("\nDashboard będzie dostępny w pliku: dashboard.html")
    print("="*60)

if __name__ == '__main__':
    try:
        setup_wizard()
    except KeyboardInterrupt:
        print("\n\n⊘ Anulowano")
    except Exception as e:
        print(f"\n✗ Błąd: {e}")
