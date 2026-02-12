FROM python:3.11-slim

# Ustaw zmienne środowiskowe
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Warsaw

# Utwórz katalog aplikacji
WORKDIR /app

# Kopiuj pliki wymagań
COPY requirements.txt .

# Instaluj zależności
RUN pip install --no-cache-dir -r requirements.txt

# Kopiuj pliki aplikacji
COPY real_estate_monitor.py .
COPY setup.py .
COPY test_setup.py .
COPY analyze.py .

# Utwórz katalog na dane
RUN mkdir -p /data

# Volume dla trwałych danych
VOLUME /data

# Domyślne polecenie
CMD ["python", "real_estate_monitor.py"]

# Opcjonalne healthcheck
HEALTHCHECK --interval=30m --timeout=10s \
  CMD python -c "import sqlite3; conn = sqlite3.connect('/data/properties.db'); conn.close()" || exit 1
