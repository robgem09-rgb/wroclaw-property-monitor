@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==================================
echo 🏠 Monitor Nieruchomości - Start
echo ==================================
echo.

REM Sprawdź czy Python jest zainstalowany
python --version >nul 2>&1
if errorlevel 1 (
    echo ✗ Python nie jest zainstalowany!
    echo   Zainstaluj Python 3.8 lub nowszy z python.org
    pause
    exit /b 1
)

echo ✓ Python zainstalowany

REM Instaluj zależności
echo.
echo 📦 Sprawdzam zależności...

if not exist requirements.txt (
    echo ✗ Brak pliku requirements.txt
    pause
    exit /b 1
)

pip install -r requirements.txt --quiet --user

REM Sprawdź konfigurację
if not exist config.json (
    echo.
    echo ⚙️  Brak pliku konfiguracyjnego
    echo    Uruchamiam kreator konfiguracji...
    echo.
    python setup.py
    
    if errorlevel 1 (
        echo.
        echo ✗ Błąd podczas konfiguracji
        pause
        exit /b 1
    )
)

:menu
echo.
echo ==================================
echo Wybierz opcję:
echo ==================================
echo 1. Uruchom jednorazowe sprawdzenie (test)
echo 2. Uruchom ciągłe monitorowanie
echo 3. Uruchom testy systemowe
echo 4. Pokaż analizę zebranych danych
echo 5. Otwórz dashboard
echo 6. Edytuj konfigurację
echo 7. Wyjście
echo.

set /p choice="Wybór (1-7): "

if "%choice%"=="1" goto test
if "%choice%"=="2" goto monitor
if "%choice%"=="3" goto tests
if "%choice%"=="4" goto analyze
if "%choice%"=="5" goto dashboard
if "%choice%"=="6" goto config
if "%choice%"=="7" goto exit
goto menu

:test
echo.
echo 🔍 Uruchamiam jednorazowe sprawdzenie...
python real_estate_monitor.py --once
goto end

:monitor
echo.
echo 🚀 Uruchamiam ciągłe monitorowanie...
echo    Naciśnij Ctrl+C aby zatrzymać
echo.
python real_estate_monitor.py
goto end

:tests
echo.
echo 🧪 Uruchamiam testy...
python test_setup.py
goto end

:analyze
echo.
python analyze.py
goto end

:dashboard
echo.
if exist dashboard.html (
    echo 🌐 Otwieranie dashboard...
    start dashboard.html
) else (
    echo ✗ Brak pliku dashboard.html
    echo   Uruchom najpierw monitor aby go wygenerować
)
goto end

:config
echo.
echo ⚙️  Edycja konfiguracji...
python setup.py
goto menu

:exit
echo.
echo 👋 Do zobaczenia!
exit /b 0

:end
echo.
echo ==================================
echo ✓ Zakończono
echo ==================================
pause
