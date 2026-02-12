#!/usr/bin/env python3
"""
Analiza zebranych danych o nieruchomościach
"""

import sqlite3
from datetime import datetime, timedelta
import statistics

def analyze_properties():
    """Analizuje zebrane oferty"""
    
    try:
        conn = sqlite3.connect('properties.db')
        cursor = conn.cursor()
        
        print("\n" + "="*60)
        print("📊 ANALIZA RYNKU NIERUCHOMOŚCI - WROCŁAW")
        print("="*60)
        print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Ogólne statystyki
        cursor.execute('SELECT COUNT(*) FROM properties WHERE is_active = 1')
        total = cursor.fetchone()[0]
        
        if total == 0:
            print("⚠️  Brak ofert w bazie danych")
            print("   Uruchom najpierw: python real_estate_monitor.py --once")
            return
        
        print(f"📈 OGÓLNE STATYSTYKI\n")
        print(f"  Łączna liczba ofert: {total}")
        
        # Statystyki po portalach
        cursor.execute('''
            SELECT portal, COUNT(*) 
            FROM properties 
            WHERE is_active = 1 
            GROUP BY portal
        ''')
        
        print("\n  Podział według portali:")
        for portal, count in cursor.fetchall():
            percentage = (count / total) * 100
            print(f"    • {portal.upper()}: {count} ({percentage:.1f}%)")
        
        # Statystyki cen
        cursor.execute('''
            SELECT 
                MIN(price), 
                MAX(price), 
                AVG(price),
                AVG(price_per_m2),
                MIN(price_per_m2),
                MAX(price_per_m2)
            FROM properties 
            WHERE is_active = 1
        ''')
        
        min_price, max_price, avg_price, avg_per_m2, min_per_m2, max_per_m2 = cursor.fetchone()
        
        print(f"\n💰 CENY\n")
        print(f"  Najniższa cena: {min_price:,.0f} PLN")
        print(f"  Najwyższa cena: {max_price:,.0f} PLN")
        print(f"  Średnia cena: {avg_price:,.0f} PLN")
        print(f"\n  Cena za m²:")
        print(f"    Min: {min_per_m2:,.0f} PLN/m²")
        print(f"    Średnia: {avg_per_m2:,.0f} PLN/m²")
        print(f"    Max: {max_per_m2:,.0f} PLN/m²")
        
        # Statystyki metrażu
        cursor.execute('''
            SELECT MIN(area), MAX(area), AVG(area)
            FROM properties 
            WHERE is_active = 1 AND area > 0
        ''')
        
        min_area, max_area, avg_area = cursor.fetchone()
        
        print(f"\n📐 METRAŻ\n")
        print(f"  Najmniejsze: {min_area:.1f} m²")
        print(f"  Największe: {max_area:.1f} m²")
        print(f"  Średnia: {avg_area:.1f} m²")
        
        # TOP 10 najtańszych za m²
        cursor.execute('''
            SELECT title, price, area, price_per_m2, location, portal, url
            FROM properties 
            WHERE is_active = 1 AND area > 0
            ORDER BY price_per_m2 ASC
            LIMIT 10
        ''')
        
        print(f"\n🏆 TOP 10 - NAJTAŃSZE ZA M²\n")
        for i, (title, price, area, ppm2, location, portal, url) in enumerate(cursor.fetchall(), 1):
            print(f"  {i}. {ppm2:,.0f} PLN/m² - {title[:50]}...")
            print(f"     {price:,.0f} PLN • {area}m² • {location} • {portal}")
            print(f"     {url}\n")
        
        # Najnowsze oferty (ostatnie 24h)
        yesterday = datetime.now() - timedelta(days=1)
        cursor.execute('''
            SELECT COUNT(*) 
            FROM properties 
            WHERE is_active = 1 AND first_seen > ?
        ''', (yesterday,))
        
        new_24h = cursor.fetchone()[0]
        
        print(f"\n⏰ AKTYWNOŚĆ\n")
        print(f"  Nowych ofert (24h): {new_24h}")
        
        # Dystrybucja cen (przedziały)
        price_ranges = [
            (0, 200000, "< 200k"),
            (200000, 300000, "200k-300k"),
            (300000, 400000, "300k-400k"),
            (400000, 500000, "400k-500k"),
            (500000, 600000, "500k-600k"),
            (600000, float('inf'), "> 600k")
        ]
        
        print(f"\n📊 ROZKŁAD CEN\n")
        for min_p, max_p, label in price_ranges:
            cursor.execute('''
                SELECT COUNT(*) 
                FROM properties 
                WHERE is_active = 1 AND price >= ? AND price < ?
            ''', (min_p, max_p))
            
            count = cursor.fetchone()[0]
            if count > 0:
                percentage = (count / total) * 100
                bar = "█" * int(percentage / 2)
                print(f"  {label:>10}: {bar} {count} ({percentage:.1f}%)")
        
        # Najpopularniejsze lokalizacje
        cursor.execute('''
            SELECT location, COUNT(*) as cnt
            FROM properties 
            WHERE is_active = 1 AND location != ''
            GROUP BY location
            ORDER BY cnt DESC
            LIMIT 5
        ''')
        
        locations = cursor.fetchall()
        if locations:
            print(f"\n📍 NAJPOPULARNIEJSZE LOKALIZACJE\n")
            for loc, count in locations:
                percentage = (count / total) * 100
                print(f"  {loc}: {count} ({percentage:.1f}%)")
        
        print("\n" + "="*60 + "\n")
        
        conn.close()
        
    except Exception as e:
        print(f"✗ Błąd: {e}")

def export_to_csv():
    """Eksportuje dane do CSV"""
    import csv
    
    try:
        conn = sqlite3.connect('properties.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                portal, title, price, area, price_per_m2, 
                location, url, first_seen, last_seen
            FROM properties 
            WHERE is_active = 1
            ORDER BY first_seen DESC
        ''')
        
        filename = f"properties_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Portal', 'Tytuł', 'Cena', 'Metraż', 'Cena za m²',
                'Lokalizacja', 'URL', 'Pierwsze zobaczenie', 'Ostatnie zobaczenie'
            ])
            writer.writerows(cursor.fetchall())
        
        print(f"✓ Dane wyeksportowane do: {filename}")
        
        conn.close()
        
    except Exception as e:
        print(f"✗ Błąd eksportu: {e}")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--export':
        export_to_csv()
    else:
        analyze_properties()
        
        print("\nChcesz wyeksportować dane do CSV?")
        if input("(t/n): ").lower() == 't':
            export_to_csv()
