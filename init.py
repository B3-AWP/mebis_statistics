import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Parameter festlegen
WAIT_TIME = 3 # Wartezeit in Sekunden

# Konfiguration einlesen
config = configparser.ConfigParser()
config.read('config.ini')

username = config['login']['username']
password = config['login']['password']

# URLs aus den verschiedenen Abschnitten der Konfiguration lesen
aufgaben_urls = config['aufgaben']
checklisten_urls = config['checklisten']

# Selenium WebDriver starten
driver = webdriver.Chrome()  # Stelle sicher, dass du den ChromeDriver installiert hast

# Funktion zum Anmelden
def login():
    # Warte, bis das Eingabefeld für den Benutzernamen sichtbar ist und gebe den Benutzernamen ein
    WebDriverWait(driver, WAIT_TIME).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
    # Gebe das Passwort ein
    driver.find_element(By.ID, "input-password").send_keys(password)
    # Klicke auf den Anmeldebutton
    driver.find_element(By.ID, "button-do-log-in").click()

def process_aufgaben(urls):
    for url_name, url in urls.items():
        print(f"Verarbeite Aufgabe - {url_name}: {url}")
        driver.get(url)
        
        # Prüfen, ob die Login-Seite angezeigt wird
        if "login" in driver.current_url:
            login()

        # Warte, bis die Tabelle geladen ist
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.ID, "completion-progress")))

        # Extrahiere alle relevanten URLs aus der Tabelle
        table = driver.find_element(By.ID, "completion-progress")
        links = table.find_elements(By.CSS_SELECTOR, "th.completion-header a")

        # Speichere die URLs in einer Liste, um StaleElementReferenceException zu vermeiden
        link_urls = [link.get_attribute('href') for link in links]

        # Ausgabe des Keys der hinterlegten URL
        print(f"Gefundene URLs für Aufgabe - {url_name}:")

        # URLs ausgeben und prüfen, ob Bewertung erwartet wird
        for link_url in link_urls:
            print(link_url)

            # Besuche die gefundene URL
            driver.get(link_url)

            # Warte, bis die Tabelle mit den Bewertungsinformationen geladen ist
            WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.generaltable.table-bordered")))

            # Extrahiere die Überschrift im <h1>-Tag
            try:
                heading = driver.find_element(By.TAG_NAME, "h1").text
            except Exception as e:
                heading = "Keine Überschrift gefunden"

            # Extrahiere die relevanten Informationen aus der Tabelle
            teilnehmer = int(driver.find_element(By.XPATH, "//tr[th[text()='Teilnehmer/innen']]/td").text)
            abgegeben = int(driver.find_element(By.XPATH, "//tr[th[text()='Abgegeben']]/td").text)
            bewertung_row = driver.find_element(By.XPATH, "//tr[th[text()='Bewertung erwartet']]")
            bewertung_wert = int(bewertung_row.find_element(By.CSS_SELECTOR, "td.cell.c1").text)

            # Berechne den Prozentsatz der Abgaben
            abgegeben_prozent = (abgegeben / teilnehmer) * 100 if teilnehmer > 0 else 0

            # Ausgabe der Informationen in einer Zeile
            print(f"Überschrift: {heading}, Teilnehmer/innen: {teilnehmer}, Abgegeben: {abgegeben}, Abgegeben in %: {abgegeben_prozent:.2f}%, Bewertung erwartet: {bewertung_wert}")

def process_checklisten(urls, namen_anzeigen, status_einschraenkung):
    for url_name, url in urls.items():
        print(f"Verarbeite Checkliste - {url_name}: {url}")
        driver.get(url)
        
        # Prüfen, ob die Login-Seite angezeigt wird
        if "login" in driver.current_url:
            login()

        # Warte, bis die Tabelle geladen ist
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.ID, "completion-progress")))

        # Extrahiere die Checklisten-Spaltenüberschriften
        headers = driver.find_elements(By.CSS_SELECTOR, "th.completion-header a")
        checklist_titles = [header.get_attribute('title') for header in headers]

        # Ausgabe der Checklistenüberschriften
        print(f"Checklisten für {url_name}: {', '.join(checklist_titles)}")

        # Extrahiere jede Zeile der Tabelle (jede Person)
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

        # Initialisiere Datenstrukturen zum Speichern der Ergebnisse
        checklist_results = {title: {'abgeschlossen': [], 'nicht_abgeschlossen': []} for title in checklist_titles}

        for row in rows:
            # Extrahiere den Namen der Person
            person_name = row.find_element(By.CSS_SELECTOR, "th a").text

            # Extrahiere den Abschlussstatus für jede Checkliste
            progress_cells = row.find_elements(By.CSS_SELECTOR, "td.completion-progresscell a img")

            for index, cell in enumerate(progress_cells):
                status = "abgeschlossen" if "completion-auto-y" in cell.get_attribute('src') else "nicht_abgeschlossen"
                checklist_title = checklist_titles[index]

                if status == "abgeschlossen":
                    checklist_results[checklist_title]['abgeschlossen'].append(person_name)
                else:
                    checklist_results[checklist_title]['nicht_abgeschlossen'].append(person_name)

        # Ausgabe der Ergebnisse
        for title, results in checklist_results.items():
            total = len(results['abgeschlossen']) + len(results['nicht_abgeschlossen'])
            abgeschlossen = len(results['abgeschlossen'])
            nicht_abgeschlossen = len(results['nicht_abgeschlossen'])
            prozent_abgeschlossen = (abgeschlossen / total) * 100 if total > 0 else 0
            prozent_nicht_abgeschlossen = (nicht_abgeschlossen / total) * 100 if total > 0 else 0

            # Filter basierend auf der Status-Einschränkung
            if status_einschraenkung == '1' and abgeschlossen == 0:
                continue
            if status_einschraenkung == '2' and abgeschlossen > 0:
                continue

            print(f"{title}")
            print(f"abgeschlossen: {abgeschlossen} von {total} Personen ({prozent_abgeschlossen:.2f} %)")
            if namen_anzeigen and abgeschlossen > 0:
                print("abgeschlossen:")
                for name in results['abgeschlossen']:
                    print(f"  - {name}")
            print(f"nicht abgeschlossen: {nicht_abgeschlossen} von {total} Personen ({prozent_nicht_abgeschlossen:.2f} %)")
            if namen_anzeigen and nicht_abgeschlossen > 0:
                print("nicht abgeschlossen:")
                for name in results['nicht_abgeschlossen']:
                    print(f"  - {name}")

# Benutzerabfrage für die Auswahl der Klasse
print("Welche Klasse soll angezeigt werden?")
print("(0) Alle")
print("(1) Alle Aufgaben")
print("(2) Alle Checklisten")
print("(3) IFA12A - Aufgaben")
print("(4) IFA12B - Aufgaben")
print("(5) IFA12A - Checklisten")
print("(6) IFA12B - Checklisten")
auswahl = input("Auswahl: ")

# Basierend auf der Auswahl des Benutzers werden die entsprechenden URLs verarbeitet
selected_aufgaben = {}
selected_checklisten = {}

if auswahl == '0':
    selected_aufgaben = aufgaben_urls
    selected_checklisten = checklisten_urls
elif auswahl == '1':
    selected_aufgaben = aufgaben_urls
elif auswahl == '2':
    selected_checklisten = checklisten_urls
elif auswahl == '3':
    selected_aufgaben = {'IFA12A': aufgaben_urls['IFA12A']}
elif auswahl == '4':
    selected_aufgaben = {'IFA12B': aufgaben_urls['IFA12B']}
elif auswahl == '5':
    selected_checklisten = {'IFA12A': checklisten_urls['IFA12A']}
elif auswahl == '6':
    selected_checklisten = {'IFA12B': checklisten_urls['IFA12B']}
else:
    print("Ungültige Eingabe. Bitte eine gültige Option wählen.")

namen_anzeigen = False
status_einschraenkung = '0'
if selected_checklisten:
    print("Namen anzeigen")
    print("(0) Nein")
    print("(1) Ja")
    namen_antwort = input("Eingabe: ")
    namen_anzeigen = namen_antwort == '1'

    print("Checklisten-Status einschränken")
    print("(0) Keine Einschränkung")
    print("(1) nur Checklisten die mind. 1 Mal abgeschlossen sind")
    print("(2) nur Checklisten, die von niemanden abgeschlossen sind")
    status_einschraenkung = input("Auswahl: ")

# Weiterverarbeitung der ausgewählten URLs
try:
    if selected_aufgaben:
        process_aufgaben(selected_aufgaben)
    if selected_checklisten:
        process_checklisten(selected_checklisten, namen_anzeigen, status_einschraenkung)
finally:
    # Beende den WebDriver
    driver.quit()