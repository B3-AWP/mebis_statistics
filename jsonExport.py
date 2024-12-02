import configparser
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Konfiguration laden
config = configparser.ConfigParser()
config.read('config.ini')

username = config['login']['username']
password = config['login']['password']
base_url = config['urls']['base_url']
course_id = config['courses']['course_ifa12']

# Selenium WebDriver initialisieren
print("Starte den WebDriver...")
driver = webdriver.Chrome()  # Stelle sicher, dass der ChromeDriver installiert und im PATH ist
driver.get(base_url + '?course=' + course_id + config['urls']['common_params'])

# Anmelden
print("Melde mich an...")
WAIT_TIME = 10
WebDriverWait(driver, WAIT_TIME).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
driver.find_element(By.ID, "input-password").send_keys(password)
driver.find_element(By.ID, "button-do-log-in").click()

# Warten, bis die Seite geladen ist
print("Warte auf das Laden der Seite...")
time.sleep(5)  # Alternativ kannst du auch WebDriverWait verwenden

# HTML der Seite abrufen und mit BeautifulSoup parsen
print("Lade die Kursseite...")
soup = BeautifulSoup(driver.page_source, 'html.parser')

# Daten sammeln
data = []  # Liste zum Speichern der Informationen
assign_urls = []  # Liste zum Speichern von Assign-URLs
print("Beginne mit dem Sammeln der Daten...")

# Tabelle mit den Personen und Aktivitäten finden
table_rows = soup.find_all('tr')

# Überschrift der Aktivitäten extrahieren
header_cells = soup.find_all('th', class_='completion-header')
activity_info = []

print("Extrahiere Aktivitätsüberschriften...")
for header in header_cells:
    activity_link = header.find('a')
    if activity_link:
        activity_title = activity_link['title']
        activity_url = activity_link['href']
        activity_id = activity_url.split('id=')[1]  # ID aus der URL extrahieren
        # Bestimme die Kategorie aus der URL
        activity_category = activity_url.split('/')[4]  # Der 5. Teil des Pfads gibt die Kategorie an

        activity_info.append({
            'activity_title': activity_title,
            'activity_id': activity_id,
            'activity_category': activity_category,
            'activity_url': activity_url
        })

        # Speichere die Assign-URLs für später, mit dem Parameter &action=grading
        if activity_category == 'assign':
            assign_urls.append(activity_url + '&action=grading')

# Einmalige Verarbeitung der Assign-URLs
for assign_url in assign_urls:
    print(f"Verarbeite Bewertungsseite für Assign-Aktivität: {assign_url}...")
    
    # Verwende Selenium, um die Bewertungsseite zu laden
    driver.get(assign_url)
    time.sleep(5)  # Warten, bis die Seite geladen ist
    grading_soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Informationen zur Bewertung extrahieren
    user_rows = grading_soup.find_all('tr')

    for user_row in user_rows:
        # Überprüfen, ob die Klasse mit 'user' beginnt
        user_class = user_row.get('class')
        if user_class and user_class[0].startswith('user'):
            user_id = user_class[0][4:]  # Entferne das 'user'-Präfix
            user_link = user_row.find('a', href=True)
            if user_link:
                user_name = user_link.text.strip()
                
                # Überprüfe, ob die Elemente existieren, bevor du auf sie zugreifst
                submission_status = user_row.find('div', class_='submissionstatussubmitted')
                submission_status = submission_status.text.strip() if submission_status else None

                submission_graded = user_row.find('div', class_='submissiongraded')
                submission_graded = submission_graded.text.strip() if submission_graded else None

                quickgrade_select = user_row.find('select', class_='quickgrade')
                if quickgrade_select:
                    selected_option = quickgrade_select.find('option', selected='selected')
                    grade_value = selected_option.text.strip() if selected_option else None
                else:
                    grade_value = None

                # Füge die Benutzerinformationen zu den entsprechenden Aktivitäten hinzu
                for person in data:
                    for activity in person['activities']:
                        if activity['activity_url'] == assign_url[:-15]:  # Entferne den &action=grading-Teil
                            if 'user_data' not in activity:
                                activity['user_data'] = []
                            activity['user_data'].append({
                                'user_name': user_name,
                                'user_id': user_id,
                                'submission_status': submission_status,
                                'submission_graded': submission_graded,
                                'grade_value': grade_value
                            })

# JSON-Datei zum Schreiben öffnen
print("Speichere die gesammelten Daten in 'activities_data.json'...")
with open('activities_data.json', 'w', encoding='utf-8') as json_file:
    json.dump(data, json_file, ensure_ascii=False, indent=4)

# WebDriver schließen
driver.quit()

print("Daten wurden erfolgreich in 'activities_data.json' geschrieben.")