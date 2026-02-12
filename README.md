# 🏠 Monitor Rynku Nieruchomości - Wrocław

System automatycznego monitorowania ofert mieszkań z Otodom, OLX i Gratka.

## 🚀 Szybki start

### 1. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 2. Konfiguracja

Edytuj plik `config.json`:

```json
{
  "criteria": {
    "min_price": 250000,      // Minimalna cena
    "max_price": 450000,      // Maksymalna cena
    "min_area": 40,           // Minimalny metraż (m²)
    "max_area": 65,           // Maksymalny metraż (m²)
    "city": "Wrocław",
    "districts": []           // [] = wszystkie dzielnice
  }
}
```

### 3. Konfiguracja powiadomień EMAIL

#### Dla Gmail:
1. Włącz weryfikację dwuetapową w swoim koncie Google
2. Wygeneruj hasło aplikacji:
   - Idź do: https://myaccount.google.com/apppasswords
   - Wybierz "Poczta" i "Inne urządzenie"
   - Skopiuj wygenerowane hasło
3. W pliku `config.json`:
```json
"email": {
  "enabled": true,
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "sender": "twoj_email@gmail.com",
  "password": "wygenerowane_haslo_aplikacji",
  "recipients": ["twoj_email@gmail.com"]
}
```

#### Dla innych dostawców:
- **Outlook/Hotmail**: smtp-mail.outlook.com:587
- **Yahoo**: smtp.mail.yahoo.com:587
- **O2**: poczta.o2.pl:587

### 4. Konfiguracja powiadomień TELEGRAM (opcjonalne)

1. Stwórz bota przez @BotFather na Telegramie
2. Otrzymasz token bota (np. `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
3. Rozpocznij rozmowę ze swoim botem
4. Pobierz swoje chat_id:
   - Wyślij wiadomość do bota
   - Odwiedź: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Znajdź swoje `chat_id` w odpowiedzi
5. W pliku `config.json`:
```json
"telegram": {
  "enabled": true,
  "bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
  "chat_id": "your_chat_id"
}
```

## 📱 Uruchamianie

### Jednorazowe sprawdzenie:
```bash
python real_estate_monitor.py --once
```

### Ciągłe monitorowanie:
```bash
python real_estate_monitor.py
```

System będzie sprawdzał oferty co 30 minut (można zmienić w config.json).

## 📊 Dashboard

Po uruchomieniu, otwórz plik `dashboard.html` w przeglądarce.
Dashboard pokazuje wszystkie znalezione oferty z możliwością sortowania.

## 🔧 Uruchomienie w chmurze (24/7)

### Opcja 1: PythonAnywhere (DARMOWE)

1. Zarejestruj się na https://www.pythonanywhere.com (darmowe konto)
2. Upload plików przez Files → Upload
3. Otwórz Bash console
4. Zainstaluj zależności:
   ```bash
   pip3 install --user -r requirements.txt
   ```
5. Uruchom:
   ```bash
   python3 real_estate_monitor.py
   ```
6. Aby działało non-stop, dodaj w Tasks:
   - Schedule: `0 */1 * * *` (co godzinę)
   - Command: `python3 /home/username/real_estate_monitor.py --once`

### Opcja 2: Render (DARMOWE)

1. Stwórz konto na https://render.com
2. Stwórz nowe Web Service z repozytorium GitHub
3. Dodaj środowiskowe zmienne dla wrażliwych danych
4. Deploy!

### Opcja 3: Własny komputer (cron/Task Scheduler)

#### Linux/Mac (cron):
```bash
crontab -e
# Dodaj linię (sprawdzanie co godzinę):
0 * * * * cd /ścieżka/do/projektu && python3 real_estate_monitor.py --once
```

#### Windows (Task Scheduler):
1. Otwórz Task Scheduler
2. Create Basic Task
3. Trigger: Daily, repeat every 1 hour
4. Action: Start program
   - Program: `python`
   - Arguments: `C:\ścieżka\real_estate_monitor.py --once`

## 📁 Struktura plików

```
.
├── real_estate_monitor.py  # Główny skrypt
├── config.json            # Konfiguracja
├── requirements.txt       # Zależności Python
├── properties.db          # Baza danych SQLite (auto-generowana)
├── dashboard.html         # Dashboard HTML (auto-generowany)
└── README.md             # Ta instrukcja
```

## 💡 Wskazówki

1. **Pierwsze uruchomienie**: Użyj `--once` aby sprawdzić czy wszystko działa
2. **Metraż w tytule**: Skrypt wyciąga metraż z tytułów OLX (np. "Mieszkanie 45m2")
3. **Zmiana ceny**: System wykrywa gdy cena oferty się zmienia
4. **Dashboard**: Odświeża się automatycznie po każdym skanie
5. **Baza danych**: Wszystkie oferty zapisywane są w SQLite

## 🐛 Rozwiązywanie problemów

### "Import error" / Brak bibliotek:
```bash
pip install -r requirements.txt --upgrade
```

### Nie wysyła emaili (Gmail):
- Sprawdź czy masz włączoną weryfikację 2-etapową
- Użyj hasła aplikacji, nie swojego hasła do Gmail
- Sprawdź czy Gmail nie blokuje "mniej bezpiecznych aplikacji"

### Nie znajduje ofert:
- Portale często zmieniają strukturę HTML
- Może być potrzebna aktualizacja selektorów CSS
- Sprawdź czy nie używasz VPN (niektóre portale blokują)

### Dashboard nie odświeża się:
- Otwórz `dashboard.html` ponownie w przeglądarce
- Może być potrzebne wyczyszczenie cache (Ctrl+F5)

## 🔐 Bezpieczeństwo

- **NIE** commituj `config.json` z hasłami do repo
- Użyj zmiennych środowiskowych dla wrażliwych danych
- Regularnie zmieniaj hasła aplikacji

## 📈 Przyszłe ulepszenia

- [ ] Wsparcie dla większej liczby portali
- [ ] Zaawansowane filtry (piętro, rok budowy)
- [ ] Integracja z Google Maps
- [ ] Wykresy zmian cen
- [ ] Porównywanie z cenami rynkowymi
- [ ] Push notifications na telefon
- [ ] API do integracji z innymi narzędziami

## 📝 Licencja

MIT License - użyj dowolnie!

## 🤝 Wsparcie

Pytania? Problemy? Stwórz issue lub wyślij pull request!
