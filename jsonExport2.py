import os
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
import json
import re
import time
from datetime import datetime

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    options = Options()
    if headless == "True":
        options.add_argument('--headless')  # Füge Headless-Argument hinzu
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)  # Stelle sicher, dass du den ChromeDriver installiert hast

def login(driver, username, password, waittime):
    WebDriverWait(driver, waittime).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
    driver.find_element(By.ID, "input-password").send_keys(password)
    driver.find_element(By.ID, "button-do-log-in").click()

def get_select_options(driver, select_name, waittime):
    select_element = WebDriverWait(driver, waittime).until(
        EC.presence_of_element_located((By.NAME, select_name))
    )
    options = select_element.find_elements(By.TAG_NAME, "option")
    return [{"value": option.get_attribute("value"), "name": option.text} for option in options]

def get_user_ids_from_group(driver, group_value, base_url, course_id):
    group_url = f"{base_url}?course={course_id}&group={group_value}"
    driver.get(group_url)
    
    user_elements = driver.find_elements(By.CSS_SELECTOR, "#completion-progress tbody th[scope='row'] a")
    users = [{"id": re.search(r'id=(\d+)', user.get_attribute("href")).group(1), "name": user.text} for user in user_elements]
    return users

def get_activity_urls(driver):
    activity_urls = {
        "assignments": [],
        "checklists": [],
        "feedbacks": [],
        "quizzes": []
    }
    
    activity_elements = driver.find_elements(By.CSS_SELECTOR, "#completion-progress thead th.completion-header a")
    if not activity_elements:
        print("No activity elements found.")
    for element in activity_elements:
        url = element.get_attribute("href")
        title = element.get_attribute("title")
        if "mod/assign/view.php?id=" in url:
            activity_urls["assignments"].append({"id": re.search(r'id=(\d+)', url).group(1), "title": title, "url": url})
        elif "mod/checklist/view.php?id=" in url:
            activity_urls["checklists"].append({"id": re.search(r'id=(\d+)', url).group(1), "title": title, "url": url})
        elif "mod/feedback/view.php?id=" in url:
            activity_urls["feedbacks"].append({"id": re.search(r'id=(\d+)', url).group(1), "title": title, "url": url})
        elif "mod/quiz/view.php?id=" in url:
            activity_urls["quizzes"].append({"id": re.search(r'id=(\d+)', url).group(1), "title": title, "url": url})
    
    return activity_urls

def get_checklist_progress_optimized(driver, checklist_url, sesskey):
    progress_data = {}

    # Erste URL mit 'showprogressbars', um die Fortschrittsbalken anzuzeigen
    url_show_progress_bars = checklist_url.replace('view.php', 'report.php')
    url_show_progress_bars += f"&sesskey={sesskey}&action=showprogressbars&perpage=300&group=0"
    driver.get(url_show_progress_bars)

    # URL zur Anzeige der Pflichtelemente
    url_hide_optional = checklist_url.replace('view.php', 'report.php')
    url_hide_optional += f"&sesskey={sesskey}&action=hideoptional&perpage=300&group=0"
    driver.get(url_hide_optional)

    # Extrahiere den required_progress
    progress_data['required_progress'] = extract_progress(driver)

    # URL zur Anzeige aller Elemente
    url_show_optional = checklist_url.replace('view.php', 'report.php')
    url_show_optional += f"&sesskey={sesskey}&action=showoptional&perpage=300&group=0"
    driver.get(url_show_optional)

    # Extrahiere den all_progress
    progress_data['all_progress'] = extract_progress(driver)

    return progress_data

def extract_progress(driver):
    progress_data = {}
    user_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='user/view.php?id=']")
    progress_elements = driver.find_elements(By.CSS_SELECTOR, "div.checklist_percentcomplete")

    for link, progress in zip(user_links, progress_elements):
        user_id = re.search(r'id=(\d+)', link.get_attribute("href")).group(1)
        progress_percent = progress.text.strip()
        progress_data[user_id] = progress_percent

    return progress_data

def get_assignment_status(driver, assignment_url, waittime):
    # Navigiere zur Bewertungsseite des Assignments mit group=0
    grading_url = f"{assignment_url}&action=grading&group=0"
    driver.get(grading_url)

    try:
        # Überprüfen, ob das tbody-Element vorhanden ist
        tbody_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tbody"))
        )
    except TimeoutException:
        # Kein tbody gefunden, also gibt es keine Abgaben
        return []

    # Finde die Spaltenüberschriften, um die Klasse der "Endbewertung"-Spalte zu ermitteln
    headers = driver.find_elements(By.CSS_SELECTOR, "th.header")
    grade_column_class = None
    for header in headers:
        if "Endbewertung" in header.text:
            # Extrahiere die Klasse, z.B. "c14"
            grade_column_class = header.get_attribute("class").split()[1]
            break

    if not grade_column_class:
        print("Spalte 'Endbewertung' nicht gefunden.")
        return []

    # Finde alle Zeilen in der Tabelle
    rows = tbody_element.find_elements(By.CSS_SELECTOR, "tr")

    user_statuses = []

    for row in rows:
        # Extrahiere die UserID aus der class des tr-Elements
        class_attribute = row.get_attribute("class")
        user_id_match = re.search(r'user(\d+)', class_attribute)
        if not user_id_match:
            continue  # Überspringe Zeilen ohne UserID

        user_id = user_id_match.group(1)

        # Extrahiere die gewünschten Informationen aus den td-Elementen
        try:
            status = row.find_element(By.CSS_SELECTOR, "div.submissionstatussubmitted").text
        except:
            status = "Nicht eingereicht"
        
        try:
            status2 = row.find_element(By.CSS_SELECTOR, "div.submissiongraded").text
        except:
            status2 = "Nicht bewertet"
        
        try:
            submission = row.find_element(By.CSS_SELECTOR, "div.assignsubmission_onlinetext .no-overflow p").text
        except:
            submission = "Keine Abgabe"
        
        grade_options = [option.text for option in row.find_elements(By.CSS_SELECTOR, "select#id_grade option")]
        
        # Verwende die ermittelte Klasse, um die Endbewertung abzurufen
        try:
            grade = row.find_element(By.CSS_SELECTOR, f"td.cell.{grade_column_class}").text
        except:
            grade = "Keine Bewertung"

        user_statuses.append({
            "user_id": user_id,
            "status": status,
            "status2": status2,
            "submission": submission,
            "grade_options": grade_options,
            "grade": grade
        })

    return user_statuses

def get_sesskey(driver):
    # Suche nach dem versteckten Input-Feld mit dem Namen 'sesskey'
    try:
        sesskey_element = driver.find_element(By.CSS_SELECTOR, "input[name='sesskey']")
        return sesskey_element.get_attribute("value")
    except Exception as e:
        print(f"Fehler beim Extrahieren des sesskey: {e}")
        return None
    

def get_all_activity_categories(driver, course_id):
    categories_data = {}

    # Lade die Seite nur einmal
    grade_url = f"https://lernplattform.mebis.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)

    # Verwenden Sie WebDriverWait, um sicherzustellen, dass die Elemente geladen sind
    activity_elements = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.gradeitemheader"))
    )

    for activity_element in activity_elements:
        try:
            # Extrahiere die Aktivitäts-ID aus dem href-Attribut
            href = activity_element.get_attribute("href")
            activity_id_match = re.search(r'\?id=(\d+)', href)
            if not activity_id_match:
                continue

            activity_id = activity_id_match.group(1)

            # Finde die übergeordnete Kategorie
            parent_tr = activity_element.find_element(By.XPATH, "./ancestor::tr")
            category_id = parent_tr.get_attribute("data-parent-category")

            full_id = f"grade-item-{category_id}"
            category_tr = driver.find_element(By.ID, full_id)

            # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
            category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")

            categories_data[activity_id] = {"category_id": category_id, "category_name": category_name}

        except Exception as e:
            print(f"Fehler beim Verarbeiten der Aktivität: {e}")

    return categories_data

def get_activity_category(driver, activity_id, course_id, waittime):
    category_data = {"category_id": "-1", "category_name": "nicht bewertet"}
    print(f"Verarbeite Aktivität ID: {activity_id}")

    grade_url = f"https://lernplattform.mebis.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)
    
    try:
        # Verwenden Sie WebDriverWait, um sicherzustellen, dass das Element geladen ist
        activity_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"a[href*='?id={activity_id}'].gradeitemheader"))
        )
        parent_tr = activity_element.find_element(By.XPATH, "./ancestor::tr")
        category_id = parent_tr.get_attribute("data-parent-category")
        
        full_id = f"grade-item-{category_id}"
        category_tr = driver.find_element(By.ID, full_id)

        # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
        category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")
        
        category_data["category_id"] = category_id
        category_data["category_name"] = category_name
    except Exception as e:
        print(f"Fehler beim Verarbeiten der Aktivität ID {activity_id}: {e}")
    
    return category_data

def group_activities_by_category(activities):
    grouped_activities = {}
    for activity_type in activities:
        for activity in activities[activity_type]:
            category_id = activity.get("category_id")
            category_name = activity.get("category_name")
            if category_id not in grouped_activities:
                grouped_activities[category_id] = {
                    "category_name": category_name,
                    activity_type: []
                }
            grouped_activities[category_id][activity_type].append(activity)
    return grouped_activities

def add_activity_to_category(category_entry, activity_type, activity):
    if activity_type in category_entry:
        category_entry[activity_type].append(activity)
    else:
        category_entry[activity_type] = [activity]


def main():
    # Startzeit des Skripts
    start_time = time.time()

    config = load_config()
    username = config['login']['username']
    password = config['login']['password']
    base_url = config['urls']['base_url']
    course_id = config['courses']['course_ifa12']
    isheadless = config['mode']['headless']
    waittime = config['mode']['waittime']

    driver = create_webdriver(headless=isheadless)
    driver.get(f"{base_url}?course={course_id}")
    
    login(driver, username, password, waittime)

    # Extrahiere den sesskey nach dem Login
    sesskey = get_sesskey(driver)
    if not sesskey:
        print("Sesskey konnte nicht extrahiert werden. Überprüfe den Login-Prozess.")
        driver.quit()
        return

    group_options = get_select_options(driver, "group", waittime)
    activityinclude_options = get_select_options(driver, "activityinclude", waittime)
    activitysection_options = get_select_options(driver, "activitysection", waittime)

    # Erfasse die Aktivitäten einmalig
    activities = get_activity_urls(driver)

    # Aktualisiere Aktivitäten mit Kategorieinformationen
    activities_by_category = []


    # Erfasse alle Kategorieninformationen in einem einzigen Aufruf
    all_categories_data = get_all_activity_categories(driver, course_id)

    # Aktualisiere Aktivitäten mit Kategorieinformationen
    activities_by_category = []


    for activity_type in activities:
        for activity in activities[activity_type]:
            category_data = all_categories_data.get(activity["id"], {"category_id": "-1", "category_name": "nicht bewertet"})
            activity.update(category_data)

            # Suche oder erstelle die Kategorie in der Liste
            category_entry = next((cat for cat in activities_by_category if cat["id"] == category_data["category_id"]), None)
            if not category_entry:
                category_entry = {
                    "id": category_data["category_id"],
                    "category_name": category_data["category_name"],
                    "assignments": [],
                    "checklists": [],
                    "feedbacks": [],
                    "quizzes": []
                }
                activities_by_category.append(category_entry)

            # Füge die Aktivität zur entsprechenden Liste hinzu
            category_entry[activity_type].append(activity)


    print("Analysiere Status Assignments")
    # Erfasse den Status der Assignments für alle Benutzer in group=0
    assignments_status = {}
    for assignment in activities["assignments"]:
        assignments_status[assignment["id"]] = get_assignment_status(driver, assignment["url"], waittime)

    print("Analysiere Status Checkliste")
    # Erfasse den Fortschritt der Checklisten für alle Benutzer in group=0
    checklist_progress = {}
    for checklist in activities["checklists"]:
        checklist_progress[checklist["id"]] = get_checklist_progress_optimized(driver, checklist["url"], sesskey)

    # Zentralisierte Speicherung der Aktivitäten
    data = {
        "activities_by_category": activities_by_category,
        "groups": [],
        "activityincludes": activityinclude_options,
        "activitysections": activitysection_options
    }

    for group in group_options:
        if group["value"] == "0":
            continue  # Überspringe Gruppe 0
        group_data = {
            "name": group["name"],
            "value": group["value"],
            "users": get_user_ids_from_group(driver, group["value"], base_url, course_id)
        }
        data["groups"].append(group_data)

    for group in data["groups"]:
        for user in group["users"]:
            user["activities"] = {
                "assignments": [],
                "checklists": [],
                "feedbacks": [],
                "quizzes": []
            }
            
            # Verwende die zuvor erfassten Assignment-Status
            for assignment in activities["assignments"]:
                user_assignment_status = next((status for status in assignments_status[assignment["id"]] if status["user_id"] == user["id"]), None)
                if user_assignment_status:
                    user["activities"]["assignments"].append({
                        "id": assignment["id"],
                        "status": user_assignment_status,
                        "category_id": assignment.get("category_id"),
                        "category_name": assignment.get("category_name")
                    })

            # Verwende die zuvor erfassten Fortschritte der Checklisten
            for checklist in activities["checklists"]:
                user_checklist_progress = checklist_progress[checklist["id"]]
                required_progress = user_checklist_progress.get('required_progress', {}).get(user["id"])
                all_progress = user_checklist_progress.get('all_progress', {}).get(user["id"])
                if required_progress or all_progress:
                    user["activities"]["checklists"].append({
                        "id": checklist["id"],
                        "progress": {
                            "required_progress": required_progress,
                            "all_progress": all_progress
                        }
                        # ,
                        # "category_id": checklist.get("category_id"),
                        # "category_name": checklist.get("category_name")
                    })

    print("Erstelle JSON Datei")
    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f'./export/output_{timestamp}.json'
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    driver.quit()

    # Endzeit des Skripts
    end_time = time.time()
    duration = end_time - start_time
    duration_minutes = duration / 60  # Umrechnung von Sekunden in Minuten
    print(f"Skript abgeschlossen in {duration_minutes:.2f} Minuten.")

if __name__ == "__main__":
    main()





    