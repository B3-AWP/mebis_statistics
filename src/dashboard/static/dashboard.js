// Dashboard JavaScript
let serverData = null;      // Vollständige Antwort von /api/data (alle Kurse + Plan)
let dashboardData = null;   // Sicht auf den aktiven Kurs — was die Tabellen lesen
let plan = null;            // Stammdaten aus plan.json
let currentGroup = 'all';   // Klasse (seit 2026/27 keine Team-Ebene mehr)
let currentWeek = 9; // Aktuelle ausgewählte Woche (wird durch Slider aktualisiert)
let maxSchoolweeks = 9; // Maximale Schulwochen (aus dem Wochenkalender des Plans)
let checklistViewType = 'pflicht'; // New: track checklist column view setting
let sortState = {}; // Track sorting state for different tables
let gradeMapping = {}; // GradeMapping from config.ini
let mitarbeitsnoteConfig = null; // Mitarbeitsnoten-Konfiguration aus Backend
let courseId = ''; // Moodle-Kurs-ID des aktiven Halbjahres
let currentHalbjahr = null; // Aktiver Kurs: kurs_id aus plan.json oder 'gesamt'

// Make variables available globally for csv_export.js
window.dashboardData = dashboardData;
window.currentGroup = currentGroup;
window.currentWeek = currentWeek;
window.maxSchoolweeks = maxSchoolweeks;
window.gradeMapping = gradeMapping;
window.mitarbeitsnoteConfig = mitarbeitsnoteConfig;

// ============================================================================
// Namen: einheitliche Sortierung nach Vorname
// ============================================================================

/**
 * Vergleicht zwei Personennamen. Moodle liefert "Vorname Nachname";
 * verglichen wird von links, der Vorname entscheidet also zuerst, bei
 * gleichem Vornamen der Nachname.
 * @param {string} a - Erster Name
 * @param {string} b - Zweiter Name
 * @returns {number} Vergleichswert fuer Array.prototype.sort
 */
function compareByVorname(a, b) {
    return (a || '').localeCompare(b || '', 'de', { sensitivity: 'base' });
}

/**
 * Liest den Anzeigenamen aus einem Benutzerobjekt — je nach Quelle heisst
 * das Feld im Export anders.
 * @param {Object} user - Benutzerobjekt aus dem Export
 * @returns {string} Name oder 'Unbekannt'
 */
function getUserName(user) {
    if (!user) return 'Unbekannt';
    return user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
}

/**
 * Sortiert Benutzerobjekte nach Vorname. Liefert eine Kopie, damit die
 * Reihenfolge im geladenen Export unangetastet bleibt.
 * @param {Array} users - Benutzerobjekte aus dem Export
 * @returns {Array} Nach Vorname sortierte Kopie
 */
function sortUsersByVorname(users) {
    return [...(users || [])].sort((a, b) => compareByVorname(getUserName(a), getUserName(b)));
}

// Tab-Management
function showTab(tabName) {
    // Alle Tabs verstecken
    document.querySelectorAll('[id$="Tab"]').forEach(tab => {
        tab.style.display = 'none';
    });

    // Alle Tab-Buttons inaktiv setzen
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.id.startsWith('tab')) {
            btn.classList.remove('active');
            btn.classList.add('inactive');
        }
    });

    // Letzte-Abgaben-Sektion nur bei Übersicht-Tab anzeigen
    const recentSection = document.getElementById('recentSubmissionsSection');
    if (recentSection) {
        recentSection.style.display = tabName === 'home' ? '' : 'none';
    }

    // Gewählten Tab anzeigen
    const tabElement = document.getElementById(tabName + 'Tab');
    if (tabElement) {
        tabElement.style.display = 'block';
    }

    // Tab-Button aktiv setzen
    const tabButton = document.getElementById('tab' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    if (tabButton) {
        tabButton.classList.add('active');
        tabButton.classList.remove('inactive');
    }

    // Gruppenauswahl synchronisieren beim Tab-Wechsel
    syncGroupSelectors();

    // Spezielle Logik für verschiedene Tabs
    if (tabName === 'checklists') {
        loadChecklistsTab();
    } else if (tabName === 'pflicht') {
        loadPflichtTab();
    } else if (tabName === 'exam') {
        loadExamTab();
    }
}

// Datei-Info anzeigen
function displayFileInfo(filename) {
    const container = document.getElementById('fileInfoContainer');
    const textElement = document.getElementById('fileInfoText');
    const ageWarning = document.getElementById('fileAgeWarning');
    const ageDaysElement = document.getElementById('fileAgeDays');

    if (!filename || !container || !textElement) {
        return;
    }

    // Extrahiere Datum und Zeit aus dem Dateinamen
    // Format: export/output_YYYYMMDD_HHMMSS.json
    const match = filename.match(/output_(\d{8})_(\d{6})\.json/);
    if (match) {
        const dateStr = match[1]; // YYYYMMDD
        const timeStr = match[2]; // HHMMSS

        // Parse Datum
        const year = dateStr.substring(0, 4);
        const month = dateStr.substring(4, 6);
        const day = dateStr.substring(6, 8);

        // Parse Zeit
        const hour = timeStr.substring(0, 2);
        const minute = timeStr.substring(2, 4);
        const second = timeStr.substring(4, 6);

        // Erstelle Date-Objekt für Alter-Berechnung
        const fileDate = new Date(year, month - 1, day, hour, minute, second);
        const now = new Date();
        const ageInMs = now - fileDate;
        const ageInDays = Math.floor(ageInMs / (1000 * 60 * 60 * 24));

        // Formatiere für Anzeige
        const formattedDateTime = `${day}.${month}.${year} ${hour}:${minute}:${second}`;
        textElement.textContent = formattedDateTime;

        // Container anzeigen
        container.style.display = 'flex';

        // Zeige Warnung nur wenn älter als 1 Tag
        if (ageInDays > 1 && ageWarning && ageDaysElement) {
            ageDaysElement.textContent = ageInDays;
            ageWarning.style.display = 'block';
        } else if (ageWarning) {
            ageWarning.style.display = 'none';
        }
    } else {
        // Fallback: zeige rohen Dateinamen
        textElement.textContent = filename.replace(/.*[\\\/]/, ''); // Nur Dateiname ohne Pfad
        container.style.display = 'flex';
        if (ageWarning) {
            ageWarning.style.display = 'none';
        }
    }
}

// Hilfsfunktion: Formatiere Sekunden in lesbare Zeit
function formatTime(seconds) {
    if (seconds < 60) {
        return `${Math.round(seconds)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}min ${secs}s`;
}

// Schließe Export-Panel
function closeExportPanel() {
    document.getElementById('exportProgressPanel').style.display = 'none';
}

// Export starten und Dashboard neu laden
async function startExportAndReload() {
    const refreshBtn = document.getElementById('refreshBtn');
    const panel = document.getElementById('exportProgressPanel');
    const progressBar = document.getElementById('exportProgressBar');
    const progressMessage = document.getElementById('exportProgressMessage');
    const estimatedTime = document.getElementById('exportEstimatedTime');
    const assignmentsProgress = document.getElementById('exportAssignmentsProgress');
    const checklistsProgress = document.getElementById('exportChecklistsProgress');
    const quizzesProgress = document.getElementById('exportQuizzesProgress');

    try {
        // Deaktiviere Button
        refreshBtn.disabled = true;
        refreshBtn.classList.add('loading');

        // Zeige Progress Panel
        panel.style.display = 'block';
        panel.style.border = '2px solid #007bff';
        progressMessage.textContent = 'Export wird gestartet...';
        estimatedTime.textContent = 'Schätze Zeit...';

        // Starte Export
        const response = await fetch('/api/export/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`Server-Fehler: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.message || result.error || 'Export konnte nicht gestartet werden');
        }

        // Polling: Überwache Export-Status
        const checkStatus = async () => {
            const statusResponse = await fetch('/api/export/status');
            const status = await statusResponse.json();

            // Update Fortschrittsbalken
            progressBar.style.width = status.progress + '%';
            progressBar.textContent = status.progress + '%';

            // Update Message
            progressMessage.textContent = status.message || 'Export läuft...';

            // Update geschätzte Zeit
            if (status.estimated_time_remaining !== null && status.estimated_time_remaining > 0) {
                estimatedTime.textContent = `Noch ca. ${formatTime(status.estimated_time_remaining)}`;
            } else if (status.progress < 100) {
                estimatedTime.textContent = 'Schätze Zeit...';
            }

            // Update Details
            if (status.details) {
                const a = status.details.assignments;
                const c = status.details.checklists;
                const q = status.details.quizzes;

                assignmentsProgress.textContent = `${a.current}/${a.total}`;
                checklistsProgress.textContent = `${c.current}/${c.total}`;
                quizzesProgress.textContent = `${q.current}/${q.total}`;
            }

            // Fehlerbehandlung
            if (status.error) {
                panel.style.border = '2px solid #dc3545';
                progressBar.style.background = '#dc3545';
                progressMessage.textContent = 'Fehler: ' + status.error;
                estimatedTime.textContent = 'Export fehlgeschlagen';
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('loading');
                return;
            }

            // Weiter prüfen oder abschließen
            if (status.running) {
                setTimeout(checkStatus, 2000);
            } else if (status.progress === 100) {
                // Export abgeschlossen
                panel.style.border = '2px solid #28a745';
                progressBar.style.background = 'linear-gradient(90deg, #28a745, #1e7e34)';
                progressMessage.textContent = 'Export abgeschlossen! Lade Dashboard neu...';
                estimatedTime.textContent = 'Abgeschlossen';

                // Lade Dashboard-Daten neu
                await loadData();

                progressMessage.textContent = 'Dashboard aktualisiert!';
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('loading');

                // Auto-Close nach 5 Sekunden
                setTimeout(() => {
                    panel.style.display = 'none';
                    // Reset für nächsten Export
                    progressBar.style.width = '0%';
                    progressBar.style.background = 'linear-gradient(90deg, #007bff, #0056b3)';
                    panel.style.border = '2px solid #007bff';
                }, 5000);
            }
        };

        // Starte Status-Überwachung
        setTimeout(checkStatus, 1000);

    } catch (error) {
        console.error('Export-Fehler:', error);
        panel.style.border = '2px solid #dc3545';
        progressBar.style.background = '#dc3545';

        // Bessere Fehlermeldungen
        let errorMessage = 'Fehler: ' + error.message;
        if (error.message.includes('NetworkError') || error.message.includes('fetch')) {
            errorMessage = 'Netzwerkfehler: Ist der Server erreichbar?';
            estimatedTime.textContent = 'Verbindung fehlgeschlagen';
        } else if (error.message.includes('Server-Fehler')) {
            estimatedTime.textContent = 'Server-Fehler';
        } else {
            estimatedTime.textContent = 'Fehler beim Starten';
        }

        progressMessage.textContent = errorMessage;
        refreshBtn.disabled = false;
        refreshBtn.classList.remove('loading');

        // Zeige detaillierte Fehlerinfo in Console
        console.error('Detaillierter Fehler:', {
            message: error.message,
            stack: error.stack,
            name: error.name
        });
    }
}
// ============================================================
// KURS-SCOPE (Halbjahre)
//
// Der Server liefert alle Kurse. currentHalbjahr waehlt einen davon
// (oder 'gesamt'); selectCourseScope() legt dessen Daten als
// dashboardData ab, damit die Tabellen unveraendert weiterlesen koennen.
// ============================================================

// Liefert die Kurse in Planreihenfolge, angereichert um die Exportdaten.
function getCourses() {
    if (!serverData || !plan) return [];
    return plan.kurse.map(k => {
        const daten = (serverData.kurse || {})[k.moodle_course_id] || {};
        return {
            kursId: k.id,
            moodleCourseId: k.moodle_course_id,
            titel: k.titel,
            gesperrt: k.gesperrt,
            freischaltung: k.freischaltung,
            stundenGeplant: k.stunden_geplant,
            verfuegbar: daten.verfuegbar === true,
            daten: daten
        };
    });
}

function getCourse(kursId) {
    return getCourses().find(c => c.kursId === kursId) || null;
}

// Fasst mehrere Kurse zu einer Sicht zusammen ('gesamt').
// Die Gewichtung ergibt sich von selbst aus der Stundensumme.
function mergeCourses(courses) {
    const verfuegbar = courses.filter(c => c.verfuegbar);
    if (verfuegbar.length === 0) return null;
    if (verfuegbar.length === 1) return verfuegbar[0].daten;

    const merged = {
        verfuegbar: true,
        groups: {},
        activities_by_category: [],
        categories: [],
        structured_tables: {},
        assignment_details: {},
        recent_submissions: [],
        grade_mapping: verfuegbar[0].daten.grade_mapping,
        mitarbeitsnote_config: verfuegbar[0].daten.mitarbeitsnote_config,
        stunden_geplant: verfuegbar.reduce((s, c) => s + (c.daten.stunden_geplant || 0), 0)
    };

    verfuegbar.forEach(c => {
        const d = c.daten;
        merged.activities_by_category.push(...(d.activities_by_category || []));
        merged.categories.push(...(d.categories || []));
        merged.recent_submissions.push(...(d.recent_submissions || []));
        Object.assign(merged.assignment_details, d.assignment_details || {});
        Object.assign(merged.structured_tables, d.structured_tables || {});

        // Gruppen und Personen ueber Kurse hinweg zusammenfuehren:
        // Stunden addieren sich, Prozentwerte werden daraus neu gebildet.
        Object.entries(d.groups || {}).forEach(([gName, gData]) => {
            if (!merged.groups[gName]) {
                merged.groups[gName] = { name: gName, value: gData.value, users: [] };
            }
            const ziel = merged.groups[gName].users;
            (gData.users || []).forEach(user => {
                const vorhanden = ziel.find(u => u.name === user.name);
                if (!vorhanden) {
                    ziel.push(JSON.parse(JSON.stringify(user)));
                    return;
                }
                const a = vorhanden.assignments, b = user.assignments;
                if (!a || !b) return;
                a.stunden_erledigt = (a.stunden_erledigt || 0) + (b.stunden_erledigt || 0);
                a.stunden_gesamt = (a.stunden_gesamt || 0) + (b.stunden_gesamt || 0);
                a.aufgaben_erledigt = (a.aufgaben_erledigt || 0) + (b.aufgaben_erledigt || 0);
                a.aufgaben_gesamt = (a.aufgaben_gesamt || 0) + (b.aufgaben_gesamt || 0);
                a.submitted_count = (a.submitted_count || 0) + (b.submitted_count || 0);
                a.reviewed_count = (a.reviewed_count || 0) + (b.reviewed_count || 0);
                a.percent_stunden = a.stunden_gesamt > 0
                    ? Math.round((a.stunden_erledigt / a.stunden_gesamt) * 10000) / 100 : 0;
                a.percent_submitted = a.aufgaben_gesamt > 0
                    ? Math.round((a.aufgaben_erledigt / a.aufgaben_gesamt) * 10000) / 100 : 0;
            });
        });
    });

    return merged;
}

// Setzt dashboardData auf den gewaehlten Kurs-Scope.
function selectCourseScope(scope) {
    const courses = getCourses();
    if (courses.length === 0) return;

    // Vorgabe: der erste verfuegbare Kurs. Zu Schuljahresbeginn ist das
    // das 1. Halbjahr — das 2. ist bis zur Freischaltung leer.
    if (!scope) {
        const ersterVerfuegbar = courses.find(c => c.verfuegbar);
        scope = ersterVerfuegbar ? ersterVerfuegbar.kursId : courses[0].kursId;
    }

    currentHalbjahr = scope;
    let daten = null;

    if (scope === 'gesamt') {
        daten = mergeCourses(courses);
        courseId = '';
    } else {
        const kurs = getCourse(scope);
        daten = kurs ? kurs.daten : null;
        courseId = kurs ? kurs.moodleCourseId : '';
    }

    // Ein gesperrter oder noch nicht exportierter Kurs hat keine Daten.
    // Leere Huelle statt Absturz — die Hinweiszeile erklaert den Grund.
    dashboardData = daten || {
        verfuegbar: false, groups: {}, activities_by_category: [], categories: [],
        structured_tables: {}, assignment_details: {}, recent_submissions: []
    };
    window.dashboardData = dashboardData;

    gradeMapping = dashboardData.grade_mapping || {};
    window.gradeMapping = gradeMapping;
    mitarbeitsnoteConfig = dashboardData.mitarbeitsnote_config || null;
    window.mitarbeitsnoteConfig = mitarbeitsnoteConfig;

    updateWeekSlider();
    updateCourseScopeUI();
}

// Der Wochen-Slider zeigt die Blockwochen des aktiven Halbjahres.
// Bei "Gesamt" laeuft er ueber das ganze Schuljahr.
function updateWeekSlider() {
    const slider = document.getElementById('referenceWeekSlider');
    if (!slider) return;

    const track = getTrackForGroup(currentGroup) || (plan && Object.keys(plan.schienen)[0]);
    const wochen = getSchulwochenForScope(track);
    if (wochen.length === 0) return;

    const min = wochen[0].woche;
    const max = wochen[wochen.length - 1].woche;

    slider.min = min;
    slider.max = max;

    // Auf die laufende Woche stellen, falls sie im Zeitraum liegt,
    // sonst auf das Ende des Zeitraums.
    const jetzt = getCurrentReferenceWeekForTrack(track);
    const wert = (jetzt >= min && jetzt <= max) ? jetzt : max;
    slider.value = wert;

    const minLabel = document.querySelector('.slider-value.min');
    const maxLabel = document.querySelector('.slider-value.max');
    if (minLabel) minLabel.textContent = min;
    if (maxLabel) maxLabel.textContent = max;
    const display = document.getElementById('currentWeekDisplay');
    if (display) display.textContent = wert;

    currentWeek = wert;
    window.currentWeek = currentWeek;
}

// Zeichnet die Halbjahr-Schaltflaechen und den Hinweis bei leerem Kurs.
function updateCourseScopeUI() {
    const nav = document.getElementById('halbjahrNav');
    if (!nav) return;

    const courses = getCourses();
    const anzahlVerfuegbar = courses.filter(c => c.verfuegbar).length;

    const knoepfe = courses.map(c => {
        const aktiv = currentHalbjahr === c.kursId ? ' active' : '';
        const gesperrt = c.verfuegbar ? '' : ' disabled';
        const titel = c.verfuegbar
            ? `${c.titel} (${c.stundenGeplant} Std.)`
            : (c.freischaltung
                ? `${c.titel} — ab ${formatDateDe(c.freischaltung)}`
                : `${c.titel} — noch keine Daten`);
        return `<button class="halbjahr-nav-btn${aktiv}${gesperrt}" `
             + `${c.verfuegbar ? `onclick="selectHalbjahr('${c.kursId}')"` : 'disabled'} `
             + `title="${titel}">${c.titel}</button>`;
    });

    // "Gesamt" steht dauerhaft an erster Stelle und fasst alle Kurse
    // zusammen. Hat erst ein Kurs Daten, zeigt es eben nur dessen Zahlen.
    const gesamtAktiv = currentHalbjahr === 'gesamt' ? ' active' : '';
    const gesamtTitel = anzahlVerfuegbar > 1
        ? 'Alle Kurse zusammen'
        : 'Alle Kurse zusammen (derzeit nur der laufende)';
    knoepfe.unshift(
        `<button class="halbjahr-nav-btn${gesamtAktiv}" onclick="selectHalbjahr('gesamt')" `
        + `title="${gesamtTitel}">Gesamt</button>`);

    nav.innerHTML = knoepfe.join('');

    const hinweis = document.getElementById('halbjahrHinweis');
    if (hinweis) {
        const kurs = currentHalbjahr !== 'gesamt' ? getCourse(currentHalbjahr) : null;
        if (kurs && !kurs.verfuegbar) {
            hinweis.textContent = kurs.freischaltung
                ? `${kurs.titel} ist noch gesperrt und wird am ${formatDateDe(kurs.freischaltung)} freigeschaltet.`
                : `Für ${kurs.titel} liegen noch keine Exportdaten vor.`;
            hinweis.style.display = '';
        } else {
            hinweis.style.display = 'none';
        }
    }
}

function formatDateDe(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString('de-DE');
}

function applyDashboardData(data) {
    serverData = data;
    plan = data.plan || null;

    if (!plan) {
        dashboardLogger.error('DATA', 'Keine Plandaten in der Server-Antwort');
    }

    // Schulwochen aus dem Plan; die Schienen haben denselben Wochenumfang.
    if (plan && plan.schienen) {
        const ersteSchiene = Object.values(plan.schienen)[0];
        if (ersteSchiene && ersteSchiene.schulwochen.length > 0) {
            maxSchoolweeks = ersteSchiene.schulwochen.length;
            window.maxSchoolweeks = maxSchoolweeks;
        }
    }

    selectCourseScope(currentHalbjahr);

    dashboardLogger.info('DATA', 'Kurse geladen', {
        schuljahr: data.schuljahr,
        kurse: getCourses().map(c => `${c.titel}${c.verfuegbar ? '' : ' (gesperrt)'}`),
        aktiv: currentHalbjahr,
        maxSchoolweeks: maxSchoolweeks
    });

    dashboardLogger.info('DATA', 'Dashboard data loaded', {
        hasActivitiesByCategory: !!dashboardData.activities_by_category,
        categoriesCount: dashboardData.activities_by_category ? dashboardData.activities_by_category.length : 'undefined',
        sampleCategory: dashboardData.activities_by_category ? dashboardData.activities_by_category[0] : 'none'
    });

    if (dashboardData.activities_by_category && dashboardData.activities_by_category.length > 0) {
        const firstCategory = dashboardData.activities_by_category[0];
        dashboardLogger.debug('DATA', 'First category assignments', {
            assignmentCount: firstCategory.assignments ? firstCategory.assignments.length : 'undefined',
            sampleAssignment: firstCategory.assignments && firstCategory.assignments.length > 0 ? firstCategory.assignments[0] : 'none'
        });
    }

    if (dashboardData.environment) {
        dashboardLogger.setBackendEnvironment(dashboardData.environment);
    }

    displayFileInfo(dashboardData.last_updated);
    populateGroupSelectors();
    populateCategoryFilter();
    updateDashboard();
}

async function loadData() {
    showLoading(true);

    try {
        const response = await fetch('/api/data');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        applyDashboardData(data);
        showLoading(false);

    } catch (error) {
        dashboardLogger.error('API', 'Fehler beim Laden der Daten', error);
        showError('Fehler beim Laden der Daten: ' + error.message);
        showLoading(false);
    }
}

async function loadFromFile(input) {
    if (!input.files || !input.files[0]) return;

    const file = input.files[0];
    input.value = ''; // Reset so same file can be selected again

    showLoading(true);

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/load-file', { method: 'POST', body: formData });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ error: response.statusText }));
            throw new Error(err.error || response.statusText);
        }

        const data = await response.json();
        applyDashboardData(data);
        showLoading(false);

    } catch (error) {
        dashboardLogger.error('API', 'Fehler beim Laden der Datei', error);
        showError('Fehler beim Laden der Datei: ' + error.message);
        showLoading(false);
    }
}

// Loading-Anzeige steuern
function showLoading(show) {
    const overlay = document.getElementById('dashboardLoadingOverlay');
    if (overlay) {
        overlay.style.display = show ? 'block' : 'none';
    }
}

// Fehler anzeigen
function showError(message) {
    dashboardLogger.error('UI', message);
    // Hier könnte eine Benutzer-freundliche Fehleranzeige implementiert werden
}

// Gruppen-Tabs und Dropdowns füllen
function populateGroupSelectors() {
    // Klassen-Tabs (seit 2026/27 keine Team-Ebene mehr)
    populateGroupTabs();

    // Populate remaining dropdown selectors
    const selectors = [
        'pflichtGroupFilter'
    ];

    selectors.forEach(selectorId => {
        const selector = document.getElementById(selectorId);
        if (selector && dashboardData && dashboardData.groups) {
            // Alle Optionen außer der ersten ("Alle Gruppen") entfernen
            while (selector.children.length > 1) {
                selector.removeChild(selector.lastChild);
            }

            // Neue Optionen hinzufügen
            Object.keys(dashboardData.groups).forEach(groupName => {
                const option = document.createElement('option');
                option.value = groupName;
                option.textContent = groupName;
                selector.appendChild(option);
            });
        }
    });
}

// Kategorie-Filter mit verfügbaren Kategorien füllen
function populateCategoryFilter() {
    const categoryFilter = document.getElementById('pflichtCategoryFilter');
    if (!categoryFilter || !dashboardData || !dashboardData.activities_by_category) return;

    // Sammle alle verfügbaren Kategorien (sowohl assignments als auch quizzes)
    const categories = [];
    dashboardData.activities_by_category.forEach(category => {
        if (category.category_name) {
            const assignmentCount = category.assignments ? category.assignments.length : 0;
            const quizCount = category.quizzes ? category.quizzes.length : 0;
            const totalCount = assignmentCount + quizCount;

            if (totalCount > 0) {
                categories.push({
                    name: category.category_name,
                    count: totalCount,
                    assignmentCount: assignmentCount,
                    quizCount: quizCount
                });
            }
        }
    });

    // Finde Pflichtaufgaben-Kategorie
    const pflichtaufgabenCategory = categories.find(cat =>
        cat.name.includes('Pflichtaufgaben') || cat.name.includes('🎯')
    );

    // Leere aktuelle Optionen (außer den Standard-Optionen)
    categoryFilter.innerHTML = '';

    // Standard-Optionen hinzufügen
    if (pflichtaufgabenCategory) {
        const pflichtOption = document.createElement('option');
        pflichtOption.value = 'pflichtaufgaben';
        // Zeige Gesamtzahl mit Aufschlüsselung
        
        pflichtOption.textContent = `Nur Pflichtaufgaben-Kategorie`;
        pflichtOption.selected = true; // Standardmäßig ausgewählt
        categoryFilter.appendChild(pflichtOption);
    }

    const allOption = document.createElement('option');
    allOption.value = 'all';
    const totalAssignments = categories.reduce((sum, cat) => sum + cat.count, 0);
    allOption.textContent = `Alle Kategorien (${totalAssignments})`;
    categoryFilter.appendChild(allOption);

    // Einzelne Kategorien als Optionen hinzufügen
    categories.forEach(category => {
        if (!category.name.includes('Pflichtaufgaben') && !category.name.includes('🎯')) {
            const option = document.createElement('option');
            option.value = category.name.toLowerCase().replace(/[^a-z0-9]/g, '');
            option.textContent = `${category.name} (${category.count})`;
            categoryFilter.appendChild(option);
        }
    });
}

// Klassen-Tabs dynamisch erstellen
function populateGroupTabs() {
    const groupTabsContainer = document.getElementById('groupTabs');
    if (!groupTabsContainer || !dashboardData || !dashboardData.groups) return;

    // Container leeren
    groupTabsContainer.innerHTML = '';

    const groupsToShow = Object.keys(dashboardData.groups);

    // Für jede zu zeigende Gruppe einen Tab erstellen
    groupsToShow.forEach(groupName => {
        const groupButton = document.createElement('button');
        groupButton.className = 'group-nav-btn';
        groupButton.id = `group${groupName.replace(/\s+/g, '')}`;
        groupButton.onclick = () => selectGroup(groupName);

        const spanText = document.createElement('span');
        spanText.className = 'group-tab-text';
        spanText.textContent = groupName;
        groupButton.appendChild(spanText);

        groupTabsContainer.appendChild(groupButton);
    });
}

// Dashboard aktualisieren
function updateDashboard() {
    if (!dashboardData) return;

    const selectedUsers = getSelectedUsers();
    const groupStats = calculateGroupStats(selectedUsers);

    updateOverviewStats(groupStats, selectedUsers);
    generateRecentSubmissionsTable();
}

// Ausgewählte Benutzer basierend auf aktueller Gruppierung und Gruppe
function getSelectedUsers() {
    if (!dashboardData || !dashboardData.groups) return [];

    // Tabellen zeigen Personen standardmaessig nach Vorname sortiert.
    if (currentGroup === 'all') {
        // Alle Personen aus allen Klassen
        let allUsers = [];
        Object.values(dashboardData.groups).forEach(group => {
            allUsers = allUsers.concat(group.users);
        });
        return sortUsersByVorname(allUsers);
    } else {
        // Benutzer aus spezifischer Gruppe
        return sortUsersByVorname(dashboardData.groups[currentGroup]?.users);
    }
}

// Gruppenstatistiken berechnen
function calculateGroupStats(users) {
    if (!users || users.length === 0) {
        return {
            assignments: {
                total_submitted: 0,
                total_reviewed: 0,
                avg_percent_submitted: 0,
                avg_percent_submitted_timed: 0,
                avg_grade: null
            },
            checklists: {
                total_required_100: 0,
                avg_required_progress: 0,
                avg_all_progress: 0,
                avg_required_progress_timed: 0,
                avg_all_progress_timed: 0
            }
        };
    }

    const totalUsers = users.length;

    // Assignment-Statistiken
    const totalSubmitted = users.reduce((sum, user) => sum + user.assignments.submitted_count, 0);
    const totalReviewed = users.reduce((sum, user) => sum + user.assignments.reviewed_count, 0);
    const avgPercentSubmitted = users.reduce((sum, user) => sum + user.assignments.percent_submitted, 0) / totalUsers;
    const avgPercentSubmittedTimed = users.reduce((sum, user) => sum + user.assignments.percent_submitted_timed, 0) / totalUsers;

    // Durchschnittsnote berechnen
    const gradesArray = users
        .map(user => user.assignments.average_grade)
        .filter(grade => grade !== null && grade !== undefined);
    const avgGrade = gradesArray.length > 0 ? gradesArray.reduce((sum, grade) => sum + grade, 0) / gradesArray.length : null;

    // Checklisten-Statistiken
    const totalRequired100 = users.reduce((sum, user) => sum + user.checklists.required_100_count, 0);
    const sumRequiredProgress = users.reduce((sum, user) => sum + user.checklists.avg_required_progress, 0);
    const sumAllProgress = users.reduce((sum, user) => sum + user.checklists.avg_all_progress, 0);
    const avgRequiredProgress = sumRequiredProgress / totalUsers;
    const avgAllProgress = sumAllProgress / totalUsers;

    // Calculate timed values correctly at group level, not by averaging individual user timed values
    // The timed calculation should be: (group_average / current_week) * max_schoolweeks
    const currentWeek = parseInt(document.getElementById('weekSlider')?.value || maxSchoolweeks);

    const avgRequiredProgressTimed = currentWeek > 0 ?
        Math.round(((avgRequiredProgress / currentWeek) * maxSchoolweeks) * 100) / 100 : 0;
    const avgAllProgressTimed = currentWeek > 0 ?
        Math.round(((avgAllProgress / currentWeek) * maxSchoolweeks) * 100) / 100 : 0;


    return {
        assignments: {
            total_submitted: totalSubmitted,
            total_reviewed: totalReviewed,
            avg_percent_submitted: Math.round(avgPercentSubmitted * 100) / 100,
            avg_percent_submitted_timed: Math.round(avgPercentSubmittedTimed * 100) / 100,
            avg_grade: avgGrade ? Math.round(avgGrade * 100) / 100 : null
        },
        checklists: {
            total_required_100: totalRequired100,
            avg_required_progress: Math.round(avgRequiredProgress * 100) / 100,
            avg_all_progress: Math.round(avgAllProgress * 100) / 100,
            avg_required_progress_timed: Math.round(avgRequiredProgressTimed * 100) / 100,
            avg_all_progress_timed: Math.round(avgAllProgressTimed * 100) / 100
        }
    };
}

// Gesamtanzahl Checklisten und Pflichtaufgaben aus den Daten ermitteln
function getTotalCounts() {
    // Verwende activities_by_category für die Gesamtzahl (globale Anzahl, nicht gruppenspezifisch)
    if (dashboardData && dashboardData.activities_by_category) {
        let totalMandatoryChecklists = 0;
        let totalPflichtaufgaben = 0;

        dashboardData.activities_by_category.forEach(category => {
            // Zähle nur Pflicht-Checklisten
            if (category.checklists) {
                const mandatoryChecklists = category.checklists.filter(cl =>
                    cl.is_mandatory !== undefined ? cl.is_mandatory : true
                );
                totalMandatoryChecklists += mandatoryChecklists.length;
            }

            // Zähle Pflichtaufgaben (nur aus Pflichtaufgaben-Kategorie)
            if (category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))) {
                if (category.assignments) {
                    totalPflichtaufgaben += category.assignments.length;
                }
                if (category.quizzes) {
                    totalPflichtaufgaben += category.quizzes.length;
                }
            }
        });

        return {
            totalChecklists: totalMandatoryChecklists || 23,
            totalPflichtaufgaben: totalPflichtaufgaben || 22
        };
    }

    // Fallback: Verwende structured_tables
    if (dashboardData && dashboardData.structured_tables) {
        let maxChecklists = 0;
        let maxPflichtaufgaben = 0;

        Object.keys(dashboardData.structured_tables).forEach(groupName => {
            const groupData = dashboardData.structured_tables[groupName];

            if (groupData.checklists && groupData.checklists.rows) {
                const mandatoryChecklists = groupData.checklists.rows.filter(row =>
                    row.is_mandatory !== undefined ? row.is_mandatory : true
                );
                maxChecklists = Math.max(maxChecklists, mandatoryChecklists.length);
            }

            if (groupData.pflichtaufgaben && groupData.pflichtaufgaben.rows) {
                maxPflichtaufgaben = Math.max(maxPflichtaufgaben, groupData.pflichtaufgaben.rows.length);
            }
        });

        return {
            totalChecklists: maxChecklists || 23,
            totalPflichtaufgaben: maxPflichtaufgaben || 22
        };
    }

    // Letzter Fallback
    return { totalChecklists: 23, totalPflichtaufgaben: 22 };
}

// Übersichts-Statistiken aktualisieren
function updateOverviewStats(groupStats, users) {
    // Pflichtaufgaben-Fortschritt zeitproportional zum gewählten Referenztermin (Gesamt-Card)
    const cardSelectedWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || maxSchoolweeks);
    const validUsers = users.filter(user => user && user.name);

    let cardAvgProgress = 0;
    let validCount = 0;
    validUsers.forEach(user => {
        const result = calculatePflichtaufgabenProgressGesamt(user, cardSelectedWeek);
        if (result !== null) {
            cardAvgProgress += result.value;
            validCount++;
        }
    });

    if (validCount > 0) {
        cardAvgProgress = cardAvgProgress / validCount;
    }

    const avgCompletionEl = document.getElementById('avgCompletionText');
    const avgCompletionBar = document.getElementById('avgCompletionBar');
    if (avgCompletionEl) avgCompletionEl.textContent = cardAvgProgress.toFixed(1) + '%';
    if (avgCompletionBar) avgCompletionBar.style.width = Math.min(cardAvgProgress, 100) + '%';

    const avgGradeElement = document.getElementById('avgGradeText');
    if (avgGradeElement) avgGradeElement.textContent = calculateGradeFromPflichtProgress(cardAvgProgress);

    // Durchschnittsnote Pflichtaufgaben
    const pflichtAvgGradeElement = document.getElementById('pflichtAverageGrade');
    let pflichtGradeDisplay = '-';

    if (currentGroup === 'all') {
        // Bei "Alle Gruppen": Durchschnitt aus allen Gruppen-Noten berechnen
        if (dashboardData && dashboardData.groups) {
            let totalPercent = 0;
            let groupCount = 0;

            Object.keys(dashboardData.groups).forEach(groupName => {
                const groupGrade = calculatePflichtaufgabenGradeForGroup(groupName);
                if (groupGrade && groupGrade.grade !== null) {
                    totalPercent += groupGrade.percent;
                    groupCount++;
                }
            });

            if (groupCount > 0) {
                const avgPercent = totalPercent / groupCount;
                const avgGrade = convertPercentToIHKGrade(avgPercent);
                pflichtGradeDisplay = `${avgGrade.toFixed(1)} (${avgPercent.toFixed(1)}%)`;
            }
        }
    } else {
        // Bei konkreter Gruppe: calculatePflichtaufgabenGradeForGroup verwenden
        const groupGrade = calculatePflichtaufgabenGradeForGroup(currentGroup);
        if (groupGrade && groupGrade.grade !== null) {
            pflichtGradeDisplay = `${groupGrade.grade.toFixed(1)} (${groupGrade.percent.toFixed(1)}%)`;
        }
    }

    if (pflichtAvgGradeElement) pflichtAvgGradeElement.textContent = pflichtGradeDisplay;

    // HJ1-Cards befüllen
    updateHalbjahrCards(users);

    // Detailierte Fortschritts-Tabelle generieren
    generateGroupProgressTable(users);
}

// Kennzahlen-Cards des aktiven Halbjahres befuellen
function updateHalbjahrCards(users) {
    const noData = '-';
    const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const ids = ['hjQuantitaetText', 'hjQualitaetText', 'hjGradeText', 'hjDeltaText'];

    if (currentGroup === 'all' || !users || users.length === 0) {
        ids.forEach(id => setEl(id, noData));
        return;
    }

    const sliderWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 0) || undefined;

    let sumQ = 0, countQ = 0;
    let sumQual = 0, countQual = 0;
    let sumGrade = 0, countGrade = 0;
    let sumDelta = 0, countDelta = 0;

    users.forEach(user => {
        const ma = calculateMitarbeitsnote(user, currentGroup, sliderWeek);
        if (!ma) return;
        if (ma.quantitaet !== null) { sumQ += ma.quantitaet; countQ++; }
        if (ma.qualitaet !== null) { sumQual += ma.qualitaet; countQual++; }
        if (ma.grade !== null) { sumGrade += ma.grade; countGrade++; }
        if (ma.deltaStunden !== null && ma.deltaStunden !== undefined) {
            sumDelta += ma.deltaStunden; countDelta++;
        }
    });

    setEl('hjQuantitaetText', countQ > 0 ? (sumQ / countQ).toFixed(1) + '%' : noData);
    setEl('hjQualitaetText', countQual > 0 ? (sumQual / countQual).toFixed(1) + '%' : noData);
    setEl('hjGradeText', countGrade > 0 ? (sumGrade / countGrade).toFixed(1) : noData);

    // Delta in Unterrichtsstunden — die Groesse, die im Schueler-Dashboard
    // vorne steht: wie viele Stunden liegt die Klasse vor oder zurueck.
    if (countDelta > 0) {
        const d = sumDelta / countDelta;
        setEl('hjDeltaText', (d >= 0 ? '+' : '') + d.toFixed(1) + ' Std.');
    } else {
        setEl('hjDeltaText', noData);
    }
}

// Statistiken für eine einzelne Gruppe berechnen
function calculateStatsForGroup(groupName, groupData) {
    const users = groupData.users || [];
    const totalUsers = users.length;

    if (totalUsers === 0) {
        return {
            groupName: groupName,
            userCount: 0,
            avgCompletedChecklists: 0,
            avgCompletedPflichtaufgaben: 0,
            avgRequiredProgress: 0,
            avgAllProgress: 0,
            avgGrade: null,
            expectedChecklistsForWeek: 0,
            expectedPflichtaufgabenForWeek: 0,
            checklistPercentage: 0,
            pflichtaufgabenPercentage: 0
        };
    }

    // Grundlegende Berechnungen
    const avgCompletedChecklists = users.reduce((sum, user) => sum + user.checklists.required_100_count, 0) / totalUsers;
    const avgCompletedPflichtaufgaben = users.reduce((sum, user) => sum + user.assignments.submitted_count, 0) / totalUsers;

    // Berechne tatsächliche Durchschnittswerte basierend auf der ausgewählten Woche
    let avgRequiredProgress = 0;
    let avgAllProgress = 0;

    // Verwende week-basierte Berechnung für jeden Benutzer
    // Hole den aktuellen Wochenwert vom Slider
    const selectedWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 10);
    users.forEach(user => {
        const actualProgress = calculateActualProgressForWeek(user, selectedWeek, 10, groupName);
        avgRequiredProgress += actualProgress.pflichtProgress;
        avgAllProgress += actualProgress.gesamtProgress;
    });

    avgRequiredProgress = avgRequiredProgress / totalUsers;
    avgAllProgress = avgAllProgress / totalUsers;


    // Durchschnittsnote: Verwende die vom Backend berechnete IHK-konforme Gruppendurchschnittsnote
    const avgGrade = groupData.assignments && groupData.assignments.avg_grade !== null ? groupData.assignments.avg_grade : null;

    // Erwartete Werte für aktuelle Referenzwoche
    const { totalChecklists, totalPflichtaufgaben } = getTotalCounts();
    const expectedChecklistsForWeek = Math.ceil((totalChecklists / maxSchoolweeks) * selectedWeek);
    const expectedPflichtaufgabenForWeek = Math.ceil((totalPflichtaufgaben / maxSchoolweeks) * selectedWeek);

    // Prozentsätze
    const checklistPercentage = expectedChecklistsForWeek > 0 ?
        (avgCompletedChecklists / expectedChecklistsForWeek) * 100 : 0;
    const pflichtaufgabenPercentage = expectedPflichtaufgabenForWeek > 0 ?
        (avgCompletedPflichtaufgaben / expectedPflichtaufgabenForWeek) * 100 : 0;

    return {
        groupName: groupName,
        userCount: totalUsers,
        avgCompletedChecklists: Math.round(avgCompletedChecklists * 10) / 10,
        avgCompletedPflichtaufgaben: Math.round(avgCompletedPflichtaufgaben * 10) / 10,
        avgRequiredProgress: Math.round(avgRequiredProgress * 10) / 10,
        avgAllProgress: Math.round(avgAllProgress * 10) / 10,
        avgGrade: avgGrade ? Math.round(avgGrade * 100) / 100 : null,
        expectedChecklistsForWeek: expectedChecklistsForWeek,
        expectedPflichtaufgabenForWeek: expectedPflichtaufgabenForWeek,
        checklistPercentage: Math.round(checklistPercentage * 10) / 10,
        pflichtaufgabenPercentage: Math.round(pflichtaufgabenPercentage * 10) / 10
    };
}

// Gruppen-Vergleichstabelle generieren (für "Alle Gruppen" Ansicht)
function generateGroupComparisonTable() {
    const container = document.getElementById('groupProgressTable');
    if (!container || !dashboardData || !dashboardData.groups) return;

    // Titel aktualisieren
    const titleElement = document.getElementById('groupDetailTitle');
    if (titleElement) {
        const kursTitel = currentHalbjahr && currentHalbjahr !== 'gesamt'
            ? (getCourse(currentHalbjahr)?.titel || 'Schuljahr') : 'Schuljahr';
        titleElement.textContent = `Klassenvergleich – ${kursTitel}`;
    }

    // Gruppen basierend auf aktueller Gruppierung filtern
    let groupsToShow = [];
    groupsToShow = Object.keys(dashboardData.groups);

    if (groupsToShow.length === 0) {
        container.innerHTML = '<p><em>Keine Gruppen verfügbar.</em></p>';
        return;
    }

    let html = '<table id="groupComparisonTable" class="info-table dashboard-table overview-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="group-name-cell">Gruppe</th>';
    html += '<th>Personen</th>';
    html += '<th>Ø Pflicht (%)</th>';
    html += '<th>Ø Note</th>';
    html += '<th>Ø Gesamt (%)</th>';
    html += '<th>Ø Eingereichte Aufgaben</th>';
    html += '<th>Ø Note Pflichtaufgaben</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    // Zeitprojektion für Gruppenwerte anwenden

    // Statistiken für jede Gruppe berechnen und anzeigen
    groupsToShow.forEach(groupName => {
        const groupData = dashboardData.groups[groupName];
        const stats = calculateStatsForGroup(groupName, groupData);

        // Verwende die bereits berechneten tatsächlichen Fortschrittswerte für die ausgewählte Woche
        const displayRequiredProgress = stats.avgRequiredProgress;

        // Berechne Note basierend auf Gruppendurchschnitt Pflicht %
        const gradeText = calculateGradeFromPflichtProgress(displayRequiredProgress);

        // Berechne Pflichtaufgaben-Note für die ganze Gruppe
        const groupPflichtGrade = calculatePflichtaufgabenGradeForGroup(groupName);
        let pflichtGradeText = '-';
        let pflichtGradeColor = '#6C757D';
        if (groupPflichtGrade && groupPflichtGrade.grade !== null) {
            pflichtGradeText = `${groupPflichtGrade.grade.toFixed(0)}<br>(${groupPflichtGrade.percent.toFixed(1)}%)`;
            pflichtGradeColor = getGradeColor(groupPflichtGrade.grade);
        }

        // Zeige die gleichen Werte wie in den Cards:
        // "Ø Checklisten 100%" = avgCompletedChecklists (wie completedCount in der Card)
        // "Ø Pflichtaufgaben eingereicht" = avgCompletedPflichtaufgaben (wie pflichtCompletedCount in der Card)

        html += '<tr>';
        html += `<td class="group-name-cell"><strong>${stats.groupName}</strong></td>`;
        html += `<td class="text-center">${stats.userCount}</td>`;
        html += `<td class="progress-cell progress-color-info" style="--progress-width: ${displayRequiredProgress}%;">${displayRequiredProgress.toFixed(1)}%</td>`;
        html += `<td class="text-center text-bold">${gradeText}</td>`;
        html += `<td class="progress-cell progress-color-secondary" style="--progress-width: ${stats.avgAllProgress}%;">${stats.avgAllProgress.toFixed(1)}%</td>`;
        html += `<td class="progress-cell progress-color-warning" style="--progress-width: ${Math.min(stats.avgCompletedPflichtaufgaben * 10, 100)}%;">${stats.avgCompletedPflichtaufgaben.toFixed(1)}</td>`;
        html += `<td class="text-center text-bold" style="color: ${pflichtGradeColor};" title="Durchschnitt von ${groupPflichtGrade ? groupPflichtGrade.count : 0} Personen mit bewerteten Pflichtaufgaben">${pflichtGradeText}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('groupComparisonTable');
    
    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('groupProgressTable'), 50);
}

// Berechnet die tatsächlichen Fortschrittsprozentsätze basierend nur auf Checklisten bis zur ausgewählten Woche
function calculateActualProgressForWeek(user, selectedWeek, maxWeeks, groupName = null) {
    // Standardwerte falls keine strukturierten Daten verfügbar sind
    let pflichtProgress = 0;
    let gesamtProgress = 0;
    let rawPflichtPercent = null;      // Summe der Pflicht-% aller Pflicht-Checklisten
    let rawExpectedPflicht = null;     // Erwartete Punkte bei gewählter Woche

    // Bestimme die zu verwendende Gruppe
    const targetGroup = groupName || currentGroup;

    // Zugriff auf strukturierte Checklisten-Daten
    if (dashboardData && dashboardData.structured_tables && targetGroup && targetGroup !== 'all') {
        const tableData = dashboardData.structured_tables[targetGroup]?.checklists;
        if (tableData && tableData.rows && tableData.headers) {
            // Finde den Index des Benutzers in den Headern
            const userIndex = tableData.headers.findIndex(header => header === user.name);

            if (userIndex > 0) { // Index 0 ist normalerweise die Checklist-Spalte
                // Zähle Pflicht-Checklisten (is_mandatory: true) für Pflicht-Spalte
                const mandatoryChecklists = tableData.rows.filter(row =>
                    row.is_mandatory !== undefined ? row.is_mandatory : true
                );
                const totalMandatoryChecklists = mandatoryChecklists.length;

                // Für Gesamt: ALLE Checklisten zählen (Pflicht + Optional)
                const totalAllChecklists = tableData.rows.length;

                // Summiere Pflicht-Prozente von NUR PFLICHT-Checklisten
                let totalPflichtPercent = 0;
                mandatoryChecklists.forEach(row => {
                    if (row.user_progress && row.user_progress[userIndex - 1]) {
                        const progress = row.user_progress[userIndex - 1];
                        const requiredProgressText = progress.required_progress || '0%';
                        const pflichtPercent = parseFloat(requiredProgressText.replace('%', ''));

                        if (!isNaN(pflichtPercent)) {
                            totalPflichtPercent += pflichtPercent;
                        }
                    }
                });

                // Summiere Gesamt-Prozente von ALLEN Checklisten (Pflicht + Optional)
                let totalGesamtPercent = 0;
                tableData.rows.forEach(row => {
                    if (row.user_progress && row.user_progress[userIndex - 1]) {
                        const progress = row.user_progress[userIndex - 1];
                        const allProgressText = progress.all_progress || '0%';
                        const gesamtPercent = parseFloat(allProgressText.replace('%', ''));

                        if (!isNaN(gesamtPercent)) {
                            totalGesamtPercent += gesamtPercent;
                        }
                    }
                });

                // Berechne erwartete Punkte direkt proportional zur Woche
                // Pflicht: Nur Pflicht-Checklisten (z.B. 23 → 2300 Punkte bei Woche 9)
                // Gesamt: ALLE Checklisten (z.B. 38 → 3800 Punkte bei Woche 9)
                const maxPflichtPoints = totalMandatoryChecklists * 100; // 23 * 100 = 2300
                const maxGesamtPoints = totalAllChecklists * 100; // 38 * 100 = 3800
                const expectedTotalPflichtPoints = (maxPflichtPoints / maxSchoolweeks) * selectedWeek;
                const expectedTotalGesamtPoints = (maxGesamtPoints / maxSchoolweeks) * selectedWeek;

                // Berechne Prozentsatz: Tatsächliche Punkte / Erwartete Punkte × 100
                rawPflichtPercent = totalPflichtPercent;
                rawExpectedPflicht = expectedTotalPflichtPoints;
                if (expectedTotalPflichtPoints > 0) {
                    pflichtProgress = Math.round((totalPflichtPercent / expectedTotalPflichtPoints) * 100 * 100) / 100;
                }
                if (expectedTotalGesamtPoints > 0) {
                    gesamtProgress = Math.round((totalGesamtPercent / expectedTotalGesamtPoints) * 100 * 100) / 100;
                }

                // Debug: Zeige neue Berechnungslogik
                dashboardLogger.debug('CALC', `Progress calculation for ${user.name}`, {
                    week: selectedWeek,
                    maxSchoolweeks: maxSchoolweeks,
                    totalMandatoryChecklists: totalMandatoryChecklists,
                    totalAllChecklists: totalAllChecklists,
                    maxPflichtPoints: maxPflichtPoints,
                    maxGesamtPoints: maxGesamtPoints,
                    expectedPflichtPoints: Math.round(expectedTotalPflichtPoints * 10) / 10,
                    expectedGesamtPoints: Math.round(expectedTotalGesamtPoints * 10) / 10,
                    totalPflicht: totalPflichtPercent,
                    totalGesamt: totalGesamtPercent,
                    pflichtProgress,
                    gesamtProgress
                });
            }
        }
    }

    // Fallback: Verwende die ursprünglichen projizierten Werte falls strukturierte Daten nicht verfügbar
    if (pflichtProgress === 0 && gesamtProgress === 0 && user.checklists) {
        const projectedPflichtProgress = selectedWeek > 0 ?
            Math.round(((user.checklists.avg_required_progress / selectedWeek) * 10) * 100) / 100 : 0;
        const projectedGesamtProgress = selectedWeek > 0 ?
            Math.round(((user.checklists.avg_all_progress / selectedWeek) * 10) * 100) / 100 : 0;

        pflichtProgress = projectedPflichtProgress;
        gesamtProgress = projectedGesamtProgress;
    }

    return {
        pflichtProgress: pflichtProgress,
        gesamtProgress: gesamtProgress,
        rawPflichtPercent: rawPflichtPercent,
        rawExpectedPflicht: rawExpectedPflicht
    };
}

// Berechnet die Note basierend auf dem Pflicht % Fortschritt nach IHK-Notenschlüssel
function calculateGradeFromPflichtProgress(pflichtProgress) {
    if (pflichtProgress >= 92) {
        return '1.0';
    } else if (pflichtProgress >= 81) {
        return '2.0';
    } else if (pflichtProgress >= 67) {
        return '3.0';
    } else if (pflichtProgress >= 50) {
        return '4.0';
    } else if (pflichtProgress >= 30) {
        return '5.0';
    } else if (pflichtProgress > 0) {
        return '6.0';
    } else {
        return '-';
    }
}

// ============================================================
// MITARBEITSNOTEN-BERECHNUNG
// ============================================================

// Gibt die Schiene für eine Gruppe zurück (z.B. "Schiene1")
// Unterstützt exakten Treffer und Prefix-Matching (z.B. "IFA12B" matcht "IFA12B - Team 1")
function getTrackForGroup(groupName) {
    if (!mitarbeitsnoteConfig || !mitarbeitsnoteConfig.class_to_track) return null;
    const map = mitarbeitsnoteConfig.class_to_track;
    if (map[groupName]) return map[groupName];
    for (const key of Object.keys(map)) {
        if (groupName.startsWith(key)) return map[key];
    }
    return null;
}

// Gibt die aktuelle Schulwoche (1-9) basierend auf dem heutigen Datum zurück.
// Gibt 0 zurück wenn vor der ersten Woche, die letzte Woche wenn danach.
function getCurrentReferenceWeekForTrack(track) {
    if (!mitarbeitsnoteConfig || !mitarbeitsnoteConfig.track_schedules) return 0;
    const schedule = mitarbeitsnoteConfig.track_schedules[track];
    if (!schedule || schedule.length === 0) return 0;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let currentWeek = 0;
    for (const entry of schedule) {
        const start = new Date(entry.start);
        if (today >= start) {
            currentWeek = entry.week;
        }
    }
    return currentWeek;
}

// Gibt Roh-Checklisten-Daten für einen Benutzer zurück
// Rückgabe: {totalPflichtPercent, totalMandatoryChecklists} oder null
function getChecklistRawData(user, groupName) {
    const targetGroup = groupName || currentGroup;
    if (!dashboardData || !dashboardData.structured_tables) return null;
    const tableData = dashboardData.structured_tables[targetGroup] && dashboardData.structured_tables[targetGroup].checklists;
    if (!tableData || !tableData.rows || !tableData.headers) return null;

    const userIndex = tableData.headers.findIndex(h => h === user.name);
    if (userIndex <= 0) return null;

    const mandatoryChecklists = tableData.rows.filter(row =>
        row.is_mandatory !== undefined ? row.is_mandatory : true
    );

    let totalPflichtPercent = 0;
    mandatoryChecklists.forEach(row => {
        if (row.user_progress && row.user_progress[userIndex - 1]) {
            const progress = row.user_progress[userIndex - 1];
            const pct = parseFloat((progress.required_progress || '0%').replace('%', ''));
            if (!isNaN(pct)) totalPflichtPercent += pct;
        }
    });

    return {
        totalPflichtPercent: totalPflichtPercent,
        totalMandatoryChecklists: mandatoryChecklists.length
    };
}

// Berechnet den Pflichtaufgaben-Durchschnitt mit Datumsfilter
// cutoffDate: ISO-Datum-String (z.B. "2025-12-10")
// useAfter: false = nur Aufgaben VOR cutoffDate, true = nur Aufgaben NACH cutoffDate
function calculatePflichtaufgabenGradeFiltered(userName, cutoffDate, useAfter) {
    if (!dashboardData || !dashboardData.activities_by_category) return null;
    const cutoff = cutoffDate ? new Date(cutoffDate) : null;
    let totalPercent = 0;
    let count = 0;

    for (const category of dashboardData.activities_by_category) {
        if (!category.category_name || !category.category_name.includes('Pflichtaufgaben')) continue;
        const allActivities = (category.assignments || []).concat(category.quizzes || []);
        for (const activity of allActivities) {
            const userStatus = (activity.user_status || []).find(s => s.user_name === userName);
            if (!userStatus || !userStatus.grade || userStatus.grade === '-') continue;

            if (cutoff) {
                if (!userStatus.submission_time) continue; // Ohne Datum ignorieren wenn Datumsfilter aktiv
                const submDate = new Date(userStatus.submission_time);
                if (useAfter) {
                    if (submDate <= cutoff) continue;
                } else {
                    if (submDate > cutoff) continue;
                }
            }

            const pct = extractPercentageFromString(userStatus.grade);
            if (pct !== null) {
                totalPercent += pct;
                count++;
            }
        }
    }

    if (count === 0) return null;
    const avg = totalPercent / count;
    return { percent: avg, count: count, grade: convertPercentToIHKGrade(avg) };
}

// Parst eine deutsche Dezimalzahl (z.B. "86,09" oder "86.09") zu einem Float
function parseGermanDecimal(str) {
    if (str === null || str === undefined) return null;
    const cleaned = String(str).replace(',', '.').replace('%', '').trim();
    const val = parseFloat(cleaned);
    return isNaN(val) ? null : val;
}

// Gibt den numerischen Bewertungswert eines manuellen Notenbuchelements für einen User zurück
// Berechnet die Mitarbeitsnote eines Halbjahres.
//
// Seit 2026/27 gibt es nur noch EINE Mitarbeitsnote je Halbjahr; die
// frueheren Funktionen fuer die 1. und die prognostizierte 2. Note sind
// hier zusammengefuehrt. Welches Halbjahr gilt, sagt der Kurs-Scope.
//
// Rueckgabe: {quantitaet, qualitaet, overall, grade, ...}
function calculateMitarbeitsnote(user, groupName, weekOverride) {
    // Komponente 1: Quantitaet — stundengewichteter Fortschritt aus dem Plan.
    const quantResult = calculateQuantitaet(user, groupName, weekOverride);
    const quantitaet = quantResult ? quantResult.value : null;

    // Komponente 2: Qualitaet — ungewichteter Durchschnitt der Bewertungen.
    // Bewusst nicht stundengewichtet: eine gut gemachte kleine Aufgabe ist
    // so viel wert wie eine gut gemachte grosse.
    const qualResult = calculatePflichtaufgabenGradeFiltered(user.name, null, false);
    const qualitaet = qualResult ? qualResult.percent : null;

    const components = [quantitaet, qualitaet]
        .filter(v => v !== null && v !== undefined);
    if (components.length === 0) return null;

    const overall = components.reduce((a, b) => a + b, 0) / components.length;

    return {
        quantitaet: quantitaet,
        quantitaetPoints: quantResult
            ? { actual: quantResult.stundenErledigt, expected: quantResult.stundenGesamt }
            : null,
        quantitaetSoll: quantResult ? quantResult.sollProzent : null,
        deltaStunden: quantResult ? quantResult.deltaStunden : null,
        qualitaet: qualitaet,
        qualitaetCount: qualResult ? qualResult.count : null,
        overall: overall,
        grade: convertPercentToIHKGrade(overall),
        componentCount: components.length
    };
}

// Stundengewichteter Fortschritt eines Kurses.
//
// Ersetzt die frueheren MA1/MA2-Quantitaetsfunktionen: Halbjahre sind seit
// 2026/27 getrennte Kurse, deshalb entfaellt die Aufteilung einer
// Aufgabenliste per Wochenanteil samt Uebertrag.
//
// Ist  = Summe Stunden abgegebener Aufgaben / Summe Stunden aller Aufgaben
// Soll = Summe Stunden der Schulwochen 1..w / Summe Stunden aller Wochen
//
// Rueckgabe: {ist, soll, deltaStunden, stundenErledigt, stundenGesamt, ...}
function calculateQuantitaet(user, groupName, weekOverride) {
    if (!plan) return null;

    const a = user.assignments || {};
    const stundenGesamt = a.stunden_gesamt || 0;
    if (stundenGesamt <= 0) return null;

    const stundenErledigt = a.stunden_erledigt || 0;
    const ist = stundenErledigt / stundenGesamt;

    const track = getTrackForGroup(groupName);
    const wochen = getSchulwochenForScope(track);
    const woche = weekOverride !== undefined && weekOverride !== null
        ? weekOverride
        : getCurrentReferenceWeekForTrack(track);
    const soll = sollAnteil(wochen, woche);

    return {
        value: Math.round(ist * 1000) / 10,       // Prozent, eine Nachkommastelle
        ist: ist,
        soll: soll,
        sollProzent: Math.round(soll * 1000) / 10,
        deltaStunden: Math.round((ist - soll) * stundenGesamt * 10) / 10,
        stundenErledigt: stundenErledigt,
        stundenGesamt: stundenGesamt,
        aufgabenErledigt: a.aufgaben_erledigt || 0,
        aufgabenGesamt: a.aufgaben_gesamt || 0,
        woche: woche
    };
}

// Gesamtfortschritt gegen das zeitproportionale Soll.
//
// Frueher gezaehlte Aufgaben gegen "Anzahl x Woche / maxWochen"; jetzt
// Stunden gegen den Soll-Anteil des Wochenkalenders. Damit rechnet diese
// Funktion wie calculateQuantitaet und liefert konsistente Werte.
//
// value > 100 % heisst: weiter als zum Stichtag erwartet.
function calculatePflichtaufgabenProgressGesamt(user, selectedWeek) {
    const a = (user && user.assignments) || {};
    const stundenGesamt = a.stunden_gesamt || 0;
    if (stundenGesamt <= 0) return null;

    const stundenErledigt = a.stunden_erledigt || 0;
    const wochen = getSchulwochenForScope(getTrackForGroup(user.group || currentGroup));
    const soll = sollAnteil(wochen, selectedWeek);

    // Vor der ersten Blockwoche gibt es kein Soll — dann zeigen wir den
    // absoluten Fortschritt statt durch null zu teilen.
    if (soll <= 0) {
        return {
            value: Math.round((stundenErledigt / stundenGesamt) * 1000) / 10,
            actual: stundenErledigt,
            expected: stundenGesamt,
            total: a.aufgaben_gesamt || 0
        };
    }

    const erwarteteStunden = soll * stundenGesamt;
    return {
        value: Math.round((stundenErledigt / erwarteteStunden) * 1000) / 10,
        actual: Math.round(stundenErledigt * 10) / 10,
        expected: Math.round(erwarteteStunden * 10) / 10,
        total: a.aufgaben_gesamt || 0
    };
}

// Soll-Anteil nach Stunden — Gegenstueck zu sollAnteil() in js/bilanz.js.
// Woche 1 hat 10 Stunden, die uebrigen 14; eine lineare Naeherung
// (woche / anzahlWochen) waere daher schon innerhalb eines Halbjahres falsch.
function sollAnteil(schulwochen, woche) {
    if (!schulwochen || schulwochen.length === 0) return 0;
    const gesamt = schulwochen.reduce((summe, w) => summe + (w.stunden || 0), 0);
    if (gesamt <= 0) return 0;
    const bisher = schulwochen
        .filter(w => w.woche <= woche)
        .reduce((summe, w) => summe + (w.stunden || 0), 0);
    return bisher / gesamt;
}

// Wochenkalender der Schiene, auf den aktiven Kurs-Scope beschnitten.
// Bei Einzelansicht eines Halbjahres darf sich das Soll nicht auf
// Blockwochen des anderen Halbjahres stuetzen.
function getSchulwochenForScope(track) {
    if (!plan || !plan.schienen) return [];
    const schiene = plan.schienen[track] || Object.values(plan.schienen)[0];
    if (!schiene) return [];
    const wochen = schiene.schulwochen || [];

    if (!currentHalbjahr || currentHalbjahr === 'gesamt') return wochen;

    // Grenze ist die Freischaltung des naechsten Kurses.
    const kurse = plan.kurse || [];
    const idx = kurse.findIndex(k => k.id === currentHalbjahr);
    if (idx < 0) return wochen;

    const ab = kurse[idx].freischaltung ? new Date(kurse[idx].freischaltung) : null;
    const bis = (idx + 1 < kurse.length && kurse[idx + 1].freischaltung)
        ? new Date(kurse[idx + 1].freischaltung) : null;

    return wochen.filter(w => {
        const start = new Date(w.start);
        if (ab && start < ab) return false;
        if (bis && start >= bis) return false;
        return true;
    });
}

// Hilfsfunktion: Rendert eine Prozentzelle mit Farbe und Fallback
// points: optional {actual, expected} – zeigt "(actual / expected)" als Sub-Label
// extraLabel: optionaler Zusatztext (z.B. "inkl. 2 aus 1.HJ")
function renderPctCell(value, cssClass, points = null, decimals = 1, extraLabel = null) {
    if (value === null || value === undefined) {
        return `<td class="text-center" style="color:#6C757D;">–</td>`;
    }
    const capped = Math.min(Math.max(value, 0), 200);
    const extraStr = extraLabel ? ` · ${extraLabel}` : '';
    const pointsStr = points !== null
        ? `<span class="cell-points">${Math.round(points.actual)} / ${Math.round(points.expected)}${extraStr}</span>`
        : (extraLabel ? `<span class="cell-points">${extraLabel}</span>` : '');
    return `<td class="progress-cell ${cssClass}" style="--progress-width: ${Math.min(capped, 100)}%;">${value.toFixed(decimals)}%${pointsStr}</td>`;
}

// Hilfsfunktion: Rendert eine Notenzelle
// overall: optionaler Gesamtprozentwert, der als Sub-Label angezeigt wird
function renderGradeCell(grade, overall = null) {
    if (grade === null || grade === undefined) {
        return `<td class="text-center" style="color:#6C757D;">–</td>`;
    }
    const overallStr = overall !== null
        ? ` (${overall.toFixed(1)}%)`
        : '';
    return `<td class="text-center text-bold" style="color: ${getGradeColor(grade)};">${grade.toFixed(1)}${overallStr}</td>`;
}

// Generiert die Fortschritts-Tabelle für die Übersicht
function generateGroupProgressTable(users) {
    const container = document.getElementById('groupProgressTable');
    if (!container) return;
    const halbjahresContainer = document.getElementById('groupHalbjahresnotenTable');

    // Ohne Daten (gesperrter Kurs) bleibt die Ansicht leer; der Hinweis
    // ueber der Navigation nennt den Grund. Der Titel zieht trotzdem mit,
    // sonst bliebe der des zuvor gewaehlten Kurses stehen.
    if (dashboardData && dashboardData.verfuegbar === false) {
        const gesperrt = currentHalbjahr && currentHalbjahr !== 'gesamt'
            ? getCourse(currentHalbjahr) : null;
        const titelEl = document.getElementById('groupDetailTitle');
        if (titelEl) {
            titelEl.textContent = `${gesperrt ? gesperrt.titel : 'Alle Kurse'} – ${currentGroup}`;
        }
        container.innerHTML = '';
        if (halbjahresContainer) halbjahresContainer.innerHTML = '';
        return;
    }

    // Wenn "Alle Gruppen" ausgewählt ist, zeige Vergleichstabelle und leere Halbjahres-Tabelle
    if (currentGroup === 'all') {
        generateGroupComparisonTable();
        if (halbjahresContainer) halbjahresContainer.innerHTML = '';
        return;
    }

    // Die Tabelle sieht in allen drei Umschalter-Stellungen gleich aus;
    // nur der zugrunde liegende Datensatz wechselt: "Gesamt" fasst alle
    // Kurse zusammen, ein Halbjahr zeigt genau seinen Kurs.
    const kurs = currentHalbjahr && currentHalbjahr !== 'gesamt'
        ? getCourse(currentHalbjahr) : null;
    const zeitraum = kurs ? kurs.titel : 'Alle Kurse';

    const titleElement = document.getElementById('groupDetailTitle');
    if (titleElement) {
        titleElement.textContent = `${zeitraum} – ${currentGroup}`;
    }

    if (users.length === 0) {
        container.innerHTML = '<p><em>Keine Daten verfügbar.</em></p>';
        if (halbjahresContainer) halbjahresContainer.innerHTML = '';
        return;
    }

    // Bezugswoche: der Slider, sonst die laufende Woche der Schiene.
    const track = getTrackForGroup(currentGroup);
    const wochen = getSchulwochenForScope(track);
    const sliderWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 0);
    const woche = sliderWeek > 0 ? sliderWeek : getCurrentReferenceWeekForTrack(track);
    const sollPct = Math.round(sollAnteil(wochen, woche) * 1000) / 10;

    let html = '';
    html += `<div class="stats-group-title" style="margin-bottom: 8px;">`;
    html += `<span>${zeitraum} (Woche ${woche} von ${wochen.length}, `
          + `Soll ${sollPct.toFixed(1)} %, Schiene: ${track || '–'})</span>`;
    html += `</div>`;
    html += '<table id="individualProgressTable" class="info-table dashboard-table overview-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="person-name">Person</th>';
    html += '<th title="Erreichte Stunden gemessen am Soll der gewählten Woche — über 100 % heißt: dem Plan voraus">Quantität Pflicht (%)</th>';
    html += '<th title="Vorsprung bzw. Rückstand in Unterrichtsstunden">Delta (Std.)</th>';
    html += '<th title="Note aus der Quantität (Schwellen 92/81/67/50/30 %)">Note</th>';
    html += '<th title="Ungewichteter Durchschnitt der Bewertungen">Qualität (%)</th>';
    html += '<th>Eingereichte Aufgaben</th>';
    html += '<th>Note Pflichtaufgaben</th>';
    html += '<th title="(Quantität + Qualität) / 2 — die Quantität dafür bei 100 % gekappt">Mitarbeitsnote</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    users.forEach(user => {
        // Quantitaet relativ zum Soll der Woche — kann ueber 100 % gehen,
        // wer dem Plan voraus ist.
        const pflichtResult = calculatePflichtaufgabenProgressGesamt(user, woche);
        const quantitaet = pflichtResult ? pflichtResult.value : 0;
        const pflichtPoints = pflichtResult
            ? { actual: pflichtResult.actual, expected: pflichtResult.expected }
            : null;

        // Delta und Qualitaet stammen aus derselben Rechnung wie bisher.
        const ma = calculateMitarbeitsnote(user, currentGroup, woche);
        const qualitaet = ma ? ma.qualitaet : null;
        const deltaStunden = ma ? ma.deltaStunden : null;

        // Note aus der Quantitaet (Schwellen 92/81/67/50/30 %).
        const gradeText = calculateGradeFromPflichtProgress(quantitaet);

        // Mitarbeitsnote: Mittel aus Quantitaet und Qualitaet. Die
        // Quantitaet wird dafuer bei 100 % gekappt — ein Vorsprung soll
        // eine schwache Qualitaet nicht rechnerisch ausgleichen.
        const quantFuerNote = Math.min(quantitaet, 100);
        const maKomponenten = [quantFuerNote, qualitaet]
            .filter(v => v !== null && v !== undefined);
        const maOverall = maKomponenten.length > 0
            ? maKomponenten.reduce((a, b) => a + b, 0) / maKomponenten.length
            : null;
        const maGrade = maOverall !== null ? convertPercentToIHKGrade(maOverall) : null;

        // Note der bewerteten Pflichtaufgaben
        const pflichtGradeResult = calculatePflichtaufgabenGradeForUserByName(user.name, currentGroup);
        let pflichtGradeText = '–';
        let pflichtGradeColor = '#6C757D';
        if (pflichtGradeResult && pflichtGradeResult.grade !== null) {
            pflichtGradeText = `${pflichtGradeResult.grade.toFixed(0)} (${pflichtGradeResult.percent.toFixed(0)}%, N=${pflichtGradeResult.count})`;
            pflichtGradeColor = getGradeColor(pflichtGradeResult.grade);
        }

        html += '<tr>';
        html += `<td class="person-name"><strong>${user.name}</strong></td>`;

        const stundenSub = pflichtPoints
            ? `<span class="cell-points">${Math.round(pflichtPoints.actual)} / ${Math.round(pflichtPoints.expected)} Std.</span>`
            : '';
        html += `<td class="progress-cell progress-color-info" style="--progress-width: ${Math.min(quantitaet, 100)}%;">`
              + `${quantitaet.toFixed(0)}%${stundenSub}</td>`;

        // Delta: positiv = voraus, negativ = im Rueckstand.
        if (deltaStunden === null || deltaStunden === undefined) {
            html += `<td class="text-center" style="color:#6C757D;">–</td>`;
        } else {
            const farbe = deltaStunden >= 0 ? '#1e7e34' : '#dc3545';
            const vz = deltaStunden >= 0 ? '+' : '';
            html += `<td class="text-center text-bold" style="color:${farbe};">`
                  + `${vz}${deltaStunden.toFixed(1)}</td>`;
        }

        html += `<td class="text-center text-bold">${gradeText}</td>`;
        html += renderPctCell(qualitaet, 'progress-color-warning', null, 1);
        html += `<td class="progress-cell progress-color-secondary" style="--progress-width: ${user.assignments.percent_submitted}%;">${user.assignments.submitted_count}</td>`;
        html += `<td class="text-center text-bold" style="color: ${pflichtGradeColor};" `
              + `title="Durchschnitt aus ${pflichtGradeResult ? pflichtGradeResult.count : 0} bewerteten Pflichtaufgaben">${pflichtGradeText}</td>`;
        html += renderGradeCell(maGrade, maOverall);
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('individualProgressTable');

    // Es gibt nur noch diese eine Tabelle je Ansicht.
    if (halbjahresContainer) halbjahresContainer.innerHTML = '';

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('groupProgressTable'), 50);
}
// Letzte Abgaben je Gruppe anzeigen
// Standardsortierung: Status (inaktive zuerst), sekundär alphabetisch
let recentSortCol = 7;
let recentSortDir = 'desc';
let recentPflichtOnly = true;

function setRecentPflichtFilter(value) {
    recentPflichtOnly = value === 'pflicht';
    generateRecentSubmissionsTable();
}

function sortRecentSubmissions(colIndex) {
    if (recentSortCol === colIndex) {
        recentSortDir = recentSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        recentSortCol = colIndex;
        recentSortDir = colIndex === 7 ? 'desc' : 'asc';
    }
    generateRecentSubmissionsTable();
}

function generateRecentSubmissionsTable() {
    const container = document.getElementById('recentSubmissionsTable');
    const section = document.getElementById('recentSubmissionsSection');
    if (!container || !section) return;

    const recentData = dashboardData && dashboardData.recent_submissions;

    if (!recentData || Object.keys(recentData).length === 0) {
        section.style.display = 'none';
        return;
    }

    // Filtere auf aktuelle Gruppierung / Gruppe (ignorierte Gruppen ausschließen)
    const ignoredGroups = (dashboardData && dashboardData.ignored_groups) || [];
    let groupNames = Object.keys(recentData).filter(name => !ignoredGroups.includes(name));
    if (currentGroup !== 'all') {
        groupNames = groupNames.filter(name => name === currentGroup);
    }

    if (groupNames.length === 0) {
        section.style.display = 'none';
        return;
    }

    // Spalten: 0=Gruppe, 1=Abgabedatum, 2=Aufgabe, 3=Kategorie, 4=Bewertung, 5=Kalendertage, 6=Schularbeitstage, 7=Status
    const getSortKey = (name) => {
        const e = recentData[name];
        const recent = e.recent_submissions || [];
        const lastTime = recent[0]?.time || e.last_submission_time || '';
        const lastTitle = recent[0]?.title || e.last_submission_title || '';
        switch (recentSortCol) {
            case 0: return name.toLowerCase();
            case 1: return lastTime;
            case 2: return lastTitle.toLowerCase();
            case 3: return (recent[0]?.category_name || e.last_submission_category || '').toLowerCase();
            case 4: return (recent[0]?.grade_display || e.last_submission_grade || '').toString().toLowerCase();
            case 5: return e.calendar_days_since ?? Infinity;
            case 6: return e.school_days_since ?? Infinity;
            case 7: return e.no_submissions ? 2 : e.inactive ? 1 : 0;
            default: return name.toLowerCase();
        }
    };

    groupNames.sort((a, b) => {
        const ka = getSortKey(a);
        const kb = getSortKey(b);
        let cmp = 0;
        if (typeof ka === 'number') {
            cmp = ka - kb;
        } else {
            cmp = ka < kb ? -1 : ka > kb ? 1 : 0;
        }
        if (cmp !== 0) return recentSortDir === 'asc' ? cmp : -cmp;
        // Sekundärsortierung bei Gleichstand: alphabetisch nach Gruppenname
        return a.localeCompare(b, 'de');
    });

    // Timezone-sicheres Datum: ISO-String direkt parsen
    const fmtDate = iso => {
        if (!iso) return '—';
        const parts = iso.substring(0, 10).split('-');
        if (parts.length !== 3) return iso;
        return `${parts[2]}.${parts[1]}.${parts[0]}`;
    };

    const fmtGrade = g => (g != null) ? g : '—';

    const colLabels = ['Gruppe', 'Abgabedatum', 'Aufgabe', 'Kategorie', 'Bewertung', 'Tage', 'Schultage', 'Status'];
    const centerCols = new Set([4, 5, 6]);

    const thList = colLabels.map((label, i) => {
        const align = centerCols.has(i) ? ' style="text-align:center;"' : '';
        const sortClass = i === recentSortCol ? ` sort-${recentSortDir}` : '';
        return `<th class="sortable-header${sortClass}"${align} onclick="sortRecentSubmissions(${i})">${label}</th>`;
    }).join('');

    let html = `<table class="info-table dashboard-table" id="recentSubmissionsDataTable">
        <thead><tr>${thList}</tr></thead><tbody>`;

    for (const groupName of groupNames) {
        const entry = recentData[groupName];
        const noSubs = entry.no_submissions;
        const inactive = entry.inactive;
        const allRecent = entry.recent_submissions || [];
        const recent = allRecent.filter(s => !recentPflichtOnly || s.is_pflicht);

        let statusHtml, groupRowClass;
        if (noSubs) {
            statusHtml = '<span class="badge badge-danger">Keine Abgaben</span>';
            groupRowClass = 'recent-group-header recent-no-subs';
        } else if (inactive) {
            const calD = entry.calendar_days_since ?? '?';
            const schD = entry.school_days_since != null ? entry.school_days_since : '?';
            statusHtml = `<span class="badge badge-warning">Inaktiv<br>(${calD} Kal. / ${schD} Schultage)</span>`;
            groupRowClass = 'recent-group-header recent-inactive';
        } else if (recentPflichtOnly && recent.length === 0) {
            statusHtml = `<span class="badge badge-secondary">Aktiv – keine Pflicht</span>`;
            groupRowClass = 'recent-group-header recent-active';
        } else {
            statusHtml = `<span class="badge badge-success">Aktiv (${allRecent.length})</span>`;
            groupRowClass = 'recent-group-header recent-active';
        }

        const groupId = entry.group_id;
        const fmtBewertbar = (sub, url, type, isBewertbar, gradeDisplay) => {
            const showBewertbar = type === 'assignment' && gradeDisplay == null;
            if (showBewertbar && url && groupId) {
                return `<a href="${bewertungsUrl(url, groupId)}" target="_blank" class="status-text-warning">bewertbar</a>`;
            }
            if (showBewertbar) {
                return '<span class="status-text-warning">bewertbar</span>';
            }
            return fmtGrade(gradeDisplay);
        };

        if (recent.length > 0) {
            const first = recent[0];
            html += `<tr class="${groupRowClass}">
                <td rowspan="${recent.length}"><strong>${groupName}</strong></td>
                <td>${fmtDate(first.time)}</td>
                <td>${first.title}</td>
                <td>${first.category_name || '—'}</td>
                <td style="text-align:center;">${fmtBewertbar(first, first.url, first.activity_type, first.is_bewertbar, first.grade_display)}</td>
                <td style="text-align:center;">${first.calendar_days_ago ?? '—'}</td>
                <td style="text-align:center;">${first.school_days_ago ?? '—'}</td>
                <td rowspan="${recent.length}">${statusHtml}</td>
            </tr>`;
            for (let i = 1; i < recent.length; i++) {
                const sub = recent[i];
                html += `<tr class="recent-sub-row">
                    <td>${fmtDate(sub.time)}</td>
                    <td>${sub.title}</td>
                    <td>${sub.category_name || '—'}</td>
                    <td style="text-align:center;">${fmtBewertbar(sub, sub.url, sub.activity_type, sub.is_bewertbar, sub.grade_display)}</td>
                    <td style="text-align:center;">${sub.calendar_days_ago ?? '—'}</td>
                    <td style="text-align:center;">${sub.school_days_ago ?? '—'}</td>
                </tr>`;
            }
        } else {
            // Inaktiv/keine aktuellen Abgaben: letzte bekannte Abgabe anzeigen
            // Bei aktivem Pflichtfilter: Detailfelder nur anzeigen wenn letzte Abgabe eine Pflichtaufgabe war
            const showFallbackDetails = !recentPflichtOnly || entry.last_submission_is_pflicht;
            html += `<tr class="${groupRowClass}">
                <td><strong>${groupName}</strong></td>
                <td>${showFallbackDetails ? fmtDate(entry.last_submission_time) : '—'}</td>
                <td>${showFallbackDetails ? (entry.last_submission_title || '—') : '—'}</td>
                <td>${showFallbackDetails ? (entry.last_submission_category || '—') : '—'}</td>
                <td style="text-align:center;">${showFallbackDetails ? fmtBewertbar(null, entry.last_submission_url, entry.last_submission_type, entry.last_submission_bewertbar, entry.last_submission_grade) : '—'}</td>
                <td style="text-align:center;">${showFallbackDetails ? (entry.calendar_days_since ?? '—') : '—'}</td>
                <td style="text-align:center;">${showFallbackDetails ? (entry.school_days_since ?? '—') : '—'}</td>
                <td>${statusHtml}</td>
            </tr>`;
        }
    }

    html += '</tbody></table>';
    container.innerHTML = html;
    section.style.display = '';
}

// Progress Ring aktualisieren
function updateProgressRing(ringId, percentage) {
    const ring = document.getElementById(ringId);
    if (ring) {
        const circumference = 2 * Math.PI * 25; // r=25
        const offset = circumference - (percentage / 100) * circumference;
        ring.style.strokeDashoffset = offset;
    }
}

// Fortschrittstyp umschalten (Pflicht/Gesamt)
function toggleProgressType() {
    const currentType = document.querySelector('input[name="progressType"]:checked').value;

    // Labels aktualisieren
    document.querySelectorAll('.progress-toggle label').forEach(label => {
        label.classList.remove('active');
    });

    const activeLabel = document.querySelector(`label[for="${currentType}Label"]`) ||
                       document.querySelector(`#${currentType}Label`);
    if (activeLabel) {
        activeLabel.classList.add('active');
    }

    // Statistiken neu berechnen
    updateDashboard();
}

// Halbjahr-Tab auswählen
// Halbjahr (= Kurs) wechseln. Der Umschalter waehlt seit 2026/27 einen
// Moodle-Kurs aus, keine Notenstufe.
function selectHalbjahr(scope) {
    selectCourseScope(scope);

    // Den Titel der Einzelklassen-Ansicht setzt generateGroupProgressTable
    // selbst; hier nur der Klassenvergleich, der von dort nicht kommt.
    const titleEl = document.getElementById('groupDetailTitle');
    if (titleEl && currentGroup === 'all') {
        const kurs = scope !== 'gesamt' ? getCourse(scope) : null;
        titleEl.textContent = `Klassenvergleich – ${kurs ? kurs.titel : 'Alle Kurse'}`;
    }

    populateGroupSelectors();
    updateDashboard();
    updateAllTabs();
}

// Gruppe über Tab auswählen
function selectGroup(groupName) {
    currentGroup = groupName;
    window.currentGroup = currentGroup; // Sync to window

    // Die Schienen starten zu unterschiedlichen Terminen (Schiene 3 am
    // 15.09., Schiene 1 erst am 28.09.). Mit der Klasse aendert sich
    // daher die laufende Woche — der Slider muss nachziehen.
    updateWeekSlider();

    // Alle Gruppen-Tabs und Dropdowns synchronisieren
    syncGroupSelectors();

    // Dashboard und alle Tabs aktualisieren
    updateDashboard();
    updateAllTabs();
}

// Legacy-Funktion für alte Gruppenauswahl (falls noch verwendet)
function filterByGroup() {
    const groupSelect = document.getElementById('groupSelect');
    if (groupSelect) {
        currentGroup = groupSelect.value;
        window.currentGroup = currentGroup; // Sync to window
    }

    // Alle anderen Gruppen-Dropdowns synchronisieren
    syncGroupSelectors();

    // Dashboard und alle Tabs aktualisieren
    updateDashboard();
    updateAllTabs();
}

// Synchronisiert alle Gruppen-Tabs und Dropdowns
function syncGroupSelectors() {
    syncGroupTabs();

    // Synchronize remaining dropdown selectors
    const selectors = [
        'pflichtGroupFilter'
    ];

    selectors.forEach(selectorId => {
        const selector = document.getElementById(selectorId);
        if (selector && selector.value !== currentGroup) {
            selector.value = currentGroup;
        }
    });
}

// Synchronisiert die Gruppen-Tabs
function syncGroupTabs() {
    // Alle Gruppen-Tabs inaktiv setzen
    document.querySelectorAll('.group-nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Den aktiven Tab markieren
    if (currentGroup === 'all') {
        const allGroupBtn = document.getElementById('groupAll');
        if (allGroupBtn) {
            allGroupBtn.classList.add('active');
        }
    } else {
        const activeGroupBtn = document.getElementById(`group${currentGroup.replace(/\s+/g, '')}`);
        if (activeGroupBtn) {
            activeGroupBtn.classList.add('active');
        }
    }
}

// Aktualisiert alle Tabs basierend auf der aktuellen Gruppenauswahl
function updateAllTabs() {
    // Checklisten-Tab aktualisieren falls sichtbar
    const checklistsTab = document.getElementById('checklistsTab');
    if (checklistsTab && checklistsTab.style.display !== 'none') {
        generateChecklistTable();
        // Spaltenansicht nach dem Neuaufbau der Tabelle anwenden
        applyChecklistColumnView();
        // View-Filter anwenden
        applyChecklistViewFilter();
    }

    // Pflichtaufgaben-Tab aktualisieren falls sichtbar
    const pflichtTab = document.getElementById('pflichtTab');
    if (pflichtTab && pflichtTab.style.display !== 'none') {
        generatePflichtTable();
        // View-Filter anwenden
        applyPflichtViewFilters();
    }

    // Leistungsnachweise-Tab aktualisieren falls sichtbar
    const examTab = document.getElementById('examTab');
    if (examTab && examTab.style.display !== 'none') {
        generateExamTable();
    }
}

// Referenzwoche aktualisieren
function updateReferenceWeek(week) {
    currentWeek = parseInt(week);
    window.currentWeek = currentWeek; // Sync to window
    dashboardLogger.info('USER', 'Referenzwoche geändert', { week: currentWeek });

    // Slider-Wert visuell aktualisieren
    const slider = document.getElementById('referenceWeekSlider');
    if (slider) {
        slider.value = currentWeek;
    }

    // Anzeige der aktuellen Woche aktualisieren
    const weekDisplay = document.getElementById('currentWeekDisplay');
    if (weekDisplay) {
        weekDisplay.textContent = currentWeek;
    }

    // Dashboard aktualisieren
    updateDashboard();
}

// Auf aktuelle Woche setzen — maßgeblich ist der Blockwochen-Kalender
// der Schiene, nicht der Abstand zum Schuljahresbeginn: Blöcke liegen weit
// auseinander, eine Hochrechnung aus dem Kalenderdatum wäre immer falsch.
function setToCurrentWeek() {
    const slider = document.getElementById('referenceWeekSlider');
    if (!slider) return;

    const track = getTrackForGroup(currentGroup) || (plan && Object.keys(plan.schienen)[0]);
    const min = parseInt(slider.min);
    const max = parseInt(slider.max);

    // Dieselbe Klammerung wie in updateWeekSlider(): liegt die laufende
    // Woche außerhalb des angezeigten Halbjahres, gilt dessen Ende.
    const jetzt = getCurrentReferenceWeekForTrack(track);
    const wert = (jetzt >= min && jetzt <= max) ? jetzt : max;

    slider.value = wert;
    updateReferenceWeek(wert);
}

// Checklisten-Tab laden
function loadChecklistsTab() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    const filterSection = document.getElementById('filterSection');

    if (loadingIndicator) loadingIndicator.style.display = 'block';

    setTimeout(() => {
        generateChecklistTable();
        // Spaltenansicht nach dem Laden der Tabelle anwenden
        applyChecklistColumnView();
        if (loadingIndicator) loadingIndicator.style.display = 'none';
        if (filterSection) filterSection.style.display = 'block';
    }, 500);
}

// Checklisten-Tabelle generieren (Zeilen = Checklisten, Spalten = Personen)
function generateChecklistTable() {
    const container = document.getElementById('checklistData');
    if (!container || !dashboardData || !dashboardData.structured_tables) return;

    // Bei "Alle Gruppen" alle Checklisten von allen Benutzern anzeigen
    if (currentGroup === 'all') {
        generateAllGroupsChecklistTable();
        return;
    }

    const tableData = dashboardData.structured_tables[currentGroup]?.checklists;

    if (!tableData) {
        container.innerHTML = '<p>Keine Daten für die ausgewählte Gruppe verfügbar.</p>';
        return;
    }

    const userCount = tableData.headers.length - 1; // Anzahl der Benutzer

    let html = '<table id="checklistTable" class="info-table dashboard-table">';
    html += '<thead><tr class="sticky-header">';

    // Header: Checkliste + Benutzernamen mit je 2 Spalten (Pflicht + Gesamt)
    html += '<th class="checklist-name-cell">Checkliste</th>';

    // Für jeden Benutzer zwei Spalten: Pflicht + Gesamt
    for (let i = 1; i < tableData.headers.length; i++) {
        const userName = tableData.headers[i];
        const displayName = userName.replace(' ', '<br>'); // Line break after first space
        html += `<th colspan="2" class="text-center">${displayName}</th>`;
    }
    html += '</tr>';

    // Zweite Header-Zeile für Pflicht/Gesamt
    html += '<tr class="sticky-header">';
    html += '<th>Typ</th>'; // Leere Zelle für Checkliste-Spalte
    for (let i = 1; i < tableData.headers.length; i++) {
        html += '<th class="sub-header-pflicht">Pflicht</th>';
        html += '<th class="sub-header-gesamt gesamt-column">Gesamt</th>';
    }
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jede Checkliste
    tableData.rows.forEach(row => {
        const isMandatory = row.is_mandatory !== undefined ? row.is_mandatory : true; // Default: true für Abwärtskompatibilität

        // Filter "Nur Pflicht": Überspringe optionale Checklisten
        if (checklistViewType === 'pflicht' && !isMandatory) {
            return; // Zeile komplett ausblenden
        }

        html += '<tr>';

        // Checkliste-Name (mit Link)
        html += `<td class="checklist-name-cell">`;
        html += `<a href="${row.checklist_url}" target="_blank">${row.checklist_title}</a>`;
        html += `<br><small class="category-label">${row.checklist_category}</small>`;
        html += `</td>`;

        // Fortschritt für jeden Benutzer (jeweils Pflicht + Gesamt)
        row.user_progress.forEach(progress => {
            const requiredProgressText = progress.required_progress || '0%';
            const allProgressText = progress.all_progress || '0%';

            const pflichtPercent = parseFloat(requiredProgressText.replace('%', ''));
            const gesamtPercent = parseFloat(allProgressText.replace('%', ''));

            // Pflicht-Fortschritt: Bei nicht-Pflicht Checklisten "-" anzeigen
            let pflichtDisplay = requiredProgressText;
            let pflichtProgressWidth = pflichtPercent;
            if (!isMandatory) {
                pflichtDisplay = '-';
                pflichtProgressWidth = 0;
            }
            html += `<td class="progress-cell" style="--progress-width: ${pflichtProgressWidth}%; class="progress-color-success">${pflichtDisplay}</td>`;

            // Gesamt-Fortschritt (mit gesamt-column Klasse für ein-/ausblenden)
            html += `<td class="progress-cell gesamt-column" style="--progress-width: ${gesamtPercent}%; class="progress-color-secondary">${allProgressText}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('checklistTable');
    
    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('checklistData'), 50);
}

// Pflichtaufgaben-Tab laden
function loadPflichtTab() {
    const filterSection = document.getElementById('pflichtFilterSection');

    setTimeout(() => {
        generatePflichtTable();
        // View-Filter anwenden
        applyPflichtViewFilters();
        if (filterSection) filterSection.style.display = 'block';
    }, 500);
}

// Leistungsnachweise-Tab laden
function loadExamTab() {
    const filterSection = document.getElementById('examFilterSection');

    setTimeout(() => {
        generateExamTable();
        if (filterSection) filterSection.style.display = 'block';
    }, 500);
}

// Hilfsfunktion: Extrahiert Sterne aus einer Bewertung und erstellt kompakte Darstellung mit Prozentwert
function formatStarGrade(grade) {
    if (!grade || grade === '-') return grade;

    // Prüfe ob die Bewertung Sterne enthält
    const starMatch = grade.match(/^(\*+)/);
    if (starMatch) {
        const stars = starMatch[1]; // Nur die Sterne (z.B. "**")

        // Finde den Prozentwert aus dem gradeMapping
        let percentage = null;
        if (gradeMapping && Object.keys(gradeMapping).length > 0) {
            // Durchsuche das gradeMapping nach dem passenden Eintrag
            for (const [points, description] of Object.entries(gradeMapping)) {
                if (description === grade) {
                    percentage = points;
                    break;
                }
            }
        }

        // Zeige Sterne mit Prozentwert, falls vorhanden
        if (percentage !== null) {
            return `<span title="${grade}">${stars} (${percentage}%)</span>`;
        } else {
            return `<span title="${grade}">${stars}</span>`;
        }
    }

    // Keine Sterne gefunden, gebe die originale Bewertung zurück
    return grade;
}

// Formatiert submission_time für die Anzeige
function formatSubmissionTime(submissionTime) {
    if (!submissionTime) {
        return '';
    }

    try {
        // Parse ISO-Format: "2025-10-21T11:33:00"
        const date = new Date(submissionTime);

        // Formatiere als deutsches Datum: DD.MM.YYYY HH:MM
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');

        return `${day}.${month}.${year} ${hours}:${minutes}`;
    } catch (e) {
        return '';
    }
}

// Berechnet die Anzahl der Schultage (Werktage Mo-Fr) zwischen zwei Daten
function getSchoolDaysDiff(fromDate, toDate) {
    let count = 0;
    let currentDate = new Date(fromDate);
    const endDate = new Date(toDate);

    // Setze auf Mitternacht für Tagesvergleich
    currentDate.setHours(0, 0, 0, 0);
    endDate.setHours(0, 0, 0, 0);

    while (currentDate < endDate) {
        const dayOfWeek = currentDate.getDay();
        // Zähle nur Montag (1) bis Freitag (5)
        if (dayOfWeek >= 1 && dayOfWeek <= 5) {
            count++;
        }
        currentDate.setDate(currentDate.getDate() + 1);
    }

    return count;
}

// Pflichtaufgaben-Tabelle generieren (Zeilen = Aufgaben, Spalten = Personen)
// ============================================================================
// Pflichtaufgaben-Tabelle: Zeilen = Personen, Spalten = Aufgaben
// ============================================================================

/**
 * Baut den Link auf die Bewertungsuebersicht einer Aufgabe.
 *
 * `action=grader` oeffnet direkt die Korrekturansicht statt der
 * Aufgaben-Startseite; `group` schraenkt auf die gewaehlte Klasse ein.
 * Welche Abgaben dort gelistet werden, steuert Moodle ueber die
 * Nutzereinstellung `assign_filter` — die laesst sich nicht per URL
 * setzen, sie bleibt auf dem zuletzt gewaehlten Wert stehen.
 *
 * \param {string} url - Basis-URL der Aufgabe (mod/assign/view.php?id=…)
 * \param {string} groupId - Moodle-Gruppen-ID der aktuellen Klasse
 * \returns {string} URL der Bewertungsuebersicht
 */
function bewertungsUrl(url, groupId) {
    if (!url) return '#';
    const trenner = url.includes('?') ? '&' : '?';
    const gruppe = groupId ? `${trenner}group=${groupId}` : '';
    return `${url}${gruppe}${gruppe ? '&' : trenner}action=grader`;
}

/**
 * Entfernt das "Pflicht: "-Praefix aus einem Aufgabentitel. Die Zugehoerigkeit
 * ergibt sich aus dem Tab; in jeder Spalte wiederholt waere es nur Rauschen.
 * \param {string} titel - Aufgabentitel aus Moodle
 * \returns {string} Titel ohne Praefix
 */
function entfernePflichtPraefix(titel) {
    return (titel || '').replace(/^Pflicht:\s*/i, '');
}

/**
 * Zieht die fuehrende Aufgabennummer ("1.2") als sortierbare Zahl aus einem
 * Titel. Ohne Nummerierung bleibt null, dann wird alphabetisch sortiert.
 * \param {string} titel - Aufgabentitel, ggf. mit "Pflicht: "-Praefix
 * \returns {number|null} Sortierzahl (1.2 -> 1.02) oder null
 */
function aufgabenNummer(titel) {
    const treffer = entfernePflichtPraefix(titel).match(/^(\d+)\.(\d+)/);
    if (!treffer) return null;
    return parseInt(treffer[1]) + parseInt(treffer[2]) / 100;
}

/**
 * Sortiert Aktivitaeten nach Aufgabennummer, sonst alphabetisch. Nummerierte
 * Aufgaben stehen vor unnummerierten.
 * \param {Array} aktivitaeten - Aufgaben/Quizzes aus dem Export
 * \returns {Array} Sortierte Kopie
 */
function sortiereAufgaben(aktivitaeten) {
    return [...(aktivitaeten || [])].sort((a, b) => {
        const na = aufgabenNummer(a.title);
        const nb = aufgabenNummer(b.title);
        if (na !== null && nb !== null) return na - nb;
        if (na !== null) return -1;
        if (nb !== null) return 1;
        return entfernePflichtPraefix(a.title)
            .localeCompare(entfernePflichtPraefix(b.title), 'de');
    });
}

/**
 * Maskiert Text fuer die Verwendung in einem HTML-Attribut.
 * \param {string} text - Rohtext
 * \returns {string} Maskierter Text
 */
function escapeAttribut(text) {
    return (text || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '&#10;');
}

/**
 * Maskiert Text fuer die Verwendung im HTML-Inhalt.
 * \param {string} text - Rohtext
 * \returns {string} Maskierter Text
 */
function escapeHtml(text) {
    return (text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

/**
 * Baut die Kopfzelle einer Aufgabenspalte. Der Titel steht ohne
 * "Pflicht: "-Praefix und bricht ueber bis zu drei Zeilen um, damit die
 * Tabelle bei vielen Aufgaben schmal bleibt; der vollstaendige Titel samt
 * Typ und Kategorie steht im Tooltip.
 * \param {Object} aktivitaet - Aufgabe oder Quiz
 * \returns {string} HTML der Kopfzelle
 */
function pflichtSpaltenKopf(aktivitaet) {
    const icon = aktivitaet.activity_type === 'quiz' ? '🧭' : '📝';
    const typ = aktivitaet.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe';
    const kurzTitel = entfernePflichtPraefix(aktivitaet.title);
    const tooltip = escapeAttribut(
        aktivitaet.title + '\n' + 'Typ: ' + typ
        + ' | Kategorie: ' + (aktivitaet.category_name || 'Unbekannt')
    );

    return `<th class="pflicht-task-col" title="${tooltip}"`
         + ` data-activity-type="${aktivitaet.activity_type}">`
         + `<a href="${aktivitaet.url}" target="_blank" class="pflicht-task-title">`
         + `<span class="pflicht-task-icon">${icon}</span>`
         + `<span class="pflicht-task-name">${escapeHtml(kurzTitel)}</span></a></th>`;
}

/**
 * Sucht den Status einer Person zu einer Aktivitaet. Moodle liefert je nach
 * Quelle nur die ID oder nur den Namen, deshalb beide Wege.
 * \param {Object} aktivitaet - Aufgabe oder Quiz
 * \param {string} userId - Moodle-Benutzer-ID
 * \param {string} userName - Anzeigename
 * \returns {Object|null} Statusobjekt oder null
 */
function findeUserStatus(aktivitaet, userId, userName) {
    if (!aktivitaet.user_status) return null;
    return aktivitaet.user_status.find(s =>
        (s.user_id && userId && s.user_id === userId) ||
        (s.user_name && userName && s.user_name === userName)
    ) || null;
}

/**
 * Baut eine Statuszelle der Pflichtaufgaben-Tabelle.
 * \param {Object|null} status - Status der Person zu dieser Aufgabe
 * \param {Object} aktivitaet - Aufgabe oder Quiz
 * \param {string} groupId - Moodle-Gruppen-ID fuer den Bewertungslink
 * \returns {string} HTML der Zelle
 */
function pflichtStatusZelle(status, aktivitaet, groupId) {
    let cellContent = '';
    let bgColor = '';

    if (status && status.grade && status.grade !== '-') {
        cellContent = `<strong>${formatStarGrade(status.grade)}</strong>`;
        bgColor = '--progress-width: 100%; --progress-color: #28a745;';
    } else if (status && status.rating && status.rating !== '-') {
        cellContent = `<strong>${formatStarGrade(status.rating)}</strong>`;
        bgColor = '--progress-width: 100%; --progress-color: #28a745;';
    } else if (status && status.score && status.score !== '-') {
        cellContent = `<strong>${status.score}</strong>`;
        bgColor = '--progress-width: 100%; --progress-color: #28a745;';
    } else if (status && status.status === 'Zur Bewertung abgegeben') {
        // Nur Aufgaben lassen sich direkt bewerten, Quizzes nicht.
        if (aktivitaet.activity_type !== 'quiz' && groupId) {
            cellContent = `<a href="${bewertungsUrl(aktivitaet.url, groupId)}" target="_blank" class="status-text-warning">bewertbar</a>`;
        } else {
            cellContent = '<span class="status-text-warning">bewertbar</span>';
        }
        bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
    } else {
        cellContent = '❌';
        bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
    }

    const zeit = formatSubmissionTime(status?.submission_time);
    if (zeit) {
        cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${zeit}</small>`;
    }

    return `<td class="progress-cell pflicht-task-cell" style="${bgColor} text-align: center;"`
         + ` data-submission-time="${status?.submission_time || ''}"`
         + ` data-activity-type="${aktivitaet.activity_type}">${cellContent}</td>`;
}

function generatePflichtTable() {
    const container = document.getElementById('pflichtData');
    if (!container || !dashboardData) return;

    // Verwende immer die neue activities_by_category Struktur
    if (dashboardData.activities_by_category) {
        generatePflichtTableFromActivities();
    } else if (dashboardData.structured_tables) {
        // Fallback auf alte Struktur
        generatePflichtTableFromStructuredTables();
    } else {
        container.innerHTML = '<p>Keine Daten verfügbar.</p>';
    }
}

function generatePflichtTableFromActivities() {
    const container = document.getElementById('pflichtData');

    // Bei "Alle Gruppen" verwende die spezielle Funktion
    if (currentGroup === 'all') {
        generateAllGroupsPflichtTable();
        return;
    }

    // NEUE LÖSUNG: Verwende dieselbe Logik wie "Alle Gruppen", aber filtere nach Gruppe
    // Das stellt sicher, dass sowohl Assignments als auch Quizzes korrekt einbezogen werden
    generateSingleGroupPflichtTableFromAllData();
    return;

    // Kategorie-Filter anwenden - aber IMMER auch Quizzes aus allen Kategorien einbeziehen
    const categoryFilter = document.getElementById('pflichtCategoryFilter')?.value || 'pflichtaufgaben';
    let categoriesToShow;

    if (categoryFilter === 'pflichtaufgaben') {
        // Für Pflichtaufgaben: Assignments nur aus Pflichtaufgaben-Kategorien, aber Quizzes aus allen
        categoriesToShow = dashboardData.activities_by_category.filter(category =>
            category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
        );


    } else if (categoryFilter === 'all') {
        categoriesToShow = dashboardData.activities_by_category;
    } else {
        const selectedCategoryName = dashboardData.activities_by_category.find(category =>
            category.category_name && category.category_name.toLowerCase().replace(/[^a-z0-9]/g, '') === categoryFilter
        )?.category_name;

        if (selectedCategoryName) {
            categoriesToShow = dashboardData.activities_by_category.filter(category =>
                category.category_name === selectedCategoryName
            );
        } else {
            categoriesToShow = dashboardData.activities_by_category;
        }
    }

    // Sammle sowohl assignments als auch quizzes
    let allActivities = [];

    if (categoryFilter === 'pflichtaufgaben') {
        // Für Pflichtaufgaben-Filter: Assignments nur aus Pflichtaufgaben, aber ALLE Quizzes für Notenberechnung

        // 1. Assignments aus Pflichtaufgaben-Kategorien
        const pflichtCategories = dashboardData.activities_by_category.filter(category =>
            category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
        );

        pflichtCategories.forEach(category => {
            if (category.assignments && category.assignments.length > 0) {
                category.assignments.forEach(assignment => {
                    allActivities.push({
                        ...assignment,
                        activity_type: 'assignment'
                    });
                });
            }
        });

        // 2. Quizzes aus ALLEN Kategorien (für umfassende Notenberechnung)
        dashboardLogger.debug('DATA', 'Searching for quizzes in all categories');
        let totalQuizzesFound = 0;
        dashboardData.activities_by_category.forEach(category => {
            const quizCount = category.quizzes ? category.quizzes.length : 0;
            dashboardLogger.debug('DATA', `Category "${category.category_name}"`, { quizzes: quizCount });
            if (category.quizzes && category.quizzes.length > 0) {
                totalQuizzesFound += category.quizzes.length;
                category.quizzes.forEach(quiz => {
                    allActivities.push({
                        ...quiz,
                        activity_type: 'quiz'
                    });
                });
            }
        });
        dashboardLogger.info('DATA', 'Total quizzes found and added', { total: totalQuizzesFound });

        // ZUSÄTZLICH: Prüfe structured_tables für weitere Quiz-Daten
        if (dashboardData.structured_tables && dashboardData.structured_tables[currentGroup]) {
            dashboardLogger.debug('DEBUG', 'Checking structured_tables for additional quiz data...');
            const structuredData = dashboardData.structured_tables[currentGroup];

            // Prüfe verschiedene mögliche Quiz-Felder in structured_tables
            Object.keys(structuredData).forEach(tableName => {
                if (tableName.toLowerCase().includes('quiz') || tableName.toLowerCase().includes('test')) {
                    console.log(`DEBUG: Found potential quiz table: ${tableName}`);
                    const tableData = structuredData[tableName];
                    if (tableData && tableData.rows) {
                        console.log(`DEBUG: Table ${tableName} has ${tableData.rows.length} rows`);
                        // TODO: Hier könnten wir Quiz-Daten aus structured_tables extrahieren
                    }
                }
            });
        }

    } else {
        // Für andere Filter: normale Logik
        categoriesToShow.forEach(category => {
            // Assignments hinzufügen
            if (category.assignments && category.assignments.length > 0) {
                category.assignments.forEach(assignment => {
                    allActivities.push({
                        ...assignment,
                        activity_type: 'assignment'
                    });
                });
            }
            // Quizzes hinzufügen
            if (category.quizzes && category.quizzes.length > 0) {
                category.quizzes.forEach(quiz => {
                    allActivities.push({
                        ...quiz,
                        activity_type: 'quiz'
                    });
                });
            }
        });
    }

    dashboardLogger.debug('DEBUG', 'Final allActivities count:', allActivities.length);
    dashboardLogger.debug('DEBUG', 'Activity types breakdown:', allActivities.reduce((acc, activity) => {
        acc[activity.activity_type] = (acc[activity.activity_type] || 0) + 1;
        return acc;
    }, {}));

    const assignments = allActivities;

    if (assignments.length === 0) {
        container.innerHTML = '<p>Keine Aktivitäten für die gewählte Kategorie verfügbar.</p>';
        return;
    }

    // Benutzer der aktuellen Gruppe sammeln
    const groupUsers = dashboardData.groups[currentGroup].users;
    const groupId = dashboardData.groups[currentGroup].value; // Get group ID for URL parameters
    dashboardLogger.debug('DEBUG', 'Erste 3 Benutzer der Gruppe:', groupUsers.slice(0, 3));

    // Prüfe verschiedene mögliche Benutzer-Name-Felder
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        // Versuche verschiedene mögliche Felder für den Namen
        const userName = user.user_name || user.name || user.username || user.display_name;
        if (userName) {
            groupUserNames.add(userName);
        }
        dashboardLogger.debug('DEBUG', 'User object:', user, 'extracted name:', userName);
    });

    dashboardLogger.debug('DEBUG', 'Gruppe', currentGroup, 'hat', groupUsers.length, 'Benutzer, extrahierte Namen:', Array.from(groupUserNames));

    // Debug: Prüfe Struktur der Activities
    dashboardLogger.debug('DEBUG', 'Assignments für Gruppe', currentGroup, ':', assignments.length);
    assignments.forEach((assignment, index) => {
        if (index < 3) { // Nur erste 3 zur Debug-Ausgabe
            console.log(`Assignment ${index}:`, {
                title: assignment.title,
                activity_type: assignment.activity_type,
                hasUserStatus: !!assignment.user_status,
                userStatusLength: assignment.user_status ? assignment.user_status.length : 0,
                firstUserStatus: assignment.user_status && assignment.user_status.length > 0 ? assignment.user_status[0] : null,
                groupUserNames: Array.from(groupUserNames)
            });
        }
    });

    // Assignments filtern um nur Benutzer aus der aktuellen Gruppe zu zeigen
    const filteredAssignments = assignments.map(assignment => ({
        ...assignment,
        user_status: assignment.user_status ? assignment.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(assignment => assignment.user_status.length > 0);

    dashboardLogger.debug('DEBUG', 'Nach Filterung:', filteredAssignments.length, 'Aktivitäten übrig');

    if (filteredAssignments.length === 0) {
        container.innerHTML = `<p>Keine Daten für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>
                               <p>Debug: ${assignments.length} Aktivitäten gefunden, aber keine für Benutzer dieser Gruppe.</p>`;
        return;
    }

    let html = '<table id="pflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    // Header für alle Benutzer der Gruppe
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
        const displayName = userName.replace(' ', '<br>'); // Line break after first space
        html += `<th style="text-align: center">${displayName}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Pflichtaufgabe/Quiz
    filteredAssignments.forEach(assignment => {
        html += '<tr>';
        html += `<td style="min-width: 250px;">`;
        const activityIcon = assignment.activity_type === 'quiz' ? '🧭' : '📝';
        const activityType = assignment.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe';
        html += `<a href="${assignment.url}" target="_blank">${activityIcon} ${assignment.title}</a>`;
        html += `<br><small class="status-text-muted">Typ: ${activityType} | Kategorie: ${assignment.category_name || 'Unbekannt'}</small>`;
        html += `</td>`;

        // Status für jeden Benutzer der Gruppe
        groupUsers.forEach(user => {
            let status = null;
            if (assignment.user_status) {
                const userId = user.user_id || user.id;
                const userName = user.user_name || user.name || user.username || user.display_name;

                // Versuche Matching sowohl über user_id als auch user_name
                status = assignment.user_status.find(s =>
                    (s.user_id && userId && s.user_id === userId) ||
                    (s.user_name && userName && s.user_name === userName)
                );
            }

            let cellContent = '';
            let cellClass = 'progress-cell';
            let bgColor = '';

            if (status && status.grade && status.grade !== '-') {
                cellContent = `<strong>${formatStarGrade(status.grade)}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                cellContent = `<strong>${formatStarGrade(status.rating)}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                cellContent = `<strong>${status.score}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.status === 'Zur Bewertung abgegeben') {
                // For assignments (type "Aufgabe"), create hyperlink with group parameter
                // Only create link for non-quiz activities (i.e., assignments)
                if (assignment.activity_type !== 'quiz' && groupId) {
                    cellContent = `<a href="${bewertungsUrl(assignment.url, groupId)}" target="_blank" class="status-text-warning">bewertbar</a>`;
                } else {
                    cellContent = '<span class="status-text-warning">bewertbar</span>';
                }
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                cellContent = '❌';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
            if (submissionTimeFormatted) {
                cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;" data-submission-time="${status?.submission_time || ''}">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';

    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('pflichtTable');

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('pflichtData'), 50);

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculation();

    // Sofortige numerische Sortierung nach Aufgabennummer
    const table = document.getElementById('pflichtTable');
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            // Sortiere Zeilen numerisch nach Aufgabennummer (falls vorhanden), sonst alphabetisch
            rows.sort((a, b) => {
                const aVal = getSortValue(a, 0);
                const bVal = getSortValue(b, 0);

                // Prüfe ob beide Werte numerische Sortierstrings sind (Dezimalzahlen für Aufgabennummern)
                if (aVal.match(/^\d+(\.\d+)?$/) && bVal.match(/^\d+(\.\d+)?$/)) {
                    // Numerischer Vergleich für Aufgabennummern
                    return parseFloat(aVal) - parseFloat(bVal);
                } else {
                    // Alphabetischer Vergleich für andere Werte
                    return aVal.localeCompare(bVal);
                }
            });

            // Zeilen in sortierter Reihenfolge einfügen
            rows.forEach(row => tbody.appendChild(row));

            // Header als sortiert markieren
            const headers = table.querySelectorAll('th');
            if (headers[0]) {
                headers[0].classList.add('sort-asc');
            }

            // Sortierstatus setzen
            sortState['pflichtTable_0'] = 'asc';
        }
    }
}

// Fallback-Implementierung für alte structured_tables Datenstruktur
function generatePflichtTableFromStructuredTables() {
    const container = document.getElementById('pflichtData');
    if (!container || !dashboardData || !dashboardData.structured_tables) return;

    if (currentGroup === 'all') {
        generateAllGroupsPflichtTable();
        return;
    }

    const tableData = dashboardData.structured_tables[currentGroup]?.pflichtaufgaben;

    if (!tableData) {
        container.innerHTML = '<p>Keine Daten für die ausgewählte Gruppe verfügbar.</p>';
        return;
    }

    const groupId = dashboardData.groups[currentGroup]?.value; // Get group ID for URL parameters

    let html = '<table id="pflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    for (let i = 1; i < tableData.headers.length; i++) {
        const userName = tableData.headers[i];
        const displayName = userName.replace(' ', '<br>'); // Line break after first space
        html += `<th style="text-align: center; min-width: 120px;">${displayName}</th>`;
    }
    html += '</tr></thead><tbody>';

    tableData.rows.forEach(row => {
        html += '<tr>';
        const typeIcon = row.assignment_type === 'quiz' ? '🧭' : '📝';
        html += `<td style="min-width: 250px;">`;
        html += `<a href="${row.assignment_url}" target="_blank">${typeIcon} ${row.assignment_title}</a>`;
        html += `<br><small class="status-text-muted">Typ: ${row.assignment_type === 'quiz' ? 'Quiz' : 'Aufgabe'}</small>`;
        html += `</td>`;

        row.user_status.forEach(status => {
            let cellContent = '';
            let cellClass = 'progress-cell';
            let bgColor = '';

            if (status.grade && status.grade != '-') {
                cellContent = `<strong>${formatStarGrade(status.grade)}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status.status === 'Zur Bewertung abgegeben') {
                // For assignments (type "Aufgabe"), create hyperlink with group parameter
                // Only create link for non-quiz activities (i.e., assignments)
                if (row.assignment_type !== 'quiz' && groupId) {
                    cellContent = `<a href="${bewertungsUrl(row.assignment_url, groupId)}" target="_blank" class="status-text-warning">bewertbar</a>`;
                } else {
                    cellContent = '<span class="status-text-warning">bewertbar</span>';
                }
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                cellContent = '❌';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
            if (submissionTimeFormatted) {
                cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;" data-submission-time="${status?.submission_time || ''}">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    makeTableSortable('pflichtTable');

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('pflichtData'), 50);

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculation();
}

// Hilfsfunktion für Pflichtaufgaben-Statistiken
function calculateUserPflichtStats(tableData) {
    const stats = [];

    for (let userIndex = 0; userIndex < tableData.headers.length - 1; userIndex++) {
        const userName = tableData.headers[userIndex + 1];
        let submitted = 0;
        let total = 0;
        const grades = [];

        tableData.rows.forEach(row => {
            total++;
            const status = row.user_status[userIndex];
            if (status.grade && status.grade !== '-') {
                // Hat eine Note - als eingereicht zählen
                submitted++;
                // Versuche Note zu extrahieren
                const gradeStr = status.grade;
                if (gradeStr !== 'Nicht bewertet') {
                    const gradeNum = parseFloat(gradeStr.replace(',', '.'));
                    if (!isNaN(gradeNum) && gradeNum >= 1 && gradeNum <= 6) {
                        grades.push(gradeNum);
                    }
                }
            } else if (status.status === 'Zur Bewertung abgegeben') {
                // Als eingereicht zählen, aber keine Note
                submitted++;
            }
        });

        const avgGrade = grades.length > 0 ? grades.reduce((a, b) => a + b, 0) / grades.length : null;

        stats.push({
            name: userName,
            submitted: submitted,
            total: total,
            avgGrade: avgGrade
        });
    }

    return stats;
}

// Funktionen für "Alle Gruppen" Ansicht
function generateAllGroupsChecklistTable() {
    const container = document.getElementById('checklistData');
    if (!container || !dashboardData || !dashboardData.structured_tables) return;

    // Gruppen basierend auf aktueller Gruppierung filtern
    let groupsToShow = [];
    groupsToShow = Object.keys(dashboardData.structured_tables).filter(groupName => {
        // Überspringe ignorierte Gruppen
        return !(dashboardData.ignored_groups && dashboardData.ignored_groups.includes(groupName));
    });

    // Alle Benutzer aus gefilterten Gruppen sammeln
    let allUsers = [];
    let allChecklists = new Set();

    groupsToShow.forEach(groupName => {
        const tableData = dashboardData.structured_tables[groupName]?.checklists;
        if (tableData) {
            // Checklisten sammeln
            tableData.rows.forEach(row => {
                allChecklists.add(JSON.stringify({
                    id: row.checklist_id,
                    title: row.checklist_title,
                    url: row.checklist_url,
                    category: row.checklist_category,
                    is_mandatory: row.is_mandatory !== undefined ? row.is_mandatory : true
                }));
            });

            // Benutzer sammeln (nur die Namen)
            for (let i = 1; i < tableData.headers.length; i++) {
                const userName = tableData.headers[i];
                if (!allUsers.find(u => u.name === userName)) {
                    allUsers.push({ name: userName, group: groupName });
                }
            }
        }
    });

    // Set zu Array konvertieren und parsen
    const checklistsArray = Array.from(allChecklists).map(str => JSON.parse(str));

    let html = '<table id="allGroupsChecklistTable" class="info-table dashboard-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="checklist-name-cell">Checkliste</th>';

    // Header für alle Benutzer
    allUsers.forEach(user => {
        const displayName = user.name.replace(' ', '<br>'); // Line break after first space
        html += `<th colspan="2" class="text-center">${displayName}<br><small>${user.group}</small></th>`;
    });
    html += '</tr>';

    // Zweite Header-Zeile
    html += '<tr class="sticky-header"><th>Typ</th>';
    allUsers.forEach(() => {
        html += '<th class="sub-header-pflicht">Pflicht</th>';
        html += '<th class="sub-header-gesamt gesamt-column">Gesamt</th>';
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Checkliste
    checklistsArray.forEach(checklist => {
        const isMandatory = checklist.is_mandatory !== undefined ? checklist.is_mandatory : true;

        // Filter "Nur Pflicht": Überspringe optionale Checklisten
        if (checklistViewType === 'pflicht' && !isMandatory) {
            return; // Zeile komplett ausblenden
        }

        html += '<tr>';
        html += `<td class="checklist-name-cell">`;
        html += `<a href="${checklist.url}" target="_blank">${checklist.title}</a>`;
        html += `<br><small class="category-label">${checklist.category}</small>`;
        html += `</td>`;

        // Fortschritt für jeden Benutzer
        allUsers.forEach(user => {
            let progress = { required_progress: '0%', all_progress: '0%' };

            // Finde den Fortschritt in den Gruppendaten
            groupsToShow.forEach(groupName => {
                const tableData = dashboardData.structured_tables[groupName]?.checklists;
                if (tableData) {
                    const userIndex = tableData.headers.indexOf(user.name);
                    if (userIndex > 0) {
                        const row = tableData.rows.find(r => r.checklist_id === checklist.id);
                        if (row && row.user_progress[userIndex - 1]) {
                            progress = row.user_progress[userIndex - 1];
                        }
                    }
                }
            });

            const requiredProgressText = progress.required_progress || '0%';
            const allProgressText = progress.all_progress || '0%';

            const pflichtPercent = parseFloat(requiredProgressText.replace('%', ''));
            const gesamtPercent = parseFloat(allProgressText.replace('%', ''));

            // Pflicht-Fortschritt: Bei nicht-Pflicht Checklisten "-" anzeigen
            let pflichtDisplay = requiredProgressText;
            let pflichtProgressWidth = pflichtPercent;
            if (!isMandatory) {
                pflichtDisplay = '-';
                pflichtProgressWidth = 0;
            }
            html += `<td class="progress-cell" style="--progress-width: ${pflichtProgressWidth}%; class="progress-color-success">${pflichtDisplay}</td>`;
            html += `<td class="progress-cell gesamt-column" style="--progress-width: ${gesamtPercent}%; class="progress-color-secondary">${allProgressText}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsChecklistTable');
    
    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('checklistData'), 50);
}

function generateAllGroupsPflichtTable() {
    const container = document.getElementById('pflichtData');
    if (!container || !dashboardData || !dashboardData.activities_by_category) return;

    // Kategorie-Filter anwenden
    const categoryFilter = document.getElementById('pflichtCategoryFilter')?.value || 'pflichtaufgaben';
    let categoriesToShow;

    if (categoryFilter === 'pflichtaufgaben') {
        // Nur Pflichtaufgaben-Kategorie
        categoriesToShow = dashboardData.activities_by_category.filter(category =>
            category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
        );
    } else if (categoryFilter === 'all') {
        // Alle Kategorien
        categoriesToShow = dashboardData.activities_by_category;
    } else {
        // Spezifische Kategorie - finde sie anhand des Wertes
        const selectedCategoryName = dashboardData.activities_by_category.find(category =>
            category.category_name && category.category_name.toLowerCase().replace(/[^a-z0-9]/g, '') === categoryFilter
        )?.category_name;

        if (selectedCategoryName) {
            categoriesToShow = dashboardData.activities_by_category.filter(category =>
                category.category_name === selectedCategoryName
            );
        } else {
            // Fallback zu Pflichtaufgaben
            categoriesToShow = dashboardData.activities_by_category.filter(category =>
                category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
            );
        }
    }

    // Nutze die gefilterten Kategorien - sowohl assignments als auch quizzes
    let allActivities = [];
    categoriesToShow.forEach(category => {
        // Assignments hinzufügen
        if (category.assignments && category.assignments.length > 0) {
            category.assignments.forEach(assignment => {
                allActivities.push({
                    ...assignment,
                    activity_type: 'assignment'
                });
            });
        }
        // Quizzes hinzufügen
        if (category.quizzes && category.quizzes.length > 0) {
            category.quizzes.forEach(quiz => {
                allActivities.push({
                    ...quiz,
                    activity_type: 'quiz'
                });
            });
        }
    });

    const assignments = allActivities;

    if (assignments.length === 0) return;

    // Bestimme welche Gruppen basierend auf der aktuellen Gruppierung angezeigt werden sollen
    let groupsToShow = [];
    groupsToShow = Object.keys(dashboardData.groups);

    // Sammle alle User-IDs aus den gefilterten Gruppen (für Filterung)
    // Erstelle eine Mapping von Name -> ID aus den Assignments
    const nameToIdMap = new Map();
    assignments.forEach(assignment => {
        if (assignment.user_status) {
            assignment.user_status.forEach(userStatus => {
                nameToIdMap.set(userStatus.user_name, userStatus.user_id);
            });
        }
    });

    const allowedUserIds = new Set();
    groupsToShow.forEach(groupName => {
        const group = dashboardData.groups[groupName];
        if (group && group.users) {
            group.users.forEach(user => {
                const userId = nameToIdMap.get(user.name);
                if (userId) {
                    allowedUserIds.add(userId);
                }
            });
        }
    });

    // Alle Benutzer sammeln (aus den Assignments wie vorher)
    let allUsersSet = new Set();
    assignments.forEach(assignment => {
        if (assignment.user_status) {
            assignment.user_status.forEach(userStatus => {
                // Nur Benutzer hinzufügen, die in den gefilterten Gruppen sind
                if (allowedUserIds.has(userStatus.user_id)) {
                    allUsersSet.add(JSON.stringify({
                        id: userStatus.user_id,
                        name: userStatus.user_name
                    }));
                }
            });
        }
    });
    const allUsers = Array.from(allUsersSet).map(str => JSON.parse(str));

    // Tabelle transponiert: Zeilen = Personen, Spalten = Aufgaben.
    const sortierteAufgaben = sortiereAufgaben(assignments);
    const sortierteUser = [...allUsers].sort((a, b) => compareByVorname(a.name, b.name));

    let html = '<table id="allGroupsPflichtTable" class="info-table dashboard-table pflicht-matrix">';
    html += '<thead><tr><th class="person-name pflicht-person-col">Person</th>';
    sortierteAufgaben.forEach(aktivitaet => {
        html += pflichtSpaltenKopf(aktivitaet);
    });
    html += '</tr></thead><tbody>';

    // Eine Zeile je Person, eine Spalte je Aufgabe. In der Gesamtsicht gibt
    // es keine Gruppen-ID, deshalb fuehrt der Bewertungslink auf group=0.
    sortierteUser.forEach(user => {
        html += '<tr>';
        html += `<td class="person-name pflicht-person-col">${escapeHtml(user.name)}</td>`;

        sortierteAufgaben.forEach(aktivitaet => {
            const status = findeUserStatus(aktivitaet, user.id, user.name);
            html += pflichtStatusZelle(status, aktivitaet, '0');
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsPflichtTable');

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('pflichtData'), 50);

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculationForAllGroups();

    // Standardsortierung: erste Spalte (Person) aufsteigend nach Vorname
    const table = document.getElementById('allGroupsPflichtTable');
    if (table) {
        const headers = table.querySelectorAll('thead th');
        if (headers[0]) headers[0].classList.add('sort-asc');
        sortState['allGroupsPflichtTable_0'] = 'asc';
    }
}

// Filter für Checklisten anwenden
function applyChecklistFilters() {
    generateChecklistTable();
    // Spaltenansicht nach dem Neuaufbau der Tabelle anwenden
    applyChecklistColumnView();
    // View-Filter anwenden
    applyChecklistViewFilter();
}

// View-Filter für Checklisten anwenden
function applyChecklistViewFilter() {
    const viewFilter = document.getElementById('viewFilter');
    if (!viewFilter) return;

    const filterValue = viewFilter.value;
    const table = document.getElementById('checklistTable') || document.getElementById('allGroupsChecklistTable');
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        if (filterValue === 'all') {
            row.style.display = '';
            return;
        }

        // Bestimme welche Spalten berücksichtigt werden sollen
        let progressCells;
        if (checklistViewType === 'pflicht') {
            // Nur Pflicht-Spalten berücksichtigen (ohne gesamt-column Klasse)
            progressCells = row.querySelectorAll('.progress-cell:not(.gesamt-column)');
        } else {
            // Beide Spaltentypen berücksichtigen
            progressCells = row.querySelectorAll('.progress-cell');
        }

        let shouldShow = false;

        progressCells.forEach(cell => {
            const progressText = cell.textContent.trim();
            const progressMatch = progressText.match(/(\d+)%/);

            if (progressMatch) {
                const progressValue = parseInt(progressMatch[1]);

                switch (filterValue) {
                    case '0':
                        if (progressValue === 0) shouldShow = true;
                        break;
                    case '>0':
                        if (progressValue > 0 && progressValue < 100) shouldShow = true;
                        break;
                    case '>80':
                        if (progressValue > 80 && progressValue < 100) shouldShow = true;
                        break;
                    case '100':
                        if (progressValue === 100) shouldShow = true;
                        break;
                }
            }
        });

        row.style.display = shouldShow ? '' : 'none';
    });
}

// Filter für Pflichtaufgaben anwenden
function applyPflichtFilters() {
    // Zeige/Verstecke Custom-Date-Range-Inputs
    const submissionTimeFilter = document.getElementById('pflichtSubmissionTimeFilter');
    const customDateRangeGroup = document.getElementById('customDateRangeGroup');
    const customDateFrom = document.getElementById('customDateFrom');
    const customDateTo = document.getElementById('customDateTo');

    if (submissionTimeFilter && customDateRangeGroup) {
        if (submissionTimeFilter.value === 'custom') {
            customDateRangeGroup.style.display = 'flex';

            // Setze Von-Datum auf gestern, wenn leer
            if (customDateFrom && !customDateFrom.value) {
                const yesterday = new Date();
                yesterday.setDate(yesterday.getDate() - 1);
                const year = yesterday.getFullYear();
                const month = String(yesterday.getMonth() + 1).padStart(2, '0');
                const day = String(yesterday.getDate()).padStart(2, '0');
                customDateFrom.value = `${year}-${month}-${day}`;
            }

            // Setze Bis-Datum auf heute, wenn leer
            if (customDateTo && !customDateTo.value) {
                const today = new Date();
                const year = today.getFullYear();
                const month = String(today.getMonth() + 1).padStart(2, '0');
                const day = String(today.getDate()).padStart(2, '0');
                customDateTo.value = `${year}-${month}-${day}`;
            }
        } else {
            customDateRangeGroup.style.display = 'none';
        }
    }

    generatePflichtTable();
    // Status- und Typ-Filter anwenden
    applyPflichtViewFilters();
}

// Status- und Typ-Filter für Pflichtaufgaben anwenden
/**
 * Prueft, ob ein Abgabezeitpunkt zum gewaehlten Zeitfilter passt.
 * @param {string} submissionTime - ISO-Zeitstempel der Abgabe (ggf. leer)
 * @param {string} filterValue - Wert des Abgabezeitraum-Filters
 * @param {Date} now - Bezugszeitpunkt
 * @returns {boolean} true, wenn die Zelle dem Filter entspricht
 */
function passtZuAbgabezeitraum(submissionTime, filterValue, now) {
    if (filterValue === 'notSubmitted') {
        return !submissionTime;
    }

    if (filterValue === 'custom') {
        const von = document.getElementById('customDateFrom')?.value;
        const bis = document.getElementById('customDateTo')?.value;
        if (!submissionTime || !von || !bis) return false;

        const abgabe = new Date(submissionTime);
        const vonDatum = new Date(von);
        const bisDatum = new Date(bis);
        vonDatum.setHours(0, 0, 0, 0);
        bisDatum.setHours(23, 59, 59, 999);

        return abgabe >= vonDatum && abgabe <= bisDatum;
    }

    if (!submissionTime) return false;

    const schultage = getSchoolDaysDiff(new Date(submissionTime), now);

    switch (filterValue) {
        case 'less1day':   return schultage < 1;
        case 'less2days':  return schultage < 2;
        case 'less3days':  return schultage < 3;
        case 'less4days':  return schultage < 4;
        case 'less5days':  return schultage < 5;
        case 'less1week':  return schultage < 5;
        case 'less2weeks': return schultage < 10;
        default:           return false;
    }
}

/**
 * Status- und Typ-Filter fuer die Pflichtaufgaben-Tabelle. Seit der
 * Transponierung stehen Aufgaben in den Spalten: die Filter blenden deshalb
 * Spalten aus, nicht mehr Zeilen. Personen-Zeilen bleiben immer sichtbar,
 * damit die Klassenliste vollstaendig bleibt.
 */
function applyPflichtViewFilters() {
    const statusFilter = document.getElementById('pflichtStatusFilter');
    const typeFilter = document.getElementById('pflichtTypeFilter');
    const submissionTimeFilter = document.getElementById('pflichtSubmissionTimeFilter');

    if (!statusFilter || !typeFilter) return;

    const statusValue = statusFilter.value;
    const typeValue = typeFilter.value;
    const submissionTimeValue = submissionTimeFilter?.value || 'all';

    const table = document.getElementById('pflichtTable') || document.getElementById('allGroupsPflichtTable');
    if (!table) return;

    const kopfzellen = Array.from(table.querySelectorAll('thead th.pflicht-task-col'));
    const zeilen = Array.from(table.querySelectorAll('tbody tr'));
    const now = new Date();

    // Je Aufgabenspalte entscheiden, ob sie sichtbar bleibt
    kopfzellen.forEach((kopf, spalte) => {
        const zellen = zeilen
            .map(zeile => zeile.querySelectorAll('td.pflicht-task-cell')[spalte])
            .filter(Boolean);

        let sichtbar = true;

        // Typ-Filter: Aufgabe oder Quiz
        if (typeValue !== 'all') {
            sichtbar = kopf.getAttribute('data-activity-type') === typeValue;
        }

        // Status-Filter: mindestens eine Person mit passendem Status
        if (sichtbar && statusValue !== 'all') {
            sichtbar = zellen.some(zelle => {
                const abgegeben = !!zelle.getAttribute('data-submission-time')
                    || extractPercentageFromCell(zelle) !== null;
                return statusValue === 'completed' ? abgegeben : !abgegeben;
            });
        }

        // Abgabezeitraum: mindestens eine Person im gewaehlten Zeitraum
        if (sichtbar && submissionTimeValue !== 'all') {
            sichtbar = zellen.some(zelle => passtZuAbgabezeitraum(
                zelle.getAttribute('data-submission-time'), submissionTimeValue, now
            ));
        }

        kopf.style.display = sichtbar ? '' : 'none';
        zellen.forEach(zelle => {
            zelle.style.display = sichtbar ? '' : 'none';
        });
    });

    // Personen-Zeilen bleiben sichtbar; die Notenspalte rechnet ueber alle
    // Aufgaben, unabhaengig davon welche Spalten gerade eingeblendet sind.
    zeilen.forEach(zeile => {
        zeile.style.display = '';
    });
}

// Details für Checklisten anzeigen
function showChecklistDetails(userName) {
    // Implementierung für Detail-Ansicht
    console.log('Zeige Checklisten-Details für:', userName);
}

// Details für Pflichtaufgaben anzeigen
function showPflichtDetails(userName) {
    // Implementierung für Detail-Ansicht
    console.log('Zeige Pflichtaufgaben-Details für:', userName);
}

// Toggle-Funktion für Checklisten-Spalten
function toggleChecklistColumns() {
    const viewType = document.querySelector('input[name="checklistViewType"]:checked').value;

    // Status speichern
    checklistViewType = viewType;

    // Tabelle komplett neu generieren, damit Zeilen-Filter greifen
    generateChecklistTable();

    // Spaltenansicht anwenden (für Spalten ein-/ausblenden)
    applyChecklistColumnView();

    // View-Filter nach Spaltenänderung erneut anwenden
    applyChecklistViewFilter();
}

// Wendet die aktuelle Spaltenansicht auf die Checklisten-Tabelle an
function applyChecklistColumnView() {
    const gesamtColumns = document.querySelectorAll('.gesamt-column');

    // Labels aktualisieren
    document.querySelectorAll('.progress-toggle label').forEach(label => {
        label.classList.remove('active');
    });

    const activeRadio = document.querySelector(`input[name="checklistViewType"][value="${checklistViewType}"]`);
    if (activeRadio) {
        activeRadio.checked = true;
        const activeLabel = activeRadio.parentElement;
        if (activeLabel) {
            activeLabel.classList.add('active');
        }
    }

    // Spalten ein-/ausblenden
    if (checklistViewType === 'pflicht') {
        // Gesamt-Spalten ausblenden
        gesamtColumns.forEach(column => {
            column.style.display = 'none';
        });

        // Colspan der Benutzer-Header anpassen
        const userHeaders = document.querySelectorAll('th[colspan="2"]');
        userHeaders.forEach(header => {
            header.setAttribute('colspan', '1');
        });
    } else {
        // Alle Spalten anzeigen
        gesamtColumns.forEach(column => {
            column.style.display = '';
        });

        // Colspan der Benutzer-Header zurücksetzen
        const userHeaders = document.querySelectorAll('th[colspan="1"]');
        userHeaders.forEach(header => {
            header.setAttribute('colspan', '2');
        });
    }
}

// Tabellen-Sortierung
function sortTable(tableId, columnIndex, dataType = 'auto') {
    const table = document.getElementById(tableId);
    if (!table) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Aktuellen Sortierstatus ermitteln
    const currentSort = sortState[tableId + '_' + columnIndex] || 'none';
    const newSort = currentSort === 'asc' ? 'desc' : 'asc';

    // Alle Header-Sortierungsklassen zurücksetzen
    table.querySelectorAll('.sortable-header').forEach(header => {
        header.classList.remove('sort-asc', 'sort-desc');
    });

    // Neue Sortierung anwenden
    const headers = table.querySelectorAll('th');
    if (headers[columnIndex]) {
        headers[columnIndex].classList.add('sort-' + newSort);
    }

    // Sortierung durchführen
    rows.sort((a, b) => {
        const aVal = getCellValue(a, columnIndex, dataType);
        const bVal = getCellValue(b, columnIndex, dataType);

        let result = 0;
        if (dataType === 'number' || dataType === 'auto') {
            const aNum = parseFloat(aVal.replace(/[^\d.-]/g, ''));
            const bNum = parseFloat(bVal.replace(/[^\d.-]/g, ''));
            if (!isNaN(aNum) && !isNaN(bNum)) {
                result = aNum - bNum;
            } else {
                result = aVal.localeCompare(bVal);
            }
        } else if (columnIndex === 0 && istPersonenSpalte(table)) {
            // Pflicht-Matrix: Spalte 0 listet Personen, sortiert nach Vorname
            result = compareByVorname(getCellValue(a, 0, 'string'), getCellValue(b, 0, 'string'));
        } else {
            // Für Spalte 0: prüfe ob numerische Sortierstrings vorliegen (Dezimalzahlen für Aufgabennummern)
            if (columnIndex === 0) {
                const aSortVal = getSortValue(a, 0);
                const bSortVal = getSortValue(b, 0);
                if (aSortVal.match(/^\d+(\.\d+)?$/) && bSortVal.match(/^\d+(\.\d+)?$/)) {
                    result = parseFloat(aSortVal) - parseFloat(bSortVal);
                } else {
                    result = aSortVal.localeCompare(bSortVal);
                }
            } else {
                result = aVal.localeCompare(bVal);
            }
        }

        return newSort === 'asc' ? result : -result;
    });

    // Zeilen in neuer Reihenfolge einfügen
    rows.forEach(row => tbody.appendChild(row));

    // Sortierstatus speichern
    sortState[tableId + '_' + columnIndex] = newSort;
}

/**
 * Erkennt Tabellen, deren erste Spalte Personen listet (transponierte
 * Pflicht-Matrix) — dort wird Spalte 0 nach Vorname sortiert.
 * @param {HTMLTableElement} table - Zu pruefende Tabelle
 * @returns {boolean} true bei einer Personen-Matrix
 */
function istPersonenSpalte(table) {
    return !!table && table.classList.contains('pflicht-matrix');
}

function getCellValue(row, columnIndex, dataType) {
    const cell = row.cells[columnIndex];
    if (!cell) return '';

    // Prüfe auf submission_time Attribut (für Sortierung nach Datum)
    const submissionTime = cell.getAttribute('data-submission-time');
    if (submissionTime) {
        // Verwende den ISO-Zeitstempel für Sortierung (leere Strings kommen ans Ende)
        return submissionTime || 'zzzz'; // 'zzzz' sorgt dafür, dass leere Werte ans Ende sortiert werden
    }

    let value = cell.textContent.trim();

    // Spezielle Behandlung für Aufgaben-Titel: Emojis entfernen für die
    // Sortierung. Personennamen bleiben unangetastet — eine Nummer am
    // Namensanfang gibt es nicht, wohl aber Namen mit Sonderzeichen.
    if (columnIndex === 0 && !cell.classList.contains('person-name')) {
        // Entferne alle Emojis vom Anfang für korrekte alphabetische Sortierung
        value = value.replace(/^[📝🧭✅❌⚠️💻🎯]\s*/, '');
        // Entferne auch Numerierung wie "1.1", "1.2" etc. für bessere alphabetische Sortierung
        value = value.replace(/^\d+\.\d+\s*/, '');
        // Entferne "Pflicht:" Prefix
        value = value.replace(/^Pflicht:\s*/, '');
    }

    // Spezielle Behandlung für verschiedene Datentypen
    if (dataType === 'number' || value.match(/^[\d.,%-]+$/)) {
        return value.replace(/[^\d.-]/g, '');
    }

    return value;
}

function getSortValue(row, columnIndex) {
    const cell = row.cells[columnIndex];
    if (!cell) return '';

    let value;

    // Für die erste Spalte: Extrahiere nur den Link-Text, nicht den gesamten Zellinhalt
    if (columnIndex === 0) {
        const link = cell.querySelector('a');
        value = link ? link.textContent.trim() : cell.textContent.trim();

        // Entferne alle Emojis und Leerzeichen vom Anfang
        let cleanValue = value.replace(/^[\u{1F4DD}\u{1F9ED}\u{2705}\u{274C}\u{26A0}\u{1F4BB}\u{1F3AF}\u{FE0F}?\s]*/u, '');
        // Fallback: Entferne alle Non-ASCII Zeichen vom Anfang
        cleanValue = cleanValue.replace(/^[^\x00-\x7F\s]*\s*/, '');

        // Extrahiere Numerierung wie "1.1", "1.2" etc. für numerische Sortierung
        const numberMatch = cleanValue.match(/^(\d+)\.(\d+)/);
        if (numberMatch) {
            // Konvertiere zu einer sortierbaren Zahl: "1.1" -> 1.01, "1.2" -> 1.02, "2.1" -> 2.01, "10.5" -> 10.05
            const major = parseInt(numberMatch[1]);
            const minor = parseInt(numberMatch[2]);
            // Verwende eine einfache Dezimalzahl ohne Padding für numerische Sortierung
            return (major + minor / 100).toString();
        }

        // Falls keine Numerierung gefunden, entferne "Pflicht:" Prefix für alphabetische Sortierung
        return cleanValue.replace(/^Pflicht:\s*/, '');
    } else {
        return cell.textContent.trim();
    }
}

function makeTableSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
        // Überspringe Spalten die nicht sortiert werden sollen
        if (header.classList.contains('no-sort')) return;

        header.classList.add('sortable-header');
        header.onclick = (event) => {
            // Der Aufgabenlink fuehrt nach Moodle — dann nicht zusaetzlich sortieren.
            if (event?.target?.closest?.('a')) return;
            sortTable(tableId, index);
        };
    });
}

// Initial laden beim Start
document.addEventListener('DOMContentLoaded', function() {
    // Der aktive Kurs steht erst fest, wenn der Plan geladen ist —
    // applyDashboardData() waehlt das erste verfuegbare Halbjahr.
    loadData();
});

// Event Listeners für Filter
document.addEventListener('DOMContentLoaded', function() {
    // Progress Type Toggle
    document.querySelectorAll('input[name="progressType"]').forEach(radio => {
        radio.addEventListener('change', toggleProgressType);
    });

    // Alle Gruppen-Dropdowns synchronisieren (excluding the main group selector which is now tabs)
    const groupSelectors = [
        'pflichtGroupFilter'
    ];

    groupSelectors.forEach(selectorId => {
        const selector = document.getElementById(selectorId);
        if (selector) {
            selector.addEventListener('change', function() {
                currentGroup = this.value;
                syncGroupSelectors();
                updateDashboard();
                updateAllTabs();
            });
        }
    });

    // Reference Week Slider
    const weekSlider = document.getElementById('referenceWeekSlider');
    if (weekSlider) {
        weekSlider.addEventListener('input', function(event) {
            console.log('Slider input event:', event.target.value);
            updateReferenceWeek(event.target.value);
        });

        weekSlider.addEventListener('change', function(event) {
            console.log('Slider change event:', event.target.value);
            updateReferenceWeek(event.target.value);
        });
    }
});

// =============  LEISTUNGSNACHWEISE FUNKTIONEN =============

// Leistungsnachweise-Tabelle generieren (Zeilen = Aufgaben, Spalten = Benutzer)
function generateExamTable() {
    const container = document.getElementById('examData');

    // Bei "Alle Gruppen" verwende die spezielle Funktion
    if (currentGroup === 'all') {
        generateAllGroupsExamTable();
        return;
    }

    // Für einzelne Gruppen: Filtere Daten nach Gruppe (gleiche Logik wie generatePflichtTableFromActivities)
    if (!dashboardData.groups || !dashboardData.groups[currentGroup]) {
        container.innerHTML = `<p>Gruppe "${currentGroup}" nicht gefunden.</p>
                               <p>Verfügbare Gruppen: ${Object.keys(dashboardData.groups || {}).join(', ')}</p>`;
        return;
    }

    // Zeige nur "Leistungsnachweise" Kategorien (Kategorie-Filter entfernt)
    const categoriesToShow = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Leistungsnachweise') || category.category_name.includes('📊'))
    );

    // Sammle sowohl assignments als auch quizzes aus den gewählten Kategorien
    let allActivities = [];
    categoriesToShow.forEach(category => {
        // Assignments hinzufügen
        if (category.assignments && category.assignments.length > 0) {
            category.assignments.forEach(assignment => {
                allActivities.push({
                    ...assignment,
                    category_name: category.category_name,
                    activity_type: 'assignment'
                });
            });
        }
        // Quizzes hinzufügen
        if (category.quizzes && category.quizzes.length > 0) {
            category.quizzes.forEach(quiz => {
                allActivities.push({
                    ...quiz,
                    category_name: category.category_name,
                    activity_type: 'quiz'
                });
            });
        }
    });

    // Benutzer der ausgewählten Gruppe (gleiche Logik wie Pflichtaufgaben)
    const groupUsers = dashboardData.groups[currentGroup].users || [];
    const groupId = dashboardData.groups[currentGroup].value; // Get group ID for URL parameters
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
        groupUserNames.add(userName);
    });

    // Aktivitäten filtern um nur Benutzer aus der aktuellen Gruppe zu zeigen
    const filteredActivities = allActivities.map(activity => ({
        ...activity,
        user_status: activity.user_status ? activity.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(activity => activity.user_status.length > 0);

    if (filteredActivities.length === 0) {
        container.innerHTML = `<p>Keine Leistungsnachweise für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>
                               <p>Debug: ${allActivities.length} Aktivitäten gefunden, aber keine für Benutzer dieser Gruppe.</p>`;
        return;
    }

    // Sammle alle einzigartigen Benutzer aus den gefilterten Aktivitäten
    const allUsers = new Set();
    filteredActivities.forEach(activity => {
        if (activity.user_status) {
            activity.user_status.forEach(userStatus => {
                if (userStatus.user_name) {
                    allUsers.add(userStatus.user_name);
                }
            });
        }
    });
    const sortedUsers = Array.from(allUsers).sort(compareByVorname);

    let html = '<table id="examTable" class="info-table dashboard-table">';
    html += '<thead><tr>';

    // Header: Aufgabe + Benutzernamen
    html += '<th style="min-width: 250px;">Aufgabe</th>';

    // Für jeden Benutzer eine Spalte mit Zeilenumbruch bei erstem Leerzeichen
    sortedUsers.forEach(userName => {
        const displayName = userName.replace(' ', '<br>');
        html += `<th class="text-center">${displayName}</th>`;
    });
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jede Aufgabe
    filteredActivities.forEach((activity, activityIndex) => {
        html += '<tr>';

        // Aufgabentitel mit Link
        const typeIcon = activity.activity_type === 'quiz' ? '🧭' : '📝';
        const fullTitle = `${typeIcon} ${activity.title}`;

        html += `<td style="min-width: 250px; font-weight: 500;">`;
        html += `<a href="${activity.url}" target="_blank">${fullTitle}</a>`;
        html += `<br><small>Typ: ${activity.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe'}</small>`;

        // Add "Bewertung überschreiben" link for assignments
        if (activity.activity_type !== 'quiz' && activity.id && courseId) {
            const currentGroupId = (currentGroup !== 'all' && dashboardData.groups[currentGroup]?.value)
                ? dashboardData.groups[currentGroup].value
                : '0';
            const overrideUrl = `https://lernplattform.bycs.de/grade/report/singleview/index.php?id=${courseId}&item=grade&groupsearchvalue=&group=${currentGroupId}&itemid=${activity.id}`;
            html += `<br><small><a href="${overrideUrl}" target="_blank" style="color: #007bff;">Bewertung überschreiben</a></small>`;
        }

        html += `</td>`;

        // Status für jeden Benutzer (gleiche Logik wie generatePflichtTableFromActivities)
        sortedUsers.forEach(userName => {
            const userId = groupUsers.find(user => (user.user_name || user.name || user.username || user.display_name) === userName)?.user_id;

            // Finde den Status für diesen Benutzer (wie in generatePflichtTableFromActivities)
            let status = null;
            if (activity.user_status) {
                status = activity.user_status.find(s =>
                    (s.user_id && userId && s.user_id === userId) ||
                    (s.user_name && userName && s.user_name === userName)
                );
            }

            let cellContent = '';
            let cellClass = '';
            let bgColor = '';

            if (!status) {
                // Kein Status gefunden für diesen Benutzer
                console.log(`DEBUG EXAM: No status found for ${activity.activity_type} "${activity.title}" for user ${userName}`);
                cellContent = '❓ Nicht gefunden';
                cellClass = 'status-not-submitted';
            } else if (status.grade && status.grade !== '-') {
                // WICHTIG: Grade muss VOR Status geprüft werden (z.B. bei Gruppeneinreichungen)
                // Grade vorhanden - zeige Grade-Wert
                console.log(`DEBUG EXAM: Grade found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.grade}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 GRADE SUCCESS: Code-Review 1 grade found for ${userName}: ${status.grade}`);
                }
                cellContent = `${status.grade}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.status === 'Nicht eingereicht' || !status.status) {
                // Nicht eingereicht - zeige "-"
                cellContent = '❌ -';
                cellClass = 'status-not-submitted';
            } else if (status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                console.log(`DEBUG EXAM: Rating found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.rating}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 RATING SUCCESS: Code-Review 1 rating found for ${userName}: ${status.rating}`);
                }
                cellContent = `${status.rating}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                console.log(`DEBUG EXAM: Score found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.score}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 SCORE SUCCESS: Code-Review 1 score found for ${userName}: ${status.score}`);
                }
                cellContent = `${status.score}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.points && status.points !== '-' && status.points !== null) {
                // Alternative: Points field for assignments
                console.log(`DEBUG EXAM: Points found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.points}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 POINTS SUCCESS: Code-Review 1 points found for ${userName}: ${status.points}`);
                }
                cellContent = `${status.points}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.result && status.result !== '-' && status.result !== null) {
                // Alternative: Result field for assignments
                console.log(`DEBUG EXAM: Result found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.result}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 RESULT SUCCESS: Code-Review 1 result found for ${userName}: ${status.result}`);
                }
                cellContent = `${status.result}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.mark && status.mark !== '-' && status.mark !== null) {
                // Alternative: Mark field for assignments
                console.log(`DEBUG EXAM: Mark found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.mark}`);
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🎯 MARK SUCCESS: Code-Review 1 mark found for ${userName}: ${status.mark}`);
                }
                cellContent = `${status.mark}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                // Zur Bewertung abgegeben - zeige "bewertbar" als Link für Aufgaben
                // Only create link for non-quiz activities (i.e., assignments)
                if (activity.activity_type !== 'quiz' && groupId) {
                    const assignmentUrl = activity.url.includes('?')
                        ? `${activity.url}&group=${groupId}`
                        : `${activity.url}?group=${groupId}`;
                    cellContent = `<a href="${assignmentUrl}" target="_blank" class="status-text-warning">bewertbar</a>`;
                } else {
                    cellContent = 'bewertbar';
                }
                cellClass = 'status-gradable'; // Gelb
            } else {
                // Andere Status - Debug ALL possible grade fields
                console.log(`DEBUG EXAM: Other status for ${activity.activity_type} "${activity.title}" for user ${userName}:`, {
                    status: status.status,
                    grade: status.grade,
                    rating: status.rating,
                    score: status.score,
                    points: status.points,
                    result: status.result,
                    mark: status.mark,
                    fullStatus: status
                });

                // Spezielle Debug-Ausgabe für Code-Review 1
                if (activity.title && activity.title.includes('Code-Review 1')) {
                    console.log(`🔍 SPECIAL DEBUG: Code-Review 1 found for user ${userName}:`, {
                        activity_type: activity.activity_type,
                        status_object: status,
                        all_grade_fields: {
                            grade: status.grade,
                            rating: status.rating,
                            score: status.score,
                            points: status.points,
                            result: status.result,
                            mark: status.mark
                        }
                    });
                }

                cellContent = status.status || 'Unbekannt';
                cellClass = 'status-other';
            }

            html += `<td class="${cellClass}">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('examTable');

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('examData'), 50);

    // Filter anwenden falls nötig
    applyExamViewFilters();
}

// Leistungsnachweise für alle Gruppen (Zeilen = Benutzer, Spalten = Leistungsnachweise)
function generateAllGroupsExamTable() {
    const container = document.getElementById('examData');
    if (!container || !dashboardData || !dashboardData.activities_by_category) return;

    // Zeige nur "Leistungsnachweise" Kategorien (Kategorie-Filter entfernt)
    const categoriesToShow = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Leistungsnachweise') || category.category_name.includes('📊'))
    );

    // Sammle sowohl assignments als auch quizzes aus den gewählten Kategorien
    let allActivities = [];
    categoriesToShow.forEach(category => {
        // Assignments hinzufügen
        if (category.assignments && category.assignments.length > 0) {
            category.assignments.forEach(assignment => {
                allActivities.push({
                    ...assignment,
                    category_name: category.category_name,
                    activity_type: 'assignment'
                });
            });
        }
        // Quizzes hinzufügen
        if (category.quizzes && category.quizzes.length > 0) {
            category.quizzes.forEach(quiz => {
                allActivities.push({
                    ...quiz,
                    category_name: category.category_name,
                    activity_type: 'quiz'
                });
            });
        }
    });

    if (allActivities.length === 0) {
        container.innerHTML = '<p>Keine Leistungsnachweise verfügbar.</p>';
        return;
    }

    // Bestimme welche Gruppen basierend auf der aktuellen Gruppierung angezeigt werden sollen
    let groupsToShow = [];
    groupsToShow = Object.keys(dashboardData.groups).filter(groupName => {
        return !(dashboardData.ignored_groups && dashboardData.ignored_groups.includes(groupName));
    });

    // Erstelle eine Mapping von Name -> ID aus den Aktivitäten
    const nameToIdMap = new Map();
    allActivities.forEach(activity => {
        if (activity.user_status) {
            activity.user_status.forEach(userStatus => {
                nameToIdMap.set(userStatus.user_name, userStatus.user_id);
            });
        }
    });

    // Sammle nur Benutzer aus den gefilterten Gruppen
    const allUsers = new Map(); // fullUserKey -> { userName, groupName, userId }
    if (dashboardData.groups) {
        groupsToShow.forEach(groupName => {
            const groupUsers = dashboardData.groups[groupName]?.users || [];
            groupUsers.forEach(user => {
                const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
                const userId = nameToIdMap.get(userName); // Verwende die gemappte ID
                const fullUserKey = `${userName} (${groupName})`;

                if (userId) { // Nur hinzufügen wenn wir eine ID haben
                    allUsers.set(fullUserKey, {
                        userName: userName,
                        groupName: groupName,
                        userId: userId
                    });
                }
            });
        });
    }

    // Sortiere Aktivitäten alphabetisch
    const sortedActivities = allActivities.sort((a, b) => a.title.localeCompare(b.title));

    // Sortiere Users alphabetisch
    const sortedUsers = Array.from(allUsers.values()).sort((a, b) => {
        // Vorname entscheidet; bei gleichem Namen trennt die Klasse.
        const nameCmp = compareByVorname(a.userName, b.userName);
        return nameCmp !== 0 ? nameCmp : compareByVorname(a.groupName, b.groupName);
    });

    let html = '<table id="allGroupsexamTable" class="info-table dashboard-table">';
    html += '<thead><tr>';

    // Header: Benutzer + Gruppe + alle Activities
    html += '<th style="max-width: 100px">Benutzer</th>';
    html += '<th style="min-width: 120px;">Gruppe</th>';

    sortedActivities.forEach(activity => {
        const typeIcon = activity.activity_type === 'quiz' ? '🧭' : '📝';
        const shortTitle = activity.title.length > 12 ?
            activity.title.substring(0, 12) + '...' : activity.title;

        html += `<th style="text-align: center; " title="${typeIcon} ${activity.title}">`;
        html += `<a href="${activity.url}" target="_blank" class="link-light">${typeIcon}<br>${shortTitle}</a>`;

        // Add "Bewertung überschreiben" link for assignments in header
        if (activity.activity_type !== 'quiz' && activity.id && courseId) {
            const overrideUrl = `https://lernplattform.bycs.de/grade/report/singleview/index.php?id=${courseId}&item=grade&groupsearchvalue=&group=0&itemid=${activity.id}`;
            html += `<br><a href="${overrideUrl}" target="_blank" class="link-light" style="font-size: 0.7em;">Überschr.</a>`;
        }

        html += `</th>`;
    });
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jeden Benutzer
    sortedUsers.forEach(user => {
        html += '<tr>';

        // Benutzername mit Zeilenumbruch
        const displayName = user.userName.replace(' ', '<br>');
        html += `<td style="font-weight: 500;">${displayName}</td>`;

        // Gruppenname
        html += `<td >${user.groupName}</td>`;

        // Status für jede Activity (gleiche Logik wie einzelne Gruppen)
        sortedActivities.forEach(activity => {
            // Finde den Status für diesen Benutzer (gleiche Logik wie generateExamTable)
            let status = null;
            if (activity.user_status) {
                status = activity.user_status.find(s =>
                    (s.user_id && user.userId && s.user_id === user.userId) ||
                    (s.user_name && user.userName && s.user_name === user.userName)
                );
            }

            let cellContent = '';
            let cellClass = '';
            let bgColor = '';

            if (!status) {
                // Kein Status gefunden für diesen Benutzer
                cellContent = '-';
                cellClass = 'status-not-submitted';
            } else if (status.status === 'Nicht eingereicht' || !status.status) {
                cellContent = '❌';
                cellClass = 'status-not-submitted';
            } else if (status.grade && status.grade !== '-') {
                console.log(`DEBUG EXAM ALL: Grade found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.grade}`);
                cellContent = `${status.grade}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                console.log(`DEBUG EXAM ALL: Rating found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.rating}`);
                cellContent = `${status.rating}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                console.log(`DEBUG EXAM ALL: Score found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.score}`);
                cellContent = `${status.score}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.points && status.points !== '-' && status.points !== null) {
                // Alternative: Points field for assignments
                console.log(`DEBUG EXAM ALL: Points found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.points}`);
                cellContent = `${status.points}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.result && status.result !== '-' && status.result !== null) {
                // Alternative: Result field for assignments
                console.log(`DEBUG EXAM ALL: Result found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.result}`);
                cellContent = `${status.result}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.mark && status.mark !== '-' && status.mark !== null) {
                // Alternative: Mark field for assignments
                console.log(`DEBUG EXAM ALL: Mark found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.mark}`);
                cellContent = `${status.mark}`;
                const submissionTimeFormatted = formatSubmissionTime(status?.submission_time);
                if (submissionTimeFormatted) {
                    cellContent += `<br><small class="status-text-muted" style="font-size: 0.75em;">${submissionTimeFormatted}</small>`;
                }
                cellClass = 'status-graded';
            } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                // For "all groups" view, use group=0
                if (activity.activity_type !== 'quiz') {
                    const assignmentUrl = activity.url.includes('?')
                        ? `${activity.url}&group=0`
                        : `${activity.url}?group=0`;
                    cellContent = `<a href="${assignmentUrl}" target="_blank" class="status-text-warning" style="font-size: 0.8em;">bewertbar</a>`;
                } else {
                    cellContent = '<span style="font-size: 0.8em;">bewertbar</span>';
                }
                cellClass = 'status-gradable'; // Gelb
            } else {
                cellContent = '?';
                cellClass = 'status-other';
            }

            html += `<td class="${cellClass} text-small">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsexamTable');

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('examData'), 50);

    // Filter anweExam();
}

// Filter für  Leistungsnachweise anwenden
function applyExamFilters() {
    generateExamTable();
    // Status- und Typ-Filter anwenden
    funExam();
}

// Status- und Typ-Filter für Leistungsnachweise anwenden
function funExam() {
    const statusFilter = document.getElementById('examStatusFilter');
    const typeFilter = document.getElementById('examTypeFilter');

    if (!statusFilter || !typeFilter) return;

    const statusValue = statusFilter.value;
    const typeValue = typeFilter.value;

    const table = document.getElementById('examTable') || document.getElementById('allGroupsexamTable');
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        let shouldShow = true;

        // Status-Filter anwenden
        if (statusValue !== 'all') {
            // Suche nach bewerteten Zellen in der Zeile
            const gradedCells = row.querySelectorAll('.status-graded');
            const submittedCells = row.querySelectorAll('.status-submitted');
            const missingCells = row.querySelectorAll('.status-missing');

            const hasGrades = gradedCells.length > 0;
            const hasSubmissions = submittedCells.length > 0;

            if (statusValue === 'completed' && !hasGrades) {
                shouldShow = false;
            } else if (statusValue === 'pending' && hasGrades && !hasSubmissions) {
                shouldShow = false;
            }
        }

        // Typ-Filter anwenden
        if (typeValue !== 'all') {
            const typeElement = row.querySelector('small');
            if (typeElement) {
                const typeText = typeElement.textContent.toLowerCase();
                if (typeValue === 'quiz' && !typeText.includes('quiz')) {
                    shouldShow = false;
                } else if (typeValue === 'assignment' && !typeText.includes('aufgabe')) {
                    shouldShow = false;
                }
            }
        }

        row.style.display = shouldShow ? '' : 'none';
    });
}

// Notenberechnung für Pflichtaufgaben hinzufügen
/**
 * Haengt die Durchschnittsnote als eigene Spalte an die Pflichtaufgaben-
 * Tabelle. Seit der Transponierung steht je Person eine Zeile, die Note
 * gehoert deshalb ans Zeilenende und nicht mehr in eine Kopfzeile.
 * @param {string} [tableId='pflichtTable'] - ID der Tabelle
 */
function addPflichtaufgabenGradeCalculation(tableId = 'pflichtTable') {
    const table = document.getElementById(tableId);
    if (!table) return;

    // Vorhandene Notenspalte entfernen, damit ein Neuaufbau nicht doppelt
    table.querySelectorAll('.pflicht-grade-cell').forEach(cell => cell.remove());

    const headerRow = table.querySelector('thead tr');
    if (!headerRow) return;

    const kopf = document.createElement('th');
    kopf.className = 'pflicht-grade-cell pflicht-grade-col';
    kopf.textContent = '📊 Ø Note';
    kopf.title = 'Durchschnitt der bewerteten Pflichtaufgaben dieser Person';
    headerRow.appendChild(kopf);

    // Je Zeile (= Person) die Note aus den Aufgabenzellen dieser Zeile
    table.querySelectorAll('tbody tr').forEach(row => {
        const zelle = document.createElement('td');
        zelle.className = 'pflicht-grade-cell pflicht-grade-col text-bold';

        const note = berechnePflichtnoteFuerZeile(row);

        if (note !== null && note.grade !== null) {
            zelle.textContent = `${note.grade.toFixed(0)} (${note.percent.toFixed(0)}%, N=${note.count})`;
            zelle.style.color = getGradeColor(note.grade);
            zelle.title = `Durchschnitt: ${note.percent.toFixed(1)}% aus ${note.count} bewerteten Aufgaben`;
        } else {
            zelle.textContent = 'n/a';
            zelle.style.color = '#6c757d';
            zelle.title = 'Keine bewerteten Aufgaben vorhanden';
        }

        row.appendChild(zelle);
    });
}

/**
 * Berechnet die Durchschnittsnote einer Person aus ihrer Tabellenzeile.
 * Gemittelt werden die Prozentwerte; erst der Durchschnitt wird in eine
 * IHK-Note umgesetzt.
 * @param {HTMLTableRowElement} row - Zeile der Person
 * @returns {Object|null} {grade, percent, count} oder null
 */
function berechnePflichtnoteFuerZeile(row) {
    const zellen = row.querySelectorAll('td.pflicht-task-cell');
    let totalPercent = 0;
    let count = 0;

    zellen.forEach(zelle => {
        const percent = extractPercentageFromCell(zelle);
        if (percent !== null) {
            totalPercent += percent;
            count++;
        }
    });

    if (count === 0) return null;

    const averagePercent = totalPercent / count;

    return {
        grade: convertPercentToIHKGrade(averagePercent),
        percent: averagePercent,
        count: count
    };
}

// Berechne Pflichtaufgaben-Durchschnittsnote für eine ganze Gruppe
function calculatePflichtaufgabenGradeForGroup(groupName) {
    if (!dashboardData || !dashboardData.groups || !dashboardData.groups[groupName]) {
        return null;
    }

    const groupData = dashboardData.groups[groupName];
    const users = groupData.users || [];

    if (users.length === 0) return null;

    let totalPercent = 0;
    let totalCount = 0;

    // Berechne Note für jeden Benutzer und sammle die Prozentwerte
    users.forEach(user => {
        const userGrade = calculatePflichtaufgabenGradeForUserByName(user.name, groupName);
        if (userGrade && userGrade.percent !== null) {
            totalPercent += userGrade.percent;
            totalCount++;
        }
    });

    if (totalCount === 0) return null;

    // Durchschnitt aller Benutzer-Prozentwerte
    const averagePercent = totalPercent / totalCount;

    // In IHK-Note umwandeln
    const grade = convertPercentToIHKGrade(averagePercent);

    return {
        grade: grade,
        percent: averagePercent,
        count: totalCount // Anzahl der Benutzer mit Bewertungen
    };
}

// Berechne Pflichtaufgaben-Durchschnittsnote für einen Benutzer basierend auf activities_by_category
function calculatePflichtaufgabenGradeForUserByName(userName, groupName) {
    if (!dashboardData || !dashboardData.activities_by_category) {
        return null;
    }

    let totalPercent = 0;
    let count = 0; // Expliziter Zähler

    console.log(`\n========== Calculating Pflichtaufgaben grade for ${userName} ==========`);

    // Finde Pflichtaufgaben-Kategorie(n)
    const pflichtCategories = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
    );

    console.log(`Found ${pflichtCategories.length} Pflichtaufgaben categories`);

    // Durchlaufe alle Pflichtaufgaben-Kategorien
    pflichtCategories.forEach(category => {
        console.log(`Processing category: ${category.category_name}`);

        // Prüfe Assignments
        if (category.assignments) {
            console.log(`  Checking ${category.assignments.length} assignments`);
            category.assignments.forEach(assignment => {
                if (assignment.user_status) {
                    const userStatus = assignment.user_status.find(status => status.user_name === userName);
                    if (userStatus && userStatus.grade) {
                        console.log(`  Assignment "${assignment.name}": grade = "${userStatus.grade}"`);
                        const percent = extractPercentageFromString(userStatus.grade);
                        console.log(`    -> Extracted percentage: ${percent}`);
                        if (percent !== null) {
                            totalPercent += percent;
                            count++; // Zähle jede gefundene Bewertung
                        }
                    }
                }
            });
        }

        // Prüfe Quizzes
        if (category.quizzes) {
            console.log(`  Checking ${category.quizzes.length} quizzes`);
            category.quizzes.forEach(quiz => {
                if (quiz.user_status) {
                    const userStatus = quiz.user_status.find(status => status.user_name === userName);
                    if (userStatus && userStatus.grade) {
                        console.log(`  Quiz "${quiz.name}": grade = "${userStatus.grade}"`);
                        const percent = extractPercentageFromString(userStatus.grade);
                        console.log(`    -> Extracted percentage: ${percent}`);
                        if (percent !== null) {
                            totalPercent += percent;
                            count++; // Zähle jede gefundene Bewertung
                        }
                    }
                }
            });
        }
    });

    if (count === 0) return null;

    // Durchschnitt der Prozentwerte berechnen
    const averagePercent = totalPercent / count;
    console.log(`DEBUG: Average percentage for ${userName}: ${averagePercent}%`);

    // Erst jetzt in IHK-Note umwandeln
    const grade = convertPercentToIHKGrade(averagePercent);

    return {
        grade: grade,
        percent: averagePercent,
        count: count
    };
}

// Extrahiere Prozentwert aus einem String (ohne Umwandlung in Note!)
function extractPercentageFromString(gradeString) {
    if (!gradeString || gradeString === '-' || gradeString === 'Nicht eingereicht') return null;

    const content = String(gradeString).trim();

    // Prüfe auf Sterne-Bewertungen basierend auf GradeMapping
    if (content.includes('*')) {
        console.log(`DEBUG extractPercentageFromString: Found stars in "${content}"`);
        console.log(`DEBUG: gradeMapping keys:`, Object.keys(gradeMapping));

        // Konvertiere Sterne zu Prozentwert über GradeMapping
        const mappingEntries = Object.entries(gradeMapping)
            .map(([score, label]) => ({ score: parseInt(score), label: label }))
            .sort((a, b) => b.score - a.score);

        console.log(`DEBUG: mappingEntries:`, mappingEntries);

        for (const entry of mappingEntries) {
            console.log(`DEBUG: Checking if "${content}" includes "${entry.label}"`);
            if (content.includes(entry.label)) {
                console.log(`DEBUG: ✓ MATCH! Returning score ${entry.score}% for "${entry.label}"`);
                return entry.score; // Gib den Score direkt als Prozentwert zurück (z.B. 70%, 100%, 130%)
            }
        }

        // Fallback: Zähle Sterne
        console.log(`DEBUG: No label match found, counting stars...`);
        const starCount = (content.match(/\*/g) || []).length;
        console.log(`DEBUG: Star count = ${starCount}`);
        if (mappingEntries.length > 0 && starCount >= 1) {
            const sortedByStars = mappingEntries.sort((a, b) => b.score - a.score);
            const index = Math.max(0, Math.min(starCount - 1, sortedByStars.length - 1));
            if (starCount <= sortedByStars.length) {
                const result = sortedByStars[sortedByStars.length - starCount].score;
                console.log(`DEBUG: Returning ${result}% based on ${starCount} stars`);
                return result;
            }
        }
        console.log(`DEBUG: ✗ Could not extract percentage from star rating`);
    }

    // Prüfe auf direkte Prozentwerte
    const percentMatch = content.match(/(\d+(?:\.\d+)?)%/);
    if (percentMatch) {
        return parseFloat(percentMatch[1]);
    }

    // Prüfe auf direkte Zahlenwerte
    const gradeMatch = content.match(/^(\d+(?:[.,]\d+)?)$/);
    if (gradeMatch) {
        const value = parseFloat(gradeMatch[1].replace(',', '.'));

        // Zahlen > 6 als Prozentwerte interpretieren
        if (value > 6 && value <= 100) {
            return value;
        }

        // Noten zwischen 1.0 und 6.0 nicht unterstützt - wir brauchen Prozentwerte
        if (value >= 1.0 && value <= 6.0) {
            return null; // Kann nicht in Prozent umgewandelt werden
        }
    }

    // Prüfe auf Punktzahlen (z.B. "8/10" oder "70 / 100")
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
    if (pointsMatch) {
        const achieved = parseFloat(pointsMatch[1]);
        const total = parseFloat(pointsMatch[2]);
        if (total > 0) {
            return (achieved / total) * 100;
        }
    }

    return null;
}

// Extrahiere Note aus einem String (ähnlich wie extractGradeFromCell, aber für reinen Text)
function extractGradeFromString(gradeString) {
    if (!gradeString || gradeString === '-' || gradeString === 'Nicht eingereicht') return null;

    const content = String(gradeString).trim();

    // Prüfe auf Sterne-Bewertungen
    if (content.includes('*')) {
        return convertStarRatingToGrade(content);
    }

    // Prüfe auf Prozentwerte
    const percentMatch = content.match(/(\d+(?:\.\d+)?)%/);
    if (percentMatch) {
        const percent = parseFloat(percentMatch[1]);
        return convertPercentToIHKGrade(percent);
    }

    // Prüfe auf direkte Notenwerte
    const gradeMatch = content.match(/^(\d+(?:[.,]\d+)?)$/);
    if (gradeMatch) {
        const value = parseFloat(gradeMatch[1].replace(',', '.'));

        // Noten zwischen 1.0 und 6.0
        if (value >= 1.0 && value <= 6.0) {
            return value;
        }

        // Zahlen > 6 als Prozentwerte interpretieren
        if (value > 6 && value <= 100) {
            return convertPercentToIHKGrade(value);
        }
    }

    // Prüfe auf Punktzahlen (z.B. "8/10" oder "70 / 100")
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
    if (pointsMatch) {
        const achieved = parseFloat(pointsMatch[1]);
        const total = parseFloat(pointsMatch[2]);
        if (total > 0) {
            const percent = (achieved / total) * 100;
            return convertPercentToIHKGrade(percent);
        }
    }

    return null;
}

// Extrahiere Prozentwert aus einer Tabellenzelle (für korrekte Notenberechnung)
function extractPercentageFromCell(cell) {
    const content = cell.textContent.trim();
    const innerHTML = cell.innerHTML.trim();

    // Prüfe auf Sterne-Bewertungen basierend auf GradeMapping
    if (content.includes('*')) {
        // Konvertiere Sterne zu Prozentwert über GradeMapping
        const mappingEntries = Object.entries(gradeMapping)
            .map(([score, label]) => ({ score: parseInt(score), label: label }))
            .sort((a, b) => b.score - a.score);

        for (const entry of mappingEntries) {
            if (content.includes(entry.label)) {
                return entry.score; // z.B. 70 für "** Verbesserungsbedarf"
            }
        }

        // Fallback: Zähle Sterne
        const starCount = (content.match(/\*/g) || []).length;
        if (mappingEntries.length > 0 && starCount >= 1 && starCount <= mappingEntries.length) {
            const sortedByStars = mappingEntries.sort((a, b) => b.score - a.score);
            return sortedByStars[sortedByStars.length - starCount].score;
        }
    }

    // Prüfe auf Prozentwerte in <strong> Tags
    const strongMatch = innerHTML.match(/<strong>([^<]+)<\/strong>/);
    if (strongMatch) {
        const gradeText = strongMatch[1].trim();

        // Prüfe auf Prozentwerte
        const percentMatch = gradeText.match(/(\d+(?:\.\d+)?)%/);
        if (percentMatch) {
            return parseFloat(percentMatch[1]);
        }

        // Prüfe auf direkte Zahlenwerte
        const gradeMatch = gradeText.match(/^(\d+(?:[.,]\d+)?)$/);
        if (gradeMatch) {
            const value = parseFloat(gradeMatch[1].replace(',', '.'));

            // Zahlen > 6 als Prozentwerte interpretieren
            if (value > 6 && value <= 100) {
                return value;
            }
        }

        // Prüfe auf Quiz-Punktzahlen (z.B. "8/10")
        const pointsMatch = gradeText.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
        if (pointsMatch) {
            const achieved = parseFloat(pointsMatch[1]);
            const total = parseFloat(pointsMatch[2]);
            if (total > 0) {
                return (achieved / total) * 100;
            }
        }
    }

    // Prüfe auf Prozentwerte im normalen Text
    const percentMatch = content.match(/(\d+(?:\.\d+)?)%/);
    if (percentMatch) {
        return parseFloat(percentMatch[1]);
    }

    // Prüfe auf Quiz-Ergebnisse mit Punktzahl (z.B. "8/10 (80%)")
    const quizMatch = content.match(/\d+\/\d+\s*\((\d+(?:\.\d+)?)%\)/);
    if (quizMatch) {
        return parseFloat(quizMatch[1]);
    }

    // Prüfe auf einfache Punktzahlen ohne Prozent
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
    if (pointsMatch) {
        const achieved = parseFloat(pointsMatch[1]);
        const total = parseFloat(pointsMatch[2]);
        if (total > 0) {
            return (achieved / total) * 100;
        }
    }

    return null;
}

// Extrahiere Note aus einer Tabellenzelle (nur tatsächlich bewertete Aufgaben)
function extractGradeFromCell(cell) {
    const content = cell.textContent.trim();
    const innerHTML = cell.innerHTML.trim();

    // Prüfe auf Sterne-Bewertungen basierend auf GradeMapping aus config.ini
    if (content.includes('*')) {
        return convertStarRatingToGrade(content);
    }

    // Prüfe auf direkte Notenwerte in <strong> Tags (z.B. Assignment-Noten und Quiz-Ergebnisse)
    const strongMatch = innerHTML.match(/<strong>([^<]+)<\/strong>/);
    if (strongMatch) {
        const gradeText = strongMatch[1].trim();

        // Prüfe auf Prozentwerte
        const percentMatch = gradeText.match(/(\d+(?:\.\d+)?)%/);
        if (percentMatch) {
            const percent = parseFloat(percentMatch[1]);
            return convertPercentToIHKGrade(percent);
        }

        // Prüfe auf direkte Notenwerte oder Prozentwerte ohne % Zeichen
        const gradeMatch = gradeText.match(/^(\d+(?:[.,]\d+)?)$/);
        if (gradeMatch) {
            const value = parseFloat(gradeMatch[1].replace(',', '.'));

            // Noten zwischen 1.0 und 6.0
            if (value >= 1.0 && value <= 6.0) {
                return value;
            }

            // Zahlen > 6 als Prozentwerte interpretieren (Quiz-Ergebnisse ohne % Zeichen)
            if (value > 6 && value <= 100) {
                return convertPercentToIHKGrade(value);
            }
        }

        // Prüfe auf Quiz-Punktzahlen in strong tags (z.B. "8/10")
        const pointsMatch = gradeText.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
        if (pointsMatch) {
            const achieved = parseFloat(pointsMatch[1]);
            const total = parseFloat(pointsMatch[2]);
            if (total > 0) {
                const percent = (achieved / total) * 100;
                return convertPercentToIHKGrade(percent);
            }
        }
    }

    // Prüfe auf Prozentwerte (sowohl für Assignments als auch Quizzes)
    const percentMatch = content.match(/(\d+(?:\.\d+)?)%/);
    if (percentMatch) {
        const percent = parseFloat(percentMatch[1]);
        return convertPercentToIHKGrade(percent);
    }

    // Prüfe auf Quiz-Ergebnisse mit Punktzahl (z.B. "8/10 (80%)")
    const quizMatch = content.match(/\d+\/\d+\s*\((\d+(?:\.\d+)?)%\)/);
    if (quizMatch) {
        const percent = parseFloat(quizMatch[1]);
        return convertPercentToIHKGrade(percent);
    }

    // Prüfe auf Punktzahl ohne Prozentwert (z.B. "8/10")
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
    if (pointsMatch) {
        const achieved = parseFloat(pointsMatch[1]);
        const total = parseFloat(pointsMatch[2]);
        if (total > 0) {
            const percent = (achieved / total) * 100;
            return convertPercentToIHKGrade(percent);
        }
    }

    // Prüfe auf direkte Notenwerte (z.B. "2,5" oder "1.0")
    const gradeMatch = content.match(/^(\d+(?:[.,]\d+)?)$/);
    if (gradeMatch) {
        const grade = parseFloat(gradeMatch[1].replace(',', '.'));
        if (grade >= 1.0 && grade <= 6.0) {
            return grade;
        }
    }

    // Für alle anderen Fälle (nicht eingereicht, zur Bewertung abgegeben, etc.)
    // wird KEINE Note zurückgegeben - diese Aufgaben fließen nicht in die Berechnung ein
    return null;
}

// Konvertiere Sterne-Bewertung zu Note basierend auf config.ini GradeMapping
function convertStarRatingToGrade(starRating) {
    // Use dynamic grade mapping from config.ini
    // Convert mapping to array and sort by score descending
    const mappingEntries = Object.entries(gradeMapping)
        .map(([score, label]) => ({ score: parseInt(score), label: label }))
        .sort((a, b) => b.score - a.score);

    // Try to match star rating with mapping entries
    for (const entry of mappingEntries) {
        if (starRating.includes(entry.label)) {
            return convertPercentToIHKGrade(entry.score);
        }
    }

    // Fallback: count stars if no text match found
    const starCount = (starRating.match(/\*/g) || []).length;

    // Map star count to the highest matching score
    // 4 stars = highest, 3 = second highest, etc.
    if (mappingEntries.length > 0) {
        const sortedByStars = mappingEntries.sort((a, b) => b.score - a.score);
        const index = Math.max(0, Math.min(starCount - 1, sortedByStars.length - 1));
        if (starCount >= 1 && starCount <= sortedByStars.length) {
            return convertPercentToIHKGrade(sortedByStars[sortedByStars.length - starCount].score);
        }
    }

    return null;
}

// Konvertiere Prozentwert zu IHK-Note
function convertPercentToIHKGrade(percent) {
    if (percent >= 92) return 1.0;
    if (percent >= 81) return 2.0;
    if (percent >= 67) return 3.0;
    if (percent >= 50) return 4.0;
    if (percent >= 30) return 5.0;
    return 6.0;
}

// Bestimme Farbe basierend auf Note
function getGradeColor(grade) {
    if (grade <= 2.0) return '#28a745'; // Grün für sehr gut/gut
    if (grade <= 3.0) return '#ffc107'; // Gelb für befriedigend
    if (grade <= 4.0) return '#fd7e14'; // Orange für ausreichend
    return '#dc3545'; // Rot für mangelhaft/ungenügend
}

// Notenberechnung für Pflichtaufgaben hinzufügen (für Alle Gruppen Ansicht)
/**
 * Notenspalte fuer die Gesamtsicht ueber alle Klassen. Die Rechnung ist
 * dieselbe wie bei einer einzelnen Klasse, nur die Tabelle ist eine andere.
 */
function addPflichtaufgabenGradeCalculationForAllGroups() {
    addPflichtaufgabenGradeCalculation('allGroupsPflichtTable');
}

// Neue Funktion für Einzelgruppen basierend auf der bewährten "Alle Gruppen" Logik
function generateSingleGroupPflichtTableFromAllData() {
    const container = document.getElementById('pflichtData');
    if (!container || !dashboardData || !dashboardData.activities_by_category) return;

    // Kategorie-Filter anwenden (gleiche Logik wie "Alle Gruppen")
    const categoryFilter = document.getElementById('pflichtCategoryFilter')?.value || 'pflichtaufgaben';
    let categoriesToShow;

    if (categoryFilter === 'pflichtaufgaben') {
        categoriesToShow = dashboardData.activities_by_category.filter(category =>
            category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
        );
    } else if (categoryFilter === 'all') {
        categoriesToShow = dashboardData.activities_by_category;
    } else {
        const selectedCategoryName = dashboardData.activities_by_category.find(category =>
            category.category_name && category.category_name.toLowerCase().replace(/[^a-z0-9]/g, '') === categoryFilter
        )?.category_name;

        if (selectedCategoryName) {
            categoriesToShow = dashboardData.activities_by_category.filter(category =>
                category.category_name === selectedCategoryName
            );
        } else {
            categoriesToShow = dashboardData.activities_by_category.filter(category =>
                category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
            );
        }
    }

    // Sammle alle Aktivitäten (wie in "Alle Gruppen")
    let allActivities = [];
    dashboardLogger.debug('DEBUG', 'New function - collecting activities...');
    dashboardLogger.debug('DEBUG', 'Categories to show:', categoriesToShow.length);

    categoriesToShow.forEach(category => {
        console.log(`DEBUG: Category "${category.category_name}" - assignments: ${category.assignments?.length || 0}, quizzes: ${category.quizzes?.length || 0}`);

        // Assignments hinzufügen
        if (category.assignments && category.assignments.length > 0) {
            category.assignments.forEach(assignment => {
                allActivities.push({
                    ...assignment,
                    activity_type: 'assignment'
                });
            });
        }
        // Quizzes hinzufügen
        if (category.quizzes && category.quizzes.length > 0) {
            console.log(`DEBUG: Adding ${category.quizzes.length} quizzes from category ${category.category_name}`);
            category.quizzes.forEach(quiz => {
                allActivities.push({
                    ...quiz,
                    activity_type: 'quiz'
                });
            });
        }
    });

    dashboardLogger.debug('DEBUG', 'Total activities collected:', allActivities.length);
    dashboardLogger.debug('DEBUG', 'Activity types:', allActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

    // ZUSÄTZLICH: Versuche Quiz-Daten aus anderen Quellen zu extrahieren
    if (dashboardData.structured_tables && dashboardData.structured_tables[currentGroup]) {
        dashboardLogger.debug('DEBUG', 'Searching for quiz data in structured_tables...');
        const structuredData = dashboardData.structured_tables[currentGroup];

        // Durchsuche alle Tabellen nach Quiz-ähnlichen Daten
        Object.keys(structuredData).forEach(tableName => {
            console.log(`DEBUG: Checking table: ${tableName}`);
            if (tableName.toLowerCase().includes('quiz') || tableName.toLowerCase().includes('test')) {
                console.log(`DEBUG: Found potential quiz table: ${tableName}`);
                const tableData = structuredData[tableName];
                if (tableData && tableData.rows) {
                    console.log(`DEBUG: Table ${tableName} has ${tableData.rows.length} rows`);
                    // Konvertiere structured_table Quiz-Daten zu activity Format
                    tableData.rows.forEach(row => {
                        const fakeQuizActivity = {
                            title: row.activity_name || row.name || `Quiz aus ${tableName}`,
                            activity_type: 'quiz',
                            url: row.activity_url || '#',
                            category_name: tableName,
                            user_status: []
                        };

                        // Konvertiere Benutzer-Progress-Daten
                        if (row.user_progress) {
                            row.user_progress.forEach(progress => {
                                // Finde Benutzer-Info in dashboardData.groups
                                const groupUsers = dashboardData.groups[currentGroup].users;
                                const userInfo = groupUsers.find(user =>
                                    (user.user_name || user.name) === progress.user_name ||
                                    (user.user_id || user.id) === progress.user_id
                                );

                                if (userInfo && progress.required_progress && progress.required_progress !== '0%') {
                                    fakeQuizActivity.user_status.push({
                                        user_name: progress.user_name,
                                        user_id: progress.user_id,
                                        grade: progress.required_progress, // z.B. "91%"
                                        status: 'Completed'
                                    });
                                }
                            });
                        }

                        if (fakeQuizActivity.user_status.length > 0) {
                            console.log(`DEBUG: Adding quiz from structured_tables: ${fakeQuizActivity.title} with ${fakeQuizActivity.user_status.length} users`);
                            allActivities.push(fakeQuizActivity);
                        }
                    });
                }
            }
        });

        dashboardLogger.debug('DEBUG', 'After adding structured_tables quizzes - Total activities:', allActivities.length);
        dashboardLogger.debug('DEBUG', 'Updated activity types:', allActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

        // ZUSÄTZLICH: Durchsuche Checklisten-Daten nach Quiz-ähnlichen Aktivitäten
        if (structuredData.checklists && structuredData.checklists.rows) {
            dashboardLogger.debug('DEBUG', 'Searching checklists for quiz-like activities...');
            structuredData.checklists.rows.forEach(checklistRow => {
                // Prüfe ob der Checklisten-Titel auf Quiz hindeutet
                const title = checklistRow.checklist_title || '';
                if (title.toLowerCase().includes('quiz') ||
                    title.toLowerCase().includes('test') ||
                    checklistRow.checklist_category?.toLowerCase().includes('quiz')) {

                    console.log(`DEBUG: Found quiz-like checklist: ${title}`);

                    const quizActivity = {
                        title: title,
                        activity_type: 'quiz',
                        url: checklistRow.checklist_url || '#',
                        category_name: checklistRow.checklist_category || 'Quiz',
                        user_status: []
                    };

                    // Extrahiere Benutzer-Progress aus Checklisten
                    if (checklistRow.user_progress) {
                        checklistRow.user_progress.forEach(progress => {
                            // Verwende required_progress (Pflicht-Fortschritt) als Quiz-Ergebnis
                            if (progress.required_progress && progress.required_progress !== '0%') {
                                quizActivity.user_status.push({
                                    user_name: progress.user_name || 'Unknown',
                                    user_id: progress.user_id,
                                    grade: progress.required_progress, // z.B. "91%"
                                    status: 'Completed'
                                });
                            }
                        });
                    }

                    if (quizActivity.user_status.length > 0) {
                        console.log(`DEBUG: Adding quiz from checklists: ${quizActivity.title} with ${quizActivity.user_status.length} users`);
                        allActivities.push(quizActivity);
                    }
                }
            });
        }
    }

    if (allActivities.length === 0) return;

    // Hole Benutzer der aktuellen Gruppe
    if (!dashboardData.groups || !dashboardData.groups[currentGroup]) {
        container.innerHTML = `<p>Gruppe "${currentGroup}" nicht gefunden.</p>`;
        return;
    }

    const groupUsers = dashboardData.groups[currentGroup].users;
    const groupId = dashboardData.groups[currentGroup].value; // Get group ID for URL parameters
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name;
        if (userName) {
            groupUserNames.add(userName);
        }
    });

    // Filtere Aktivitäten, um nur Benutzer aus der aktuellen Gruppe zu zeigen
    dashboardLogger.debug('DEBUG', 'Group user names:', Array.from(groupUserNames));
    const filteredActivities = allActivities.map(activity => ({
        ...activity,
        user_status: activity.user_status ? activity.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(activity => activity.user_status.length > 0);

    dashboardLogger.debug('DEBUG', 'Filtered activities:', filteredActivities.length);
    dashboardLogger.debug('DEBUG', 'Filtered activity types:', filteredActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

    // Debug: Zeige erste paar Aktivitäten
    filteredActivities.slice(0, 3).forEach((activity, index) => {
        console.log(`DEBUG: Activity ${index}: "${activity.title}" (${activity.activity_type}) - users: ${activity.user_status.length}`);
    });

    if (filteredActivities.length === 0) {
        container.innerHTML = `<p>Keine Daten für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>`;
        return;
    }

    // Tabelle transponiert: Zeilen = Personen, Spalten = Aufgaben.
    const sortierteAufgaben = sortiereAufgaben(filteredActivities);
    const sortierteUser = sortUsersByVorname(groupUsers);

    let html = '<table id="pflichtTable" class="info-table dashboard-table pflicht-matrix">';
    html += '<thead><tr><th class="person-name pflicht-person-col">Person</th>';
    sortierteAufgaben.forEach(aktivitaet => {
        html += pflichtSpaltenKopf(aktivitaet);
    });
    html += '</tr></thead><tbody>';

    // Eine Zeile je Person, eine Spalte je Aufgabe
    sortierteUser.forEach(user => {
        const userName = getUserName(user);
        const userId = user.user_id || user.id;

        html += '<tr>';
        html += `<td class="person-name pflicht-person-col">${escapeHtml(userName)}</td>`;

        sortierteAufgaben.forEach(aktivitaet => {
            const status = findeUserStatus(aktivitaet, userId, userName);
            html += pflichtStatusZelle(status, aktivitaet, groupId);
        });

        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('pflichtTable');

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculation();

    // Scroll-Wrapper anwenden
    setTimeout(() => wrapTableWithScrollContainer('pflichtData'), 50);

    // Standardsortierung: erste Spalte (Person) aufsteigend nach Vorname
    const table = document.getElementById('pflichtTable');
    if (table) {
        const headers = table.querySelectorAll('thead th');
        if (headers[0]) headers[0].classList.add('sort-asc');
        sortState['pflichtTable_0'] = 'asc';
    }
}

// ============================================================================
// Table Scroll Wrapper - Automatisches Einpacken breiter Tabellen
// ============================================================================

/**
 * Packt breite Tabellen in einen Scroll-Wrapper ein und macht Headers sticky
 * @param {string} containerId - ID des Containers, der die Tabelle enthält
 */
function wrapTableWithScrollContainer(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Finde alle Tabellen im Container
    const tables = container.querySelectorAll("table.info-table, table.dashboard-table");

    tables.forEach(table => {
        // Prüfe ob Tabelle bereits gewickelt ist
        if (table.parentElement.classList.contains("table-scroll-wrapper")) {
            return;
        }

        // Erstelle Wrapper
        const wrapper = document.createElement("div");
        wrapper.className = "table-scroll-wrapper";

        // Füge Scroll-Hinweis hinzu
        const hint = document.createElement("div");
        hint.className = "table-scroll-hint";
        hint.innerHTML = "↔ Horizontal scrollen für alle Spalten";

        // Wickle Tabelle
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);

        // Füge Hinweis vor Wrapper ein
        wrapper.parentNode.insertBefore(hint, wrapper);

        // Erstelle oberen Scrollbalken für leichtere Erreichbarkeit
        const topScroll = document.createElement("div");
        topScroll.className = "table-scroll-top";
        const topScrollContent = document.createElement("div");
        topScrollContent.className = "table-scroll-top-content";
        topScroll.appendChild(topScrollContent);

        // Füge oberen Scrollbalken vor Hinweis ein
        wrapper.parentNode.insertBefore(topScroll, hint);

        // Prüfe ob Tabelle zu breit ist und füge Overflow-Klassen hinzu
        setTimeout(() => {
            const hasOverflow = wrapper.scrollWidth > wrapper.clientWidth;
            if (hasOverflow) {
                hint.classList.add("show");
                wrapper.classList.add("has-overflow");
                // Setze die Breite des oberen Scrollbalkens
                topScrollContent.style.width = wrapper.scrollWidth + "px";
                topScroll.style.display = "block";
            } else {
                topScroll.style.display = "none";
            }
        }, 100);

        // Synchronisiere Scrolling zwischen oberem und unterem Scrollbalken
        topScroll.addEventListener("scroll", function() {
            wrapper.scrollLeft = this.scrollLeft;
        });

        wrapper.addEventListener("scroll", function() {
            const scrollLeft = this.scrollLeft;
            const maxScroll = this.scrollWidth - this.clientWidth;

            // Synchronisiere mit oberem Scrollbalken
            topScroll.scrollLeft = scrollLeft;

            // Ändere Hint-Farbe basierend auf Scroll-Position
            if (scrollLeft > 10) {
                hint.style.background = "linear-gradient(135deg, #d4edda, #c3e6cb)";
                hint.style.color = "#155724";
            } else {
                hint.style.background = "linear-gradient(135deg, #e8f0fe, #d2e3fc)";
                hint.style.color = "#1a73e8";
            }

            // Entferne Schatten wenn ans Ende gescrollt
            if (scrollLeft >= maxScroll - 5) {
                wrapper.classList.add("scrolled-to-end");
            } else {
                wrapper.classList.remove("scrolled-to-end");
            }
        });
    });
}

/**
 * Wendet Scroll-Wrapper auf alle relevanten Container an
 */
function applyTableScrollWrappers() {
    const containerIds = [
        "checklistData",
        "pflichtData",
        "examData",
        "groupProgressTable"
    ];

    containerIds.forEach(id => {
        wrapTableWithScrollContainer(id);
    });
}

// Event-Listener für DOM-Updates (wenn Tabellen neu generiert werden)
if (typeof MutationObserver !== "undefined") {
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.addedNodes.length > 0) {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1 && node.tagName === "TABLE") {
                        const containerId = node.closest("[id]")?.id;
                        if (containerId && ["checklistData", "pflichtData", "examData", "groupProgressTable"].includes(containerId)) {
                            setTimeout(() => wrapTableWithScrollContainer(containerId), 50);
                        }
                    }
                });
            }
        });
    });

    // Beobachte relevante Container
    document.addEventListener("DOMContentLoaded", () => {
        ["checklistData", "pflichtData", "examData", "groupProgressTable"].forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                observer.observe(element, { childList: true, subtree: true });
            }
        });
    });
}
