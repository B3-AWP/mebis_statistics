import os
import configparser
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options

def load_config():
    """Load configuration from config.ini"""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    """Create Chrome WebDriver instance"""
    options = Options()
    if headless:
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    # Add some basic optimizations
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-default-apps')

    try:
        driver = webdriver.Chrome(options=options)
        driver.get("about:blank")
        return driver
    except Exception as e:
        print(f"Fehler beim Erstellen des WebDrivers: {e}")
        # Try with minimal options
        options = Options()
        if headless:
            options.add_argument('--headless')
        return webdriver.Chrome(options=options)

def login_to_owncloud(driver, username, password):
    """Login to OwnCloud using credentials"""
    print(f"Anmeldung mit Benutzer: {username}")

    # Navigate to the OwnCloud login page
    driver.get("https://6072.drive.bycs.de/")
    time.sleep(3)

    try:
        # Find username field
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#input-username"))
        )
        username_field.clear()
        username_field.send_keys(username)
        print("Username eingegeben")

        # Find password field
        password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        password_field.clear()
        password_field.send_keys(password)
        print("Password eingegeben")

        # Find and click login button
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        print("Login-Button geklickt")

        # Wait for successful login
        WebDriverWait(driver, 20).until(
            EC.any_of(
                EC.url_contains("/f/"),
                EC.url_contains("/files/"),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".files-view")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid]"))
            )
        )
        print("Erfolgreich angemeldet!")
        return True

    except Exception as e:
        print(f"Fehler beim Login: {e}")
        return False

def navigate_to_upload_folder(driver):
    """Navigate to the Segel_Export folder"""
    print("Navigiere zum Segel_Export Ordner...")

    target_url = "https://6072.drive.bycs.de/files/spaces/project/aeup12/Segel_Export?fileId=e4a0c375-2fb6-4fc6-af92-ac4b95c18ce1%24596fbe56-16a5-41fd-a1a0-96b7e392435e%21f4797d5b-9177-43b8-be8e-0cba1bb25ead&sort-by=name&sort-dir=asc&items-per-page=100&files-spaces-generic-view-mode=resource-table&tiles-size=2"
    driver.get(target_url)
    time.sleep(5)

    try:
        # Wait for folder content to load
        WebDriverWait(driver, 10).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".files-list")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='files-list']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".file-row")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody"))
            )
        )
        print("Ordner erfolgreich geladen!")
        return True
    except TimeoutException:
        print("Ordner-Ladezeit überschritten, versuche fortzufahren...")
        return True

def create_file_in_cloud(driver, filename, content):
    """Create a new file in the cloud using the web interface"""
    print(f"Erstelle Datei: {filename}")

    try:
        # Click on new file menu button
        new_file_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#new-file-menu-btn svg"))
        )
        new_file_button.click()
        print("New-File-Menu geklickt")
        time.sleep(1)

        # Click on "Text-Datei" option
        text_file_option = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".new-file-btn-txt > .create-list-file-item-text"))
        )
        text_file_option.click()
        print("Text-Datei Option geklickt")
        time.sleep(1)

        # Wait for filename input and clear it
        filename_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#oc-textinput-8"))
        )

        # Clear existing text and enter filename
        filename_input.clear()
        filename_input.send_keys(filename)
        print(f"Dateiname eingegeben: {filename}")

        # Press Enter to create the file
        filename_input.send_keys("\n")
        print("Enter gedrückt, warte auf Navigation...")

        # Wait for the file editor to load
        time.sleep(3)

        # Click in the content area
        content_area = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".cm-content"))
        )
        content_area.click()
        print("Content-Bereich geklickt")

        # Clear any existing content and enter new content
        content_area.clear()
        if content:
            content_area.send_keys(content)
            print("Inhalt eingegeben")

        # Save the file
        save_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#app-save-action svg"))
        )
        save_button.click()
        print("Save-Button geklickt")
        time.sleep(2)

        # Close the file editor
        close_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#app-top-bar-close svg"))
        )
        close_button.click()
        print("Close-Button geklickt")
        time.sleep(3)

        print(f"Datei '{filename}' erfolgreich erstellt!")
        return True

    except Exception as e:
        print(f"Fehler beim Erstellen der Datei: {e}")
        return False

def upload_json_to_cloud(data, filename):
    """Upload JSON data by creating a file in the cloud interface"""
    print("=" * 60)
    print("CLOUD FILE CREATOR - JSON Upload")
    print("=" * 60)

    # Load configuration
    try:
        config = load_config()
        username = config['login']['username']
        password = config['login']['password']
        print(f"Konfiguration geladen für Benutzer: {username}")
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        return False

    # Convert data to JSON string
    json_content = json.dumps(data, ensure_ascii=False, indent=2)

    # Create WebDriver
    driver = create_webdriver(headless=False)

    try:
        # Step 1: Login
        if not login_to_owncloud(driver, username, password):
            print("Anmeldung fehlgeschlagen!")
            return False

        time.sleep(2)

        # Step 2: Navigate to folder
        if not navigate_to_upload_folder(driver):
            print("Navigation fehlgeschlagen!")
            return False

        time.sleep(2)

        # Step 3: Create file
        if create_file_in_cloud(driver, filename, json_content):
            print(f"SUCCESS: Datei '{filename}' wurde erfolgreich in der Cloud erstellt!")
            return True
        else:
            print("Datei-Erstellung fehlgeschlagen!")
            return False

    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
        return False
    finally:
        try:
            # Keep browser open for a moment to see the result
            print("Browser bleibt 5 Sekunden offen zur Überprüfung...")
            time.sleep(5)
            driver.quit()
        except:
            pass

def test_cloud_file_creation():
    """Test function to create a sample JSON file in the cloud"""
    test_data = {
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "message": "Cloud-Datei-Erstellung Test",
        "sample_data": {
            "numbers": [1, 2, 3, 4, 5],
            "text": "Beispieltext mit Umlauten: äöüß",
            "method": "Cloud File Creator"
        },
        "metadata": {
            "script": "cloud_file_creator.py",
            "purpose": "Automatische Datei-Erstellung in der Cloud",
            "creation_method": "Web Interface Automation"
        }
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cloud_created_{timestamp}.json"

    success = upload_json_to_cloud(test_data, filename)

    if success:
        print(f"\nTEST ERFOLGREICH: '{filename}' wurde in der Cloud erstellt!")
    else:
        print(f"\nTEST FEHLGESCHLAGEN: Datei konnte nicht erstellt werden!")

    return success

if __name__ == "__main__":
    test_cloud_file_creation()