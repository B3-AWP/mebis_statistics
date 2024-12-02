import os
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Konfiguration
WAIT_TIME = 3  # Wartezeit in Sekunden, erhöht für langsam ladende Seiten

# ANSI-Escape-Sequenzen für Farben
class ANSIColors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    ORANGE = '\033[33m'
    RESET = '\033[0m'

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    options = Options()
    if headless:
        options.add_argument('--headless')  # Füge Headless-Argument hinzu
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)  # Stelle sicher, dass du den ChromeDriver installiert hast

def login(driver, username, password):
    WebDriverWait(driver, WAIT_TIME).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
    driver.find_element(By.ID, "input-password").send_keys(password)
    driver.find_element(By.ID, "button-do-log-in").click()

def extract_links_from_table(driver):
    table = driver.find_element(By.ID, "completion-progress")
    links = table.find_elements(By.CSS_SELECTOR, "th.completion-header a")
    return [link.get_attribute('href') for link in links]

def build_url(base_url, common_params, course, group, activity):
    query_params = f"course={course}&activityinclude={activity}&group={group}{common_params}"
    return f"{base_url}?{query_params}"

def determine_color(prozent_abgeschlossen, thresholds, order):
    color_order = ['green', 'yellow', 'orange', 'red'] if order == 1 else ['red', 'orange', 'yellow', 'green']
    
    for color in color_order:
        if prozent_abgeschlossen > thresholds[color]:
            return getattr(ANSIColors, color.upper())
    
    return ANSIColors.RESET


def print_checklist_results_header():
    print(f"{'Gesamt':<8}{'Abg':<8}{'% Abg':<10}{'Offen':<8}{'% Offen':<10}{'Thema'}")

def print_assign_results_header():
    print(f"{'Gesamt':<6}\t{'Abg':<10}{'Offen':<5}\t\t{'Thema'}")



def process_single_checkliste(course_name, group_name, activity_name, base_url, common_params, course, group, activity, username, password, namen_anzeigen, status_einschraenkung, thresholds, driver):
    url_with_group = build_url(base_url, common_params, course, group, activity)
    
    print(f"Kurs: {course_name}")
    print(f"  Gruppe: {group_name}")
    print(f"    {activity_name} - Checklisten")
    driver.get(url_with_group)
    
    if "login" in driver.current_url:
        login(driver, username, password)

    WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.ID, "completion-progress")))

    # Extrahiere die Checklisten-Spaltenüberschriften
    headers = driver.find_elements(By.CSS_SELECTOR, "th.completion-header a")
    checklist_titles = [header.get_attribute('title') for header in headers]
    checklist_links = [header.get_attribute('href') for header in headers]  # Extrahiere die Links
    checklist_dict = {title: link for title, link in zip(checklist_titles, checklist_links)}
    print_checklist_results_header()

    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    checklist_results = {title: {'link': checklist_dict[title], 'abgeschlossen': [], 'nicht_abgeschlossen': []} for title in checklist_titles}

    for row in rows:
        person_name = row.find_element(By.CSS_SELECTOR, "th a").text
        progress_cells = row.find_elements(By.CSS_SELECTOR, "td.completion-progresscell a img")

        for index, cell in enumerate(progress_cells):
            status = "abgeschlossen" if "completion-auto-y" in cell.get_attribute('src') else "nicht_abgeschlossen"
            checklist_title = checklist_titles[index]

            checklist_results[checklist_title][status].append(person_name)

    for title, results in checklist_results.items():
        specific_link = results['link']
        total = len(results['abgeschlossen']) + len(results['nicht_abgeschlossen'])
        abgeschlossen = len(results['abgeschlossen'])
        nicht_abgeschlossen = len(results['nicht_abgeschlossen'])
        prozent_abgeschlossen = (abgeschlossen / total) * 100 if total > 0 else 0
        prozent_nicht_abgeschlossen = (nicht_abgeschlossen / total) * 100 if total > 0 else 0

        if (status_einschraenkung == '1' and abgeschlossen == 0) or (status_einschraenkung == '2' and abgeschlossen > 0):
            continue

        color = determine_color(prozent_abgeschlossen, thresholds, 1)
        # Verwende den spezifischen Link für die Checkliste

        print(f"{total:>8}{abgeschlossen:>8}{color}{int(prozent_abgeschlossen):>3}%{ANSIColors.RESET:<10}{nicht_abgeschlossen:>8}{int(prozent_nicht_abgeschlossen):>3}%\t{title} - {specific_link}")

        if namen_anzeigen and abgeschlossen > 0:
            print("Abgeschlossen:")
            for name in results['abgeschlossen']:
                print(f"  - {name}")


def process_single_aufgabe(course_name, group_name, activity_name, base_url, common_params, course, group, activity, username, password, thresholds, driver):
    url_with_group = build_url(base_url, common_params, course, group, activity)
    

    print(f"Kurs: {course_name}")
    print(f"  Gruppe: {group_name}")
    print(f"    {activity_name} - Aufgaben")
    driver.get(url_with_group)
    
    if "login" in driver.current_url:
        login(driver, username, password)

    WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.ID, "completion-progress")))
    link_urls = extract_links_from_table(driver)

    total_links = len(link_urls)
    completed_count = 0
    eingereicht_sum = 0
    bewertet_sum = 0
    persons = 0

    print_assign_results_header()


    for link_url in link_urls:
        link_url_with_group = build_url(link_url, '', '', group, '')
        driver.get(link_url_with_group)

        # Alternative Selektoren ausprobieren
        try:
            WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.generaltable.table-bordered")))
        except TimeoutException:
            print("Tabelle nicht gefunden, versuche alternativen Selektor")
            WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'generaltable')]")))

        heading = extract_heading(driver)
        teilnehmer, abgegeben, bewertung_wert = extract_task_info(driver)

        if abgegeben != -1:
            persons = teilnehmer
            eingereicht_sum += abgegeben
            bewertet_sum += bewertung_wert
            abgegeben_prozent = (abgegeben / teilnehmer) * 100 if teilnehmer > 0 else 0
            if abgegeben == teilnehmer:
                completed_count += 1

            # Einheitliche Ausgabeformatierung
            color = determine_color(abgegeben_prozent, thresholds, 1)
            color_bewertung_offen = determine_color(bewertung_wert, thresholds, 0)

            print(f"{teilnehmer:>6}\t{color}{abgegeben:>3} ({int(abgegeben_prozent):>3}%) {color_bewertung_offen}{bewertung_wert:>5}\t{ANSIColors.RESET}{heading} - {link_url_with_group}")


    print_summary(total_links, completed_count, eingereicht_sum, bewertet_sum, persons)

def process_aufgaben_parallel(base_url, common_params, courses, groups, activities, username, password, namen_anzeigen, status_einschraenkung, thresholds, driver):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for course_name, course_id in courses.items():
            for group_name, group_id in groups.items():
                for activity_name, activity_id in activities.items():
                    if activity_name == "assignments":
                        futures.append(executor.submit(process_single_aufgabe, course_name, group_name, activity_name, base_url, common_params, course_id, group_id, activity_id, username, password, thresholds, driver))
                    elif activity_name == "checklist":
                        futures.append(executor.submit(process_single_checkliste, course_name, group_name, activity_name, base_url, common_params, course_id, group_id, activity_id, username, password, namen_anzeigen, status_einschraenkung, thresholds, driver))
        for future in futures:
            future.result()  # Warten auf die Fertigstellung aller Threads

def extract_heading(driver):
    try:
        return driver.find_element(By.TAG_NAME, "h1").text
    except Exception:
        return "Keine Überschrift gefunden"


def extract_task_info(driver):
    teilnehmer_elements = driver.find_elements(By.XPATH, "//tr[th[text()='Teilnehmer/innen']]/td")
    teilnehmer = int(teilnehmer_elements[0].text) if teilnehmer_elements else -1

    abgegeben_elements = driver.find_elements(By.XPATH, "//tr[th[text()='Abgegeben']]/td")
    abgegeben = int(abgegeben_elements[0].text) if abgegeben_elements else -1

    bewertung_elements = driver.find_elements(By.XPATH, "//tr[th[text()='Bewertung erwartet']]/td")
    bewertung_wert = int(bewertung_elements[0].text) if bewertung_elements else -1

    return teilnehmer, abgegeben, bewertung_wert

def print_task_info(heading, teilnehmer, abgegeben, abgegeben_prozent, bewertung_wert, link_url, abgeschlossen_farbe, bewertung_farbe):
    print("\t########################################################")
    print(f"\t{heading},")
    print(f"\t\tGesamt: {teilnehmer}\tAbgeschlossen: {abgeschlossen_farbe}{abgegeben} ({abgegeben_prozent:.2f}%){ANSIColors.RESET}\t\tOffen: {bewertung_farbe}{bewertung_wert}{ANSIColors.RESET}")
    print(f"\t\t{link_url}\n")


def print_summary(anzahl_aufgaben, anzahl_abgeschlossner_aufgaben, anzahl_eingereicht, anzahl_bewertet, anzahl_teilnehmer):
    anzahl_eingereicht_prozent = anzahl_eingereicht / (anzahl_aufgaben * anzahl_teilnehmer) * 100
    anzahl_bewertet_prozent = anzahl_bewertet / anzahl_eingereicht * 100

    print("\n")
    print(f"\tGesamt: \t{anzahl_aufgaben}")
    print(f"\tAbgeschlossen: {anzahl_abgeschlossner_aufgaben}")
    print(f"\tEingereicht:\t{anzahl_eingereicht}\t({anzahl_eingereicht_prozent:.2f}%)")
    print(f"\tBewertung offen:\t{anzahl_bewertet}\t({anzahl_bewertet_prozent:.2f}%)")
    print("\n")
    

def get_user_selection(courses, groups, activities):
    options = []
    
    # TODO: Fehlerhafte Usereingabe abfangen.
    # Kursauswahl
    if len(courses) > 1:
        print("Welcher Kurs soll angezeigt werden?")
        for index, course_name in enumerate(courses):
            print(f"({index}) {course_name}")
        selected_course_index = int(input("Auswahl: "))
        selected_course = list(courses.keys())[selected_course_index]
    else:
        selected_course = list(courses.keys())[0]

    # TODO: Fehlerhafte Usereingabe abfangen.
    # Gruppenauswahl
    if len(groups) > 1:
        print("Welche Gruppe soll angezeigt werden?")
        for index, group_name in enumerate(groups):
            print(f"({index}) {group_name}")
        selected_group_index = int(input("Auswahl: "))
        selected_group = list(groups.keys())[selected_group_index]
    else:
        selected_group = list(groups.keys())[0]

    # TODO: Fehlerhafte Usereingabe abfangen.
    # Aktivitätenauswahl
    print("Welche Aktivität soll angezeigt werden?")
    for index, activity_name in enumerate(activities):
        print(f"({index}) {activity_name}")
    print(f"({len(activities)}) Alle Aktivitäten")
    selected_activity_index = int(input("Auswahl: "))
    
    if selected_activity_index == len(activities):
        selected_activity = activities  # Alle Aktivitäten
    else:
        selected_activity = list(activities.keys())[selected_activity_index]

    return selected_course, selected_group, selected_activity

def main():
    config = load_config()
    username = config['login']['username']
    password = config['login']['password']
    base_url = config['urls']['base_url']
    common_params = config['urls']['common_params']
    debug_mode = config['mode']['headless']
    courses = {key: value for key, value in config['courses'].items()}
    groups = {key: value for key, value in config['groups'].items()}
    activities = {key: value for key, value in config['activities'].items()}
    thresholds = {key: int(value) for key, value in config['thresholds'].items()}

    # Webdriver zu Beginn erstellen
    if debug_mode == "True":
        driver = create_webdriver(True)
    else:
        driver = create_webdriver()


    try:
        while True:
            selected_course, selected_group, selected_activity = get_user_selection(courses, groups, activities)

            # Benutzerabfrage für Checklisten-Optionen
            namen_anzeigen = False
            status_einschraenkung = '0'

            # Todo Crash bei auswahl aller Aktivitäten!
            if selected_activity == "assignments":
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

            # TODO kann nicht beides ausführen!
            process_aufgaben_parallel(base_url, common_params, {selected_course: courses[selected_course]}, {selected_group: groups[selected_group]}, {selected_activity: activities[selected_activity]}, username, password, namen_anzeigen, status_einschraenkung, thresholds, driver)

            # Abbruchoption 
            exit_input = input("Geben Sie '0' ein, um das Programm zu beenden oder drücken Sie 'Enter', um fortzufahren: ")
            if exit_input == '0':
                break
    finally:
        driver.quit()  # Webdriver am Ende schließen

if __name__ == "__main__":
    main()