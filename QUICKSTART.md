# 🚀 SZYBKI START - Monitor Nieruchomości

## ⚡ 5-minutowa instalacja

### Windows

1. **Pobierz i rozpakuj** wszystkie pliki do folderu (np. `C:\PropertyMonitor\`)

2. **Kliknij dwukrotnie**: `start.bat`

3. **Wybierz opcję 6** - "Edytuj konfigurację"

4. **Wprowadź swoje dane**:
   - Cena: np. 250000 - 450000
   - Metraż: np. 40 - 65
   - Email: twoj@email.com
   - Hasło aplikacji Gmail (instrukcja poniżej)

5. **Wybierz opcję 1** - "Uruchom test"

6. **Gotowe!** Sprawdź email i otwórz `dashboard.html`

### Linux / Mac

```bash
# 1. Przejdź do katalogu
cd /ścieżka/do/folderu

# 2. Uruchom kreator
./start.sh

# 3. Wybierz opcję 6 i skonfiguruj
# 4. Wybierz opcję 1 aby przetestować
```

### Docker (zaawansowane)

```bash
# 1. Stwórz config.json
python3 setup.py

# 2. Uruchom
docker-compose up -d

# 3. Sprawdź logi
docker-compose logs -f
```

---

## 📧 Jak zdobyć hasło aplikacji Gmail?

1. Otwórz: https://myaccount.google.com/security

2. Włącz **"Weryfikacja dwuetapowa"** (jeśli nie masz)

3. Wróć do bezpieczeństwa i znajdź **"Hasła aplikacji"**

4. Wybierz:
   - Aplikacja: **Poczta**
   - Urządzenie: **Inne** (wpisz: "PropertyMonitor")

5. **Skopiuj** 16-znakowe hasło (bez spacji)

6. **Wklej** to hasło w konfiguracji (NIE twoje zwykłe hasło!)

---

## 🔍 Co dalej?

### Jednorazowe sprawdzenie (test)
```bash
python real_estate_monitor.py --once
```

### Ciągłe monitorowanie (24/7)
```bash
python real_estate_monitor.py
```

### Analiza zebranych ofert
```bash
python analyze.py
```

---

## 📊 Co dostaniesz?

✅ **Email** gdy pojawi się nowa oferta  
✅ **Dashboard HTML** z listą wszystkich ofert  
✅ **Baza danych SQLite** ze wszystkimi danymi  
✅ **Wykrywanie zmian cen**  
✅ **Filtrowanie według twoich kryteriów**

---

## 🆘 Problemy?

### "Nie mogę zainstalować bibliotek"
```bash
pip install --user -r requirements.txt
```

### "Nie wysyła emaili"
- Sprawdź hasło aplikacji (NIE zwykłe hasło!)
- Upewnij się że masz weryfikację 2-etapową
- Sprawdź czy email jest poprawny

### "Nie znajduje ofert"
- To normalne przy pierwszym uruchomieniu
- Poczekaj kilka minut
- Portale mogą zmieniać strukturę - zgłoś issue

### "Dashboard jest pusty"
- Uruchom najpierw: `python real_estate_monitor.py --once`
- Sprawdź czy jest plik `properties.db`

---

## 📱 Uruchomienie non-stop (24/7)

### Raspberry Pi / Linux server
```bash
# Dodaj do crontab
crontab -e

# Sprawdzaj co godzinę
0 * * * * cd /home/user/monitor && python3 real_estate_monitor.py --once
```

### Windows (Task Scheduler)
1. Otwórz **Task Scheduler**
2. **Create Basic Task**
3. **Trigger**: Daily, repeat every 1 hour
4. **Action**: 
   - Program: `python`
   - Arguments: `C:\path\real_estate_monitor.py --once`

### Cloud (darmowe opcje)
- **PythonAnywhere**: https://www.pythonanywhere.com
- **Render**: https://render.com
- **Fly.io**: https://fly.io

---

## 🎯 Przykładowa konfiguracja

```json
{
  "criteria": {
    "min_price": 280000,
    "max_price": 420000,
    "min_area": 42,
    "max_area": 60,
    "city": "Wrocław"
  },
  "check_interval_minutes": 30,
  "portals": ["otodom", "olx", "gratka"]
}
```

---

## 💡 Pro tipy

1. **Uruchom test najpierw**: `--once` zamiast od razu ciągłego monitorowania
2. **Nie ustawiaj zbyt krótkiego interwału**: 30 minut to minimum
3. **Sprawdzaj dashboard**: Otwórz `dashboard.html` w przeglądarce
4. **Backup bazy**: Skopiuj `properties.db` aby nie stracić danych
5. **Eksportuj do Excel**: Użyj `analyze.py --export`

---

## 📞 Pomoc

Problemy? Pytania?
1. Uruchom: `python test_setup.py`
2. Sprawdź logi
3. Stwórz issue na GitHub

**Powodzenia w poszukiwaniach! 🏠**
