import json
import requests
import urllib.parse
from datetime import datetime

def upload_to_owncloud(data, filename):
    """Upload JSON data to OwnCloud public upload folder"""
    # Original URL provided by user
    original_url = "https://6072.drive.bycs.de/files/spaces/project/aeup12/Segel_Export?fileId=e4a0c375-2fb6-4fc6-af92-ac4b95c18ce1%24596fbe56-16a5-41fd-a1a0-96b7e392435e%21f4797d5b-9177-43b8-be8e-0cba1bb25ead&sort-by=name&sort-dir=asc&items-per-page=100&files-spaces-generic-view-mode=resource-table&tiles-size=2"

    # Extract fileId from URL
    file_id_param = original_url.split('fileId=')[1].split('&')[0]
    file_id = urllib.parse.unquote(file_id_param)

    print(f"Upload zu OwnCloud")
    print(f"Extracted File ID: {file_id}")
    print(f"Target: Segel_Export folder")

    try:
        # Serialize JSON data
        json_content = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

        # Try multiple upload approaches for modern OwnCloud/NextCloud
        approaches = [
            # Approach 1: Modern OwnCloud Spaces API
            {
                "url": f"https://6072.drive.bycs.de/api/v0/spaces/{file_id}/upload",
                "method": "POST",
                "files": {
                    'file': (filename, json_content.encode('utf-8'), 'application/json')
                },
                "data": {
                    'path': f'/{filename}',
                    'overwrite': 'true'
                }
            },
            # Approach 2: GraphQL upload endpoint
            {
                "url": f"https://6072.drive.bycs.de/graph/v1beta1/drives/{file_id}/items/upload",
                "method": "POST",
                "files": {
                    'file': (filename, json_content.encode('utf-8'), 'application/json')
                }
            },
            # Approach 3: WebDAV with decoded token as user
            {
                "url": f"https://6072.drive.bycs.de/remote.php/dav/public-files/{file_id}/{filename}",
                "method": "PUT",
                "headers": {
                    'Content-Type': 'application/json'
                },
                "auth": ('public', file_id)
            },
            # Approach 4: Alternative spaces WebDAV
            {
                "url": f"https://6072.drive.bycs.de/dav/public-files/{file_id}/{filename}",
                "method": "PUT",
                "headers": {
                    'Content-Type': 'application/json'
                }
            },
            # Approach 5: Direct file API
            {
                "url": f"https://6072.drive.bycs.de/api/v0/files/{filename}",
                "method": "PUT",
                "headers": {
                    'Content-Type': 'application/json',
                    'X-Space-ID': file_id
                }
            }
        ]

        for i, approach in enumerate(approaches, 1):
            print(f"\nVersuche Methode {i}: {approach['method']} zu {approach['url']}")

            try:
                if approach["method"] == "PUT":
                    response = requests.put(
                        approach["url"],
                        data=json_content.encode('utf-8'),
                        headers=approach.get("headers", {}),
                        auth=approach.get("auth"),
                        timeout=60,
                        verify=True
                    )
                elif approach["method"] == "POST":
                    response = requests.post(
                        approach["url"],
                        files=approach.get("files"),
                        data=approach.get("data"),
                        timeout=60,
                        verify=True
                    )

                print(f"  Status Code: {response.status_code}")
                print(f"  Response Headers: {dict(list(response.headers.items())[:5])}")

                response_preview = response.text[:300] if len(response.text) > 300 else response.text
                print(f"  Response (first 300 chars): {response_preview}")

                if response.status_code in [200, 201, 204]:
                    print(f"  SUCCESS: Methode {i} erfolgreich!")

                    # Additional success indicators
                    response_lower = response.text.lower()
                    if any(indicator in response_lower for indicator in ['success', 'uploaded', 'created', 'ok']):
                        print(f"  Upload-Erfolg bestaetigt durch Response!")
                        return True
                    elif not response.text or len(response.text.strip()) == 0:
                        print(f"  Leere Response - wahrscheinlich erfolgreich!")
                        return True
                    else:
                        print(f"  Status OK, aber Response unklar")

                elif response.status_code == 401:
                    print(f"  Authentifizierung fehlgeschlagen")
                elif response.status_code == 403:
                    print(f"  Zugriff verweigert - moeglicherweise keine Upload-Berechtigung")
                elif response.status_code == 404:
                    print(f"  Endpunkt nicht gefunden")
                else:
                    print(f"  Unerwarteter Status Code")

            except Exception as method_error:
                print(f"  FEHLER bei Methode {i}: {method_error}")

        print(f"\nFEHLER: Alle {len(approaches)} Upload-Methoden fehlgeschlagen")
        return False

    except Exception as e:
        print(f"Allgemeiner Fehler: {e}")
        return False

def main():
    print("TEST: OwnCloud Upload Test")
    print("=" * 50)

    # Create test data
    test_data = {
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "message": "Dies ist ein Test-Upload zu OwnCloud",
        "sample_data": {
            "numbers": [1, 2, 3, 4, 5],
            "text": "Beispieltext mit Umlauten: äöüß",
            "nested": {
                "level1": {
                    "level2": "Tiefe Verschachtelung"
                }
            }
        },
        "metadata": {
            "script": "test_owncloud_upload.py",
            "purpose": "Upload-Test für OwnCloud-Integration",
            "size_info": "Small test file"
        }
    }

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_filename = f"test_upload_{timestamp}.json"

    print(f"Test-Datei: {test_filename}")
    print(f"Datengroesse: {len(json.dumps(test_data))} Zeichen")
    print()

    # Attempt upload
    success = upload_to_owncloud(test_data, test_filename)

    print("\n" + "=" * 50)
    if success:
        print("SUCCESS: TEST ERFOLGREICH!")
        print(f"Die Datei '{test_filename}' sollte nun im OwnCloud-Ordner sichtbar sein.")
        print("Pruefen Sie den Ordner in Ihrem Browser.")
    else:
        print("FEHLER: TEST FEHLGESCHLAGEN!")
        print("Der Upload-Mechanismus muss angepasst werden.")
        print("Moeglicherweise sind spezielle Headers oder ein anderer Endpunkt erforderlich.")

    print("=" * 50)

if __name__ == "__main__":
    main()