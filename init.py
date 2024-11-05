import os
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def create_webdriver():
    return webdriver.Chrome()  # Stelle sicher, dass du den ChromeDriver installiert hast

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

def determine_color(prozent_abgeschlossen, thresholds):
    if prozent_abgeschlossen > thresholds['green']:
        return ANSIColors.GREEN
    elif prozent_abgeschlossen > thresholds['yellow']:
        return ANSIColors.YELLOW
    elif prozent_abgeschlossen > thresholds['orange']:
        return ANSIColors.ORANGE
    elif prozent_abgeschlossen > thresholds['red']:
        return ANSIColors.RED
    else:
        return ANSIColors.RESET

def print_checklist_results_header():
    print(f"{'Gesamt':<8}{'Abg':<8}{'% Abg':<10}{'Offen':<8}{'% Offen':<10}{'Thema'}")

def process_single_checkliste(course_name, group_name, activity_name, base_url, common_params, course, group, activity, username, password, namen_anzeigen, status_einschraenkung, thresholds):
    url_with_group = build_url(base_url, common_params, course, group, activity)
    
    driver = create_webdriver()
    try:
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

        print_checklist_results_header()

        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        checklist_results = {title: {'abgeschlossen': [], 'nicht_abgeschlossen': []} for title in checklist_titles}

        for row in rows:
            person_name = row.find_element(By.CSS_SELECTOR, "th a").text
            progress_cells = row.find_elements(By.CSS_SELECTOR, "td.completion-progresscell a img")

            for index, cell in enumerate(progress_cells):
                status = "abgeschlossen" if "completion-auto-y" in cell.get_attribute('src') else "nicht_abgeschlossen"
                checklist_title = checklist_titles[index]

                checklist_results[checklist_title][status].append(person_name)

        for title, results in checklist_results.items():
            total = len(results['abgeschlossen']) + len(results['nicht_abgeschlossen'])
            abgeschlossen = len(results['abgeschlossen'])
            nicht_abgeschlossen = len(results['nicht_abgeschlossen'])
            prozent_abgeschlossen = (abgeschlossen / total) * 100 if total > 0 else 0
            prozent_nicht_abgeschlossen = (nicht_abgeschlossen / total) * 100 if total > 0 else 0

            if (status_einschraenkung == '1' and abgeschlossen == 0) or (status_einschraenkung == '2' and abgeschlossen > 0):
                continue

            color = determine_color(prozent_abgeschlossen, thresholds)

            print(f"{total:<8}{abgeschlossen:<8}{color}{prozent_abgeschlossen:.2f}%{ANSIColors.RESET:<10}{nicht_abgeschlossen:<8}{prozent_nicht_abgeschlossen:.2f}%\t{title} - {url_with_group}")

            if namen_anzeigen and abgeschlossen > 0:
                print("Abgeschlossen:")
                for name in results['abgeschlossen']:
                    print(f"  - {name}")

    finally:
        driver.quit()

def process_single_aufgabe(course_name, group_name, activity_name, base_url, common_params, course, group, activity, username, password, thresholds):
    url_with_group = build_url(base_url, common_params, course, group, activity)
    
    driver = create_webdriver()
    try:
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
                abgegeben_prozent = (abgegeben / teilnehmer) * 100 if teilnehmer > 0 else 0
                if abgegeben == teilnehmer:
                    completed_count += 1

                bewertung_farbe = ANSIColors.RED if bewertung_wert > 0 else ANSIColors.GREEN
                abgeschlossen_farbe = ANSIColors.RED if abgegeben == 0 else ANSIColors.YELLOW

                print_task_info(heading, teilnehmer, abgegeben, abgegeben_prozent, bewertung_wert, link_url_with_group, abgeschlossen_farbe, bewertung_farbe)

        print_summary(total_links, completed_count)
    finally:
        driver.quit()

def process_aufgaben_parallel(base_url, common_params, courses, groups, activities, username, password, namen_anzeigen, status_einschraenkung, thresholds):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for course_name, course_id in courses.items():
            for group_name, group_id in groups.items():
                for activity_name, activity_id in activities.items():
                    if activity_name == "assignments":
                        futures.append(executor.submit(process_single_aufgabe, course_name, group_name, activity_name, base_url, common_params, course_id, group_id, activity_id, username, password, thresholds))
                    elif activity_name == "checklist":
                        futures.append(executor.submit(process_single_checkliste, course_name, group_name, activity_name, base_url, common_params, course_id, group_id, activity_id, username, password, namen_anzeigen, status_einschraenkung, thresholds))
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

def print_summary(total_links, completed_count):
    open_count = total_links - completed_count
    completed_percent = (completed_count / total_links) * 100 if total_links > 0 else 0
    print(f"Anzahl: {total_links}\tAbgeschlossen: {ANSIColors.YELLOW if completed_count > 0 else ANSIColors.RED}{completed_count} ({completed_percent:.2f}%){ANSIColors.RESET}\t\tOffen: {open_count}")

def get_user_selection(courses, groups, activities):
    print("Welche Klasse soll angezeigt werden?")
    options = []
    index = 0

    for course_name in courses:
        for group_name in groups:
            for activity_name in activities:
                options.append((course_name, group_name, activity_name))
                print(f"({index}) {course_name} - {group_name} - {activity_name}")
                index += 1

    auswahl = int(input("Auswahl: "))
    selected_course, selected_group, selected_activity = options[auswahl]
    return selected_course, selected_group, selected_activity

def main():
    config = load_config()
    username = config['login']['username']
    password = config['login']['password']
    base_url = config['urls']['base_url']
    common_params = config['urls']['common_params']
    courses = {key: value for key, value in config['courses'].items()}
    groups = {key: value for key, value in config['groups'].items()}
    activities = {key: value for key, value in config['activities'].items()}
    thresholds = {key: int(value) for key, value in config['thresholds'].items()}

    while True:
        selected_course, selected_group, selected_activity = get_user_selection(courses, groups, activities)

        # Benutzerabfrage für Checklisten-Optionen
        namen_anzeigen = False
        status_einschraenkung = '0'
        if selected_activity == "checklist":
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

        process_aufgaben_parallel(base_url, common_params, {selected_course: courses[selected_course]}, {selected_group: groups[selected_group]}, {selected_activity: activities[selected_activity]}, username, password, namen_anzeigen, status_einschraenkung, thresholds)

        # Abbruchoption
        exit_input = input("Geben Sie '0' ein, um das Programm zu beenden oder drücken Sie 'Enter', um fortzufahren: ")
        if exit_input == '0':
            break

if __name__ == "__main__":
    main()