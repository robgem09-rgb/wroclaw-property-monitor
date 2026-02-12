#!/bin/bash

# Start script dla monitora nieruchomości

echo "=================================="
echo "🏠 Monitor Nieruchomości - Start"
echo "=================================="
echo ""

# Sprawdź czy Python jest zainstalowany
if ! command -v python3 &> /dev/null; then
    echo "✗ Python3 nie jest zainstalowany!"
    echo "  Zainstaluj Python 3.8 lub nowszy"
    exit 1
fi

echo "✓ Python: $(python3 --version)"

# Sprawdź czy pip jest zainstalowany
if ! command -v pip3 &> /dev/null; then
    echo "✗ pip3 nie jest zainstalowany!"
    exit 1
fi

echo "✓ pip zainstalowany"

# Instaluj zależności jeśli nie ma
echo ""
echo "📦 Sprawdzam zależności..."

if [ ! -f "requirements.txt" ]; then
    echo "✗ Brak pliku requirements.txt"
    exit 1
fi

pip3 install -r requirements.txt --quiet --user

# Sprawdź czy istnieje plik konfiguracyjny
if [ ! -f "config.json" ]; then
    echo ""
    echo "⚙️  Brak pliku konfiguracyjnego"
    echo "   Uruchamiam kreator konfiguracji..."
    echo ""
    python3 setup.py
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "✗ Błąd podczas konfiguracji"
        exit 1
    fi
fi

# Menu wyboru
echo ""
echo "=================================="
echo "Wybierz opcję:"
echo "=================================="
echo "1. Uruchom jednorazowe sprawdzenie (test)"
echo "2. Uruchom ciągłe monitorowanie"
echo "3. Uruchom testy systemowe"
echo "4. Pokaż analizę zebranych danych"
echo "5. Otwórz dashboard"
echo "6. Edytuj konfigurację"
echo "7. Wyjście"
echo ""

read -p "Wybór (1-7): " choice

case $choice in
    1)
        echo ""
        echo "🔍 Uruchamiam jednorazowe sprawdzenie..."
        python3 real_estate_monitor.py --once
        ;;
    2)
        echo ""
        echo "🚀 Uruchamiam ciągłe monitorowanie..."
        echo "   Naciśnij Ctrl+C aby zatrzymać"
        echo ""
        python3 real_estate_monitor.py
        ;;
    3)
        echo ""
        echo "🧪 Uruchamiam testy..."
        python3 test_setup.py
        ;;
    4)
        echo ""
        python3 analyze.py
        ;;
    5)
        echo ""
        if [ -f "dashboard.html" ]; then
            echo "🌐 Otwieranie dashboard..."
            
            # Próbuj otworzyć w przeglądarce
            if command -v xdg-open &> /dev/null; then
                xdg-open dashboard.html
            elif command -v open &> /dev/null; then
                open dashboard.html
            else
                echo "Otwórz plik dashboard.html w przeglądarce"
            fi
        else
            echo "✗ Brak pliku dashboard.html"
            echo "  Uruchom najpierw monitor aby go wygenerować"
        fi
        ;;
    6)
        echo ""
        echo "⚙️  Edycja konfiguracji..."
        python3 setup.py
        ;;
    7)
        echo ""
        echo "👋 Do zobaczenia!"
        exit 0
        ;;
    *)
        echo ""
        echo "✗ Nieprawidłowy wybór"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "✓ Zakończono"
echo "=================================="
