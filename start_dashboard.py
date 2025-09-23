#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Startskript für das Mebis Statistik Dashboard

Dieses Skript startet das Dashboard und öffnet automatisch den Browser.
"""

import subprocess
import sys
import os
import webbrowser
import time
import threading
from pathlib import Path

def install_requirements():
    """Installiert die benötigten Python-Pakete"""
    print("Überprüfe Python-Abhängigkeiten...")
    try:
        requirements_file = Path("requirements.txt")
        if requirements_file.exists():
            print("Installiere Abhängigkeiten...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("[OK] Abhängigkeiten erfolgreich installiert")
        else:
            print("[FEHLER] requirements.txt nicht gefunden")
            return False
    except subprocess.CalledProcessError as e:
        print(f"[FEHLER] Fehler beim Installieren der Abhängigkeiten: {e}")
        return False
    except Exception as e:
        print(f"[FEHLER] Unerwarteter Fehler: {e}")
        return False
    return True

def check_export_folder():
    """Überprüft, ob der Export-Ordner und Daten vorhanden sind"""
    export_folder = Path("export")
    if not export_folder.exists():
        print("[FEHLER] Export-Ordner nicht gefunden!")
        print("   Bitte stellen Sie sicher, dass der 'export' Ordner mit JSON-Dateien existiert.")
        return False

    json_files = list(export_folder.glob("output_*.json"))
    if not json_files:
        print("[FEHLER] Keine Export-Dateien gefunden!")
        print("   Bitte führen Sie zuerst den Daten-Export aus, um JSON-Dateien zu generieren.")
        return False

    latest_file = max(json_files, key=os.path.getctime)
    print(f"[OK] Export-Daten gefunden: {latest_file.name}")
    return True

def open_browser():
    """Öffnet den Browser nach kurzer Verzögerung"""
    time.sleep(2)  # Warten bis der Server gestartet ist
    webbrowser.open('http://localhost:5000')

def main():
    """Hauptfunktion"""
    print("=" * 60)
    print("         MEBIS STATISTIK DASHBOARD")
    print("=" * 60)
    print()

    # Überprüfung der Voraussetzungen
    if not check_export_folder():
        print("\n[FEHLER] Dashboard kann nicht gestartet werden.")
        input("Drücken Sie Enter zum Beenden...")
        return

    if not install_requirements():
        print("\n[FEHLER] Dashboard kann nicht gestartet werden.")
        input("Drücken Sie Enter zum Beenden...")
        return

    # Browser in separatem Thread öffnen
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    print("\n[START] Starte Dashboard...")
    print("[INFO] Dashboard wird verfügbar sein unter: http://localhost:5000")
    print("[INFO] Browser wird automatisch geöffnet...")
    print("\n[HINWEIS] Drücken Sie Ctrl+C um das Dashboard zu stoppen")
    print("-" * 60)

    try:
        # Dashboard starten
        from dashboard_backend import app
        app.run(debug=False, host='0.0.0.0', port=5000)

    except ImportError as e:
        print(f"[FEHLER] Fehler beim Importieren: {e}")
        print("   Stellen Sie sicher, dass dashboard_backend.py vorhanden ist.")
    except KeyboardInterrupt:
        print("\n\n[STOPP] Dashboard wurde beendet.")
    except Exception as e:
        print(f"\n[FEHLER] Fehler beim Starten des Dashboards: {e}")

    input("\nDrücken Sie Enter zum Beenden...")

if __name__ == "__main__":
    main()