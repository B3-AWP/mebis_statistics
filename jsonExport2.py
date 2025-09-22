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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    options = Options()
    if headless == "True":
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    # Performance-Optimierungen (sicher)
    options.add_argument('--disable-images')  # Bilder nicht laden
    options.add_argument('--disable-plugins') # Plugins deaktivieren
    options.add_argument('--disable-extensions') # Extensions deaktivieren
    options.add_argument('--disable-features=VizDisplayCompositor') # GPU deaktivieren
    options.add_argument('--disable-gpu')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-translate')
    options.add_argument('--hide-scrollbars')
    options.add_argument('--mute-audio')

    # Memory und CPU Optimierungen
    options.add_argument('--memory-pressure-off')
    options.add_argument('--max_old_space_size=4096')

    # Sicherere Performance-Einstellungen
    options.add_argument('--aggressive-cache-discard')
    options.add_argument('--disable-ipc-flooding-protection')

    return webdriver.Chrome(options=options)

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

# Thread-local storage for WebDriver instances
thread_local = threading.local()

def get_thread_driver(isheadless, username=None, password=None, base_url=None, course_id=None):
    """Get or create a WebDriver instance for the current thread"""
    if not hasattr(thread_local, 'driver'):
        thread_local.driver = create_webdriver(headless=isheadless)
        thread_local.logged_in = False
        thread_local.sesskey = None

    # Login und sesskey für jeden Thread
    if not thread_local.logged_in and username and password:
        thread_local.driver.get(f"{base_url}?course={course_id}")
        if "login" in thread_local.driver.current_url:
            login(thread_local.driver, username, password, 10)

        # Extrahiere sesskey für diesen Thread
        thread_local.sesskey = get_sesskey(thread_local.driver)
        thread_local.logged_in = True

    return thread_local.driver

def get_thread_sesskey():
    """Get the sesskey for the current thread"""
    if hasattr(thread_local, 'sesskey'):
        return thread_local.sesskey
    return None

def process_assignment_parallel(assignment, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single assignment in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id)
        assignment_id = assignment["id"]
        assignment_url = assignment["url"]
        assignment_title = assignment.get("title", f"Assignment {assignment_id}")

        print(f"[{index+1}/{total}] Verarbeite Assignment: {assignment_title[:50]}...")
        start_time = time.time()
        status = get_assignment_status(driver, assignment_url, waittime)
        duration = time.time() - start_time
        print(f"  └─ Abgeschlossen in {duration:.1f}s ({len(status)} Einträge)")
        return assignment_id, status
    except Exception as e:
        print(f"❌ Fehler bei Assignment {assignment.get('id', 'unknown')}: {e}")
        return assignment.get('id', 'unknown'), []

def process_checklist_parallel(checklist, isheadless, username, password, base_url, course_id, index, total):
    """Process a single checklist in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id)
        thread_sesskey = get_thread_sesskey()

        if not thread_sesskey:
            print(f"❌ Fehler: Kein sesskey für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        checklist_id = checklist["id"]
        checklist_url = checklist["url"]
        checklist_title = checklist.get("title", f"Checklist {checklist_id}")

        print(f"[{index+1}/{total}] Verarbeite Checklist: {checklist_title[:50]}...")
        start_time = time.time()
        progress = get_checklist_progress_optimized(driver, checklist_url, thread_sesskey)
        duration = time.time() - start_time

        req_count = len(progress.get('required_progress', {}))
        all_count = len(progress.get('all_progress', {}))
        print(f"  └─ Abgeschlossen in {duration:.1f}s ({req_count} req, {all_count} all)")
        return checklist_id, progress
    except Exception as e:
        print(f"❌ Fehler bei Checklist {checklist.get('id', 'unknown')}: {e}")
        return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}
    

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

def cleanup_thread_drivers():
    """Cleanup WebDriver instances in all threads"""
    try:
        if hasattr(thread_local, 'driver'):
            thread_local.driver.quit()
            delattr(thread_local, 'driver')
    except:
        pass


def main():
    # Startzeit des Skripts
    start_time = time.time()
    print("🚀 Starte Mebis-Datenexport...")
    print(f"⏰ Startzeit: {datetime.now().strftime('%H:%M:%S')}")

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


    print("Analysiere Status Assignments (parallel)")
    assignments_status = {}

    # Bestimme die Anzahl der Worker-Threads basierend auf der Anzahl der Assignments
    max_workers = min(2, len(activities["assignments"]))  # Maximal 2 parallel für Stabilität

    if activities["assignments"]:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Future-Tasks für alle Assignments
            future_to_assignment = {
                executor.submit(process_assignment_parallel, assignment, isheadless, waittime, username, password, base_url, course_id, idx, len(activities["assignments"])): assignment
                for idx, assignment in enumerate(activities["assignments"])
            }

            # Sammle die Ergebnisse
            for future in as_completed(future_to_assignment):
                assignment_id, status = future.result()
                assignments_status[assignment_id] = status

    print("Analysiere Status Checkliste (parallel)")
    checklist_progress = {}

    # Bestimme die Anzahl der Worker-Threads basierend auf der Anzahl der Checklists
    max_workers = min(2, len(activities["checklists"]))

    if activities["checklists"]:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Future-Tasks für alle Checklists
            future_to_checklist = {
                executor.submit(process_checklist_parallel, checklist, isheadless, username, password, base_url, course_id, idx, len(activities["checklists"])): checklist
                for idx, checklist in enumerate(activities["checklists"])
            }

            # Sammle die Ergebnisse
            for future in as_completed(future_to_checklist):
                checklist_id, progress = future.result()
                checklist_progress[checklist_id] = progress

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

    print("Erstelle JSON Datei...")
    json_start_time = time.time()

    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f'./export/output_{timestamp}.json'

    # Optimierte JSON-Serialisierung ohne Einrückung für bessere Performance
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    json_duration = time.time() - json_start_time
    print(f"✅ JSON-Datei erstellt in {json_duration:.1f}s: {json_filename}")

    # Cleanup: Schließe alle WebDriver-Instanzen
    driver.quit()

    # Cleanup aller Thread-spezifischen WebDriver
    import atexit
    atexit.register(cleanup_thread_drivers)

    # Endzeit des Skripts
    end_time = time.time()
    duration = end_time - start_time
    duration_minutes = duration / 60  # Umrechnung von Sekunden in Minuten

    # Performance-Statistiken
    total_activities = len(activities["assignments"]) + len(activities["checklists"])
    total_groups = len(data["groups"])
    total_users = sum(len(group["users"]) for group in data["groups"])

    print("\n" + "="*60)
    print("📊 EXPORT ABGESCHLOSSEN")
    print("="*60)
    print(f"⏱️  Gesamtdauer: {duration_minutes:.2f} Minuten ({duration:.1f} Sekunden)")
    print(f"🎯 Aktivitäten: {total_activities} ({len(activities['assignments'])} Assignments, {len(activities['checklists'])} Checklists)")
    print(f"👥 Gruppen: {total_groups} mit insgesamt {total_users} Benutzern")
    if total_activities > 0:
        print(f"⚡ Durchschnitt: {(duration / total_activities):.1f}s pro Aktivität")
    print(f"💾 Ausgabedatei: {json_filename}")
    print(f"🏁 Endzeit: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)

if __name__ == "__main__":
    main()





    