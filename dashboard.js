// Dashboard JavaScript
let dashboardData = null;
let currentGroup = 'all';
let currentGrouping = 'all'; // New: current grouping selection
let currentWeek = 10;
let totalWeeks = 40;
let checklistViewType = 'both'; // New: track checklist column view setting
let sortState = {}; // Track sorting state for different tables
let gradeMapping = {}; // GradeMapping from config.ini

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
    } else if (tabName === 'zentral') {
        loadZentralTab();
    }
}

// Datei-Info anzeigen
function displayFileInfo(filename) {
    const container = document.getElementById('fileInfoContainer');
    const textElement = document.getElementById('fileInfoText');

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

        // Formatiere für Anzeige
        const formattedDateTime = `${day}.${month}.${year} ${hour}:${minute}:${second}`;
        textElement.textContent = formattedDateTime;

        // Container anzeigen
        container.style.display = 'flex';
    } else {
        // Fallback: zeige rohen Dateinamen
        textElement.textContent = filename.replace(/.*[\\\/]/, ''); // Nur Dateiname ohne Pfad
        container.style.display = 'flex';
    }
}

// Daten laden
async function loadData() {
    showLoading(true);

    try {
        const response = await fetch('/api/data');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        dashboardData = await response.json();

        // Load grade mapping from backend
        console.log('DEBUG: Checking for grade_mapping in response...');
        console.log('DEBUG: dashboardData.grade_mapping exists?', !!dashboardData.grade_mapping);
        console.log('DEBUG: dashboardData.grade_mapping value:', dashboardData.grade_mapping);

        if (dashboardData.grade_mapping) {
            gradeMapping = dashboardData.grade_mapping;
            console.log('✓ Grade mapping loaded successfully:', gradeMapping);
        } else {
            console.error('✗ ERROR: No grade_mapping found in backend response!');
            console.log('Available keys in dashboardData:', Object.keys(dashboardData));
        }

        // Debug: JSON-Struktur analysieren
        console.log('=== DASHBOARD DATA LOADED ===');
        console.log('Data structure:', {
            hasActivitiesByCategory: !!dashboardData.activities_by_category,
            categoriesCount: dashboardData.activities_by_category ? dashboardData.activities_by_category.length : 'undefined',
            sampleCategory: dashboardData.activities_by_category ? dashboardData.activities_by_category[0] : 'none'
        });

        if (dashboardData.activities_by_category && dashboardData.activities_by_category.length > 0) {
            const firstCategory = dashboardData.activities_by_category[0];
            console.log('First category assignments:', {
                assignmentCount: firstCategory.assignments ? firstCategory.assignments.length : 'undefined',
                sampleAssignment: firstCategory.assignments && firstCategory.assignments.length > 0 ? firstCategory.assignments[0] : 'none'
            });
        }

        // Datei-Info anzeigen
        displayFileInfo(dashboardData.last_updated);

        // Gruppen-Dropdown füllen
        populateGroupSelectors();

        // Kategorie-Filter füllen
        populateCategoryFilter();

        // Dashboard aktualisieren
        updateDashboard();

        showLoading(false);

    } catch (error) {
        console.error('Fehler beim Laden der Daten:', error);
        showError('Fehler beim Laden der Daten: ' + error.message);
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
    console.error(message);
    // Hier könnte eine Benutzer-freundliche Fehleranzeige implementiert werden
}

// Gruppen-Tabs und Dropdowns füllen
function populateGroupSelectors() {
    // Populate grouping tabs
    populateGroupingTabs();

    // Populate group tabs
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
        const detailText = pflichtaufgabenCategory.assignmentCount > 0 && pflichtaufgabenCategory.quizCount > 0
            ? ` (${pflichtaufgabenCategory.assignmentCount} Aufgaben + ${pflichtaufgabenCategory.quizCount} Quizzes)`
            : ` (${pflichtaufgabenCategory.count})`;
        pflichtOption.textContent = `Nur Pflichtaufgaben-Kategorie${detailText}`;
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

// Gruppierungen aus Gruppennamen extrahieren
function extractGroupings() {
    if (!dashboardData || !dashboardData.groups) return {};

    const groupings = {};

    Object.keys(dashboardData.groups).forEach(groupName => {
        // Alles vor dem ersten Leerzeichen als Gruppierung verwenden
        const prefix = groupName.split(' ')[0];

        if (!groupings[prefix]) {
            groupings[prefix] = [];
        }
        groupings[prefix].push(groupName);
    });

    return groupings;
}

// Gruppierungs-Tabs dynamisch erstellen
function populateGroupingTabs() {
    const groupingTabsContainer = document.getElementById('groupingTabs');
    if (!groupingTabsContainer || !dashboardData || !dashboardData.groups) return;

    // Container leeren
    groupingTabsContainer.innerHTML = '';

    const groupings = extractGroupings();

    // Für jede Gruppierung einen Tab erstellen
    Object.keys(groupings).sort().forEach(groupingName => {
        const groupingButton = document.createElement('button');
        groupingButton.className = 'grouping-nav-btn';
        groupingButton.id = `grouping${groupingName.replace(/\s+/g, '')}`;
        groupingButton.onclick = () => selectGrouping(groupingName);

        const spanText = document.createElement('span');
        spanText.className = 'grouping-tab-text';
        spanText.textContent = groupingName;
        groupingButton.appendChild(spanText);

        // Zeige Anzahl der Gruppen in dieser Gruppierung
        const countBadge = document.createElement('span');
        countBadge.className = 'grouping-count-badge';
        countBadge.textContent = groupings[groupingName].length;
        groupingButton.appendChild(countBadge);

        groupingTabsContainer.appendChild(groupingButton);
    });
}

// Gruppen-Tabs dynamisch erstellen (basierend auf aktueller Gruppierung)
function populateGroupTabs() {
    const groupTabsContainer = document.getElementById('groupTabs');
    if (!groupTabsContainer || !dashboardData || !dashboardData.groups) return;

    // Container leeren
    groupTabsContainer.innerHTML = '';

    // Gruppen basierend auf aktueller Gruppierung filtern
    let groupsToShow = [];

    if (currentGrouping === 'all') {
        groupsToShow = Object.keys(dashboardData.groups);
    } else {
        const groupings = extractGroupings();
        groupsToShow = groupings[currentGrouping] || [];
    }

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
}

// Ausgewählte Benutzer basierend auf aktueller Gruppierung und Gruppe
function getSelectedUsers() {
    if (!dashboardData || !dashboardData.groups) return [];

    if (currentGroup === 'all') {
        // Alle Benutzer basierend auf aktueller Gruppierung
        if (currentGrouping === 'all') {
            // Alle Benutzer aus allen Gruppen
            let allUsers = [];
            Object.values(dashboardData.groups).forEach(group => {
                allUsers = allUsers.concat(group.users);
            });
            return allUsers;
        } else {
            // Alle Benutzer aus Gruppen der aktuellen Gruppierung
            const groupings = extractGroupings();
            const groupsInGrouping = groupings[currentGrouping] || [];
            let groupingUsers = [];
            groupsInGrouping.forEach(groupName => {
                if (dashboardData.groups[groupName]) {
                    groupingUsers = groupingUsers.concat(dashboardData.groups[groupName].users);
                }
            });
            return groupingUsers;
        }
    } else {
        // Benutzer aus spezifischer Gruppe
        return dashboardData.groups[currentGroup]?.users || [];
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
    // The timed calculation should be: (group_average / current_week) * total_weeks
    const currentWeek = parseInt(document.getElementById('weekSlider')?.value || 10);
    const totalWeeks = 10; // This should match the max value of the week slider

    const avgRequiredProgressTimed = currentWeek > 0 ?
        Math.round(((avgRequiredProgress / currentWeek) * totalWeeks) * 100) / 100 : 0;
    const avgAllProgressTimed = currentWeek > 0 ?
        Math.round(((avgAllProgress / currentWeek) * totalWeeks) * 100) / 100 : 0;


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
    if (!dashboardData || !dashboardData.structured_tables) {
        return { totalChecklists: 38, totalPflichtaufgaben: 22 }; // Fallback-Werte
    }

    let maxChecklists = 0;
    let maxPflichtaufgaben = 0;

    // Durch alle Gruppen iterieren und die maximale Anzahl finden
    Object.keys(dashboardData.structured_tables).forEach(groupName => {
        const groupData = dashboardData.structured_tables[groupName];

        if (groupData.checklists && groupData.checklists.rows) {
            maxChecklists = Math.max(maxChecklists, groupData.checklists.rows.length);
        }

        if (groupData.pflichtaufgaben && groupData.pflichtaufgaben.rows) {
            maxPflichtaufgaben = Math.max(maxPflichtaufgaben, groupData.pflichtaufgaben.rows.length);
        }
    });

    return {
        totalChecklists: maxChecklists || 38, // Fallback wenn keine Daten gefunden
        totalPflichtaufgaben: maxPflichtaufgaben || 22 // Fallback wenn keine Daten gefunden
    };
}

// Übersichts-Statistiken aktualisieren
function updateOverviewStats(groupStats, users) {
    // Gesamtanzahl dynamisch aus den Daten ermitteln
    const { totalChecklists, totalPflichtaufgaben } = getTotalCounts();

    // Maximale Schulwochen basierend auf dem Slider (nicht 40!)

    // Durchschnittliche erledigte Anzahl pro Person berechnen
    const avgCompletedChecklists = users.length > 0 ?
        users.reduce((sum, user) => sum + user.checklists.required_100_count, 0) / users.length : 0;
    const avgCompletedPflichtaufgaben = users.length > 0 ?
        users.reduce((sum, user) => sum + user.assignments.submitted_count, 0) / users.length : 0;

    // Erwartete Anzahl für die ausgewählte Referenzwoche
    // Bei Woche 10 (Maximum) sollten alle Checklisten/Aufgaben erwartet werden
    const selectedWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 10);
    const expectedChecklistsForWeek = Math.ceil((totalChecklists / 10) * selectedWeek);
    const expectedPflichtaufgabenForWeek = Math.ceil((totalPflichtaufgaben / 10) * selectedWeek);

    // Prozentsätze basierend auf durchschnittlich erledigte vs. erwartete für die Woche
    const percentChecklists = expectedChecklistsForWeek > 0 ?
        Math.round((avgCompletedChecklists / expectedChecklistsForWeek) * 100 * 100) / 100 : 0;
    const percentPflichtaufgaben = expectedPflichtaufgabenForWeek > 0 ?
        Math.round((avgCompletedPflichtaufgaben / expectedPflichtaufgabenForWeek) * 100 * 100) / 100 : 0;

    // Checklisten-Karte aktualisieren - zeigt durchschnittlich erledigte vs. erwartete für gewählte Woche
    document.getElementById('completedCount').textContent = avgCompletedChecklists.toFixed(1);
    document.getElementById('totalCount').textContent = expectedChecklistsForWeek;
    document.getElementById('completionPercentage').textContent = percentChecklists.toFixed(2) + '%';

    // Progress Ring für Checklisten
    updateProgressRing('completionRing', Math.min(percentChecklists, 100));

    // Durchschnittlicher Fortschritt (wochenabhängig)
    // Berechne die Werte direkt basierend auf der aktuell ausgewählten Woche
    const currentProgressType = document.querySelector('input[name="progressType"]:checked').value;
    const cardSelectedWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 10);

    // Berechne den Gruppendurchschnitt für die ausgewählte Woche
    let cardAvgRequiredProgress = 0;
    let cardAvgAllProgress = 0;
    const validUsers = users.filter(user => user && user.name);

    validUsers.forEach(user => {
        const actualProgress = calculateActualProgressForWeek(user, cardSelectedWeek, 10, currentGroup);
        cardAvgRequiredProgress += actualProgress.pflichtProgress;
        cardAvgAllProgress += actualProgress.gesamtProgress;
    });

    if (validUsers.length > 0) {
        cardAvgRequiredProgress = cardAvgRequiredProgress / validUsers.length;
        cardAvgAllProgress = cardAvgAllProgress / validUsers.length;
    }

    const progressValue = currentProgressType === 'pflicht' ? cardAvgRequiredProgress : cardAvgAllProgress;

    document.getElementById('avgCompletionText').textContent = progressValue.toFixed(1) + '%';
    document.getElementById('avgCompletionBar').style.width = progressValue + '%';

    // Durchschnittsnote basierend auf Pflicht % (IHK-Notenschlüssel)
    const avgGradeElement = document.getElementById('avgGradeText');
    const calculatedGrade = calculateGradeFromPflichtProgress(cardAvgRequiredProgress);
    avgGradeElement.textContent = calculatedGrade;

    // Pflichtaufgaben-Statistiken - zeigt durchschnittlich erledigte vs. erwartete für gewählte Woche
    document.getElementById('pflichtCompletedCount').textContent = avgCompletedPflichtaufgaben.toFixed(1);
    document.getElementById('pflichtTotalCount').textContent = expectedPflichtaufgabenForWeek;
    document.getElementById('pflichtCompletionPercentage').textContent = percentPflichtaufgaben.toFixed(2) + '%';

    // Pflicht Progress Ring aktualisieren
    updateProgressRing('pflichtCompletionRing', Math.min(percentPflichtaufgaben, 100));

    // Durchschnittsnote Pflichtaufgaben basierend auf Pflicht % (IHK-Notenschlüssel)
    const pflichtAvgGradeElement = document.getElementById('pflichtAverageGrade');
    const calculatedPflichtGrade = calculateGradeFromPflichtProgress(cardAvgRequiredProgress);
    pflichtAvgGradeElement.textContent = calculatedPflichtGrade;

    // Detailierte Fortschritts-Tabelle generieren
    generateGroupProgressTable(users);
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
    const expectedChecklistsForWeek = Math.ceil((totalChecklists / 10) * selectedWeek);
    const expectedPflichtaufgabenForWeek = Math.ceil((totalPflichtaufgaben / 10) * selectedWeek);

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
        if (currentGrouping === 'all') {
            titleElement.textContent = 'Gruppenvergleich - Alle Gruppen';
        } else {
            titleElement.textContent = `Gruppenvergleich - ${currentGrouping}`;
        }
    }

    // Gruppen basierend auf aktueller Gruppierung filtern
    let groupsToShow = [];
    if (currentGrouping === 'all') {
        groupsToShow = Object.keys(dashboardData.groups);
    } else {
        const groupings = extractGroupings();
        groupsToShow = groupings[currentGrouping] || [];
    }

    if (groupsToShow.length === 0) {
        container.innerHTML = '<p><em>Keine Gruppen verfügbar.</em></p>';
        return;
    }

    let html = '<div style="overflow-x: auto;"><table id="groupComparisonTable" class="info-table dashboard-table overview-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="group-name-cell">Gruppe</th>';
    html += '<th>Personen</th>';
    html += '<th>Checklisten 100%</th>';
    html += '<th>Ø Pflicht (%)</th>';
    html += '<th>Ø Note</th>';
    html += '<th>Ø Gesamt (%)</th>';
    html += '<th>Eingereichte Aufgaben</th>';
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

        // Zeige die gleichen Werte wie in den Cards:
        // "Ø Checklisten 100%" = avgCompletedChecklists (wie completedCount in der Card)
        // "Ø Pflichtaufgaben eingereicht" = avgCompletedPflichtaufgaben (wie pflichtCompletedCount in der Card)

        html += '<tr>';
        html += `<td class="group-name-cell"><strong>${stats.groupName}</strong></td>`;
        html += `<td style="text-align: center;">${stats.userCount}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(stats.avgCompletedChecklists * 10, 100)}%; --progress-color: #28a745;">${stats.avgCompletedChecklists.toFixed(1)}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${displayRequiredProgress}%; --progress-color: #007bff;">${displayRequiredProgress.toFixed(1)}%</td>`;
        html += `<td style="text-align: center; font-weight: bold;">${gradeText}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${stats.avgAllProgress}%; --progress-color: #6f42c1;">${stats.avgAllProgress.toFixed(1)}%</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(stats.avgCompletedPflichtaufgaben * 10, 100)}%; --progress-color: #fd7e14;">${stats.avgCompletedPflichtaufgaben.toFixed(1)}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('groupComparisonTable');
}

// Berechnet die tatsächlichen Fortschrittsprozentsätze basierend nur auf Checklisten bis zur ausgewählten Woche
function calculateActualProgressForWeek(user, selectedWeek, maxWeeks, groupName = null) {
    // Standardwerte falls keine strukturierten Daten verfügbar sind
    let pflichtProgress = 0;
    let gesamtProgress = 0;

    // Bestimme die zu verwendende Gruppe
    const targetGroup = groupName || currentGroup;

    // Zugriff auf strukturierte Checklisten-Daten
    if (dashboardData && dashboardData.structured_tables && targetGroup && targetGroup !== 'all') {
        const tableData = dashboardData.structured_tables[targetGroup]?.checklists;
        if (tableData && tableData.rows && tableData.headers) {
            // Finde den Index des Benutzers in den Headern
            const userIndex = tableData.headers.findIndex(header => header === user.name);

            if (userIndex > 0) { // Index 0 ist normalerweise die Checklist-Spalte
                const totalChecklists = tableData.rows.length;
                const expectedChecklistsForWeek = Math.ceil((totalChecklists / 10) * selectedWeek);

                // Summiere alle Pflicht- und Gesamt-Prozente von ALLEN Checklisten
                let totalPflichtPercent = 0;
                let totalGesamtPercent = 0;

                // Durchlaufe ALLE Checklisten und summiere die Prozente
                tableData.rows.forEach(row => {
                    if (row.user_progress && row.user_progress[userIndex - 1]) {
                        const progress = row.user_progress[userIndex - 1];
                        const requiredProgressText = progress.required_progress || '0%';
                        const allProgressText = progress.all_progress || '0%';

                        const pflichtPercent = parseFloat(requiredProgressText.replace('%', ''));
                        const gesamtPercent = parseFloat(allProgressText.replace('%', ''));

                        if (!isNaN(pflichtPercent)) {
                            totalPflichtPercent += pflichtPercent;
                        }
                        if (!isNaN(gesamtPercent)) {
                            totalGesamtPercent += gesamtPercent;
                        }
                    }
                });

                // Berechne erwartete Gesamtpunkte für diese Woche (Anzahl Checklisten × 100%)
                const expectedTotalPflichtPoints = expectedChecklistsForWeek * 100;
                const expectedTotalGesamtPoints = expectedChecklistsForWeek * 100;

                // Berechne Prozentsatz: Tatsächliche Punkte / Erwartete Punkte × 100
                if (expectedTotalPflichtPoints > 0) {
                    pflichtProgress = Math.round((totalPflichtPercent / expectedTotalPflichtPoints) * 100 * 100) / 100;
                }
                if (expectedTotalGesamtPoints > 0) {
                    gesamtProgress = Math.round((totalGesamtPercent / expectedTotalGesamtPoints) * 100 * 100) / 100;
                }

                // Debug: Zeige neue Berechnungslogik
                console.log(`DEBUG NEW: ${user.name}, Week ${selectedWeek}: Expected=${expectedChecklistsForWeek} checklists (${expectedTotalPflichtPoints} points), Total Pflicht=${totalPflichtPercent}%, Total Gesamt=${totalGesamtPercent}% → Pflicht=${pflichtProgress}%, Gesamt=${gesamtProgress}%`);
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
        gesamtProgress: gesamtProgress
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

// Generiert die Fortschritts-Tabelle für die Übersicht
function generateGroupProgressTable(users) {
    const container = document.getElementById('groupProgressTable');
    if (!container) return;

    // Wenn "Alle Gruppen" ausgewählt ist, zeige Vergleichstabelle
    if (currentGroup === 'all') {
        generateGroupComparisonTable();
        return;
    }

    // Titel für individuelle Gruppe aktualisieren
    const titleElement = document.getElementById('groupDetailTitle');
    if (titleElement) {
        titleElement.textContent = `Gesamtfortschritt pro Person - ${currentGroup}`;
    }

    if (users.length === 0) {
        container.innerHTML = '<p><em>Keine Daten verfügbar.</em></p>';
        return;
    }

    let html = '<div style="overflow-x: auto;"><table id="individualProgressTable" class="info-table dashboard-table overview-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="person-name">Person</th>';
    html += '<th>Checklisten 100%</th>';
    html += '<th>Ø Pflicht (%)</th>';
    html += '<th>Ø Note</th>';
    html += '<th>Ø Gesamt (%)</th>';
    html += '<th>Eingereichte Aufgaben</th>';
    html += '<th>Note Pflichtaufgaben</th>';
    html += '</tr></thead>';
    html += '<tbody>';


    users.forEach(user => {
        // Berechne tatsächliche Prozentsätze basierend nur auf Checklisten bis zur ausgewählten Woche
        // Hole den aktuellen Wochenwert vom Slider
        const selectedWeek = parseInt(document.getElementById('referenceWeekSlider')?.value || 10);
        const actualProgress = calculateActualProgressForWeek(user, selectedWeek, 10);
        const displayPflichtProgress = actualProgress.pflichtProgress;
        const displayGesamtProgress = actualProgress.gesamtProgress;



        // Berechne Note basierend auf Pflicht %
        const gradeText = calculateGradeFromPflichtProgress(displayPflichtProgress);

        // Berechne Pflichtaufgaben-Note
        const pflichtGradeResult = calculatePflichtaufgabenGradeForUserByName(user.name, currentGroup);
        let pflichtGradeText = '-';
        let pflichtGradeColor = '#6C757D';
        if (pflichtGradeResult && pflichtGradeResult.grade !== null) {
            pflichtGradeText = `${pflichtGradeResult.grade.toFixed(1)} (${pflichtGradeResult.percent.toFixed(1)}%, n=${pflichtGradeResult.count})`;
            pflichtGradeColor = getGradeColor(pflichtGradeResult.grade);
        }

        html += '<tr>';
        html += `<td class="person-name"><strong>${user.name}</strong></td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(user.checklists.required_100_count * 10, 100)}%; --progress-color: #28a745;">${user.checklists.required_100_count}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${displayPflichtProgress}%; --progress-color: #007bff;">${displayPflichtProgress.toFixed(1)}%</td>`;
        html += `<td style="text-align: center; font-weight: bold;">${gradeText}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${displayGesamtProgress}%; --progress-color: #6f42c1;">${displayGesamtProgress.toFixed(1)}%</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${user.assignments.percent_submitted}%; --progress-color: #fd7e14;">${user.assignments.submitted_count}</td>`;
        html += `<td style="text-align: center; font-weight: bold; color: ${pflichtGradeColor};" title="Durchschnitt aus ${pflichtGradeResult ? pflichtGradeResult.count : 0} bewerteten Pflichtaufgaben">${pflichtGradeText}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('individualProgressTable');
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

// Gruppierung über Tab auswählen
function selectGrouping(groupingName) {
    currentGrouping = groupingName;

    // Bei Gruppierungsauswahl auf "Alle Gruppen" der Gruppierung setzen
    currentGroup = 'all';

    // Gruppen-Tabs basierend auf neuer Gruppierung aktualisieren
    populateGroupTabs();

    // Alle Tabs und Dropdowns synchronisieren
    syncGroupSelectors();

    // Dashboard und alle Tabs aktualisieren
    updateDashboard();
    updateAllTabs();
}

// Gruppe über Tab auswählen
function selectGroup(groupName) {
    currentGroup = groupName;

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
    }

    // Alle anderen Gruppen-Dropdowns synchronisieren
    syncGroupSelectors();

    // Dashboard und alle Tabs aktualisieren
    updateDashboard();
    updateAllTabs();
}

// Synchronisiert alle Gruppen-Tabs und Dropdowns
function syncGroupSelectors() {
    // Synchronize grouping tabs
    syncGroupingTabs();

    // Synchronize group tabs
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

// Synchronisiert die Gruppierungs-Tabs
function syncGroupingTabs() {
    // Alle Gruppierungs-Tabs inaktiv setzen
    document.querySelectorAll('.grouping-nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Den aktiven Gruppierungs-Tab markieren
    if (currentGrouping === 'all') {
        const allGroupingBtn = document.getElementById('groupingAll');
        if (allGroupingBtn) {
            allGroupingBtn.classList.add('active');
        }
    } else {
        const activeGroupingBtn = document.getElementById(`grouping${currentGrouping.replace(/\s+/g, '')}`);
        if (activeGroupingBtn) {
            activeGroupingBtn.classList.add('active');
        }
    }
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
    }

    // Zentrale Leistungsnachweise-Tab aktualisieren falls sichtbar
    const zentralTab = document.getElementById('zentralTab');
    if (zentralTab && zentralTab.style.display !== 'none') {
        generateZentralTable();
    }
}

// Referenzwoche aktualisieren
function updateReferenceWeek(week) {
    currentWeek = parseInt(week);
    console.log('Referenzwoche geändert zu:', currentWeek);

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

// Auf aktuelle Woche setzen
function setToCurrentWeek() {
    const slider = document.getElementById('referenceWeekSlider');
    const currentDate = new Date();
    // Einfache Berechnung der Schulwoche (könnte verfeinert werden)
    const schoolStart = new Date(currentDate.getFullYear(), 8, 1); // 1. September
    const weeksDiff = Math.ceil((currentDate - schoolStart) / (7 * 24 * 60 * 60 * 1000));
    const calculatedWeek = Math.max(1, Math.min(parseInt(slider.max), weeksDiff));

    slider.value = calculatedWeek;
    updateReferenceWeek(calculatedWeek);
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

    let html = '<div style="overflow-x: auto;"><table id="checklistTable" class="info-table dashboard-table">';
    html += '<thead><tr class="sticky-header">';

    // Header: Checkliste + Benutzernamen mit je 2 Spalten (Pflicht + Gesamt)
    html += '<th class="checklist-name-cell">Checkliste</th>';

    // Für jeden Benutzer zwei Spalten: Pflicht + Gesamt
    for (let i = 1; i < tableData.headers.length; i++) {
        const userName = tableData.headers[i];
        html += `<th colspan="2" style="text-align: center; background: linear-gradient(135deg, #667eea, #764ba2);">${userName}</th>`;
    }
    html += '</tr>';

    // Zweite Header-Zeile für Pflicht/Gesamt
    html += '<tr class="sticky-header">';
    html += '<th></th>'; // Leere Zelle für Checkliste-Spalte
    for (let i = 1; i < tableData.headers.length; i++) {
        html += '<th class="sub-header-pflicht">Pflicht</th>';
        html += '<th class="sub-header-gesamt gesamt-column">Gesamt</th>';
    }
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jede Checkliste
    tableData.rows.forEach(row => {
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

            // Pflicht-Fortschritt
            html += `<td class="progress-cell" style="--progress-width: ${pflichtPercent}%; --progress-color: #28a745;">${requiredProgressText}</td>`;

            // Gesamt-Fortschritt (mit gesamt-column Klasse für ein-/ausblenden)
            html += `<td class="progress-cell gesamt-column" style="--progress-width: ${gesamtPercent}%; --progress-color: #6f42c1;">${allProgressText}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('checklistTable');
}

// Pflichtaufgaben-Tab laden
function loadPflichtTab() {
    const filterSection = document.getElementById('pflichtFilterSection');

    setTimeout(() => {
        generatePflichtTable();
        if (filterSection) filterSection.style.display = 'block';
    }, 500);
}

// Zentrale Leistungsnachweise-Tab laden
function loadZentralTab() {
    const filterSection = document.getElementById('zentralFilterSection');

    setTimeout(() => {
        generateZentralTable();
        if (filterSection) filterSection.style.display = 'block';
    }, 500);
}

// Pflichtaufgaben-Tabelle generieren (Zeilen = Aufgaben, Spalten = Personen)
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
        console.log('DEBUG: Searching for quizzes in all categories...');
        let totalQuizzesFound = 0;
        dashboardData.activities_by_category.forEach(category => {
            console.log(`DEBUG: Category "${category.category_name}" has ${category.quizzes ? category.quizzes.length : 0} quizzes`);
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
        console.log('DEBUG: Total quizzes found and added:', totalQuizzesFound);

        // ZUSÄTZLICH: Prüfe structured_tables für weitere Quiz-Daten
        if (dashboardData.structured_tables && dashboardData.structured_tables[currentGroup]) {
            console.log('DEBUG: Checking structured_tables for additional quiz data...');
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

    console.log('DEBUG: Final allActivities count:', allActivities.length);
    console.log('DEBUG: Activity types breakdown:', allActivities.reduce((acc, activity) => {
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
    console.log('DEBUG: Erste 3 Benutzer der Gruppe:', groupUsers.slice(0, 3));

    // Prüfe verschiedene mögliche Benutzer-Name-Felder
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        // Versuche verschiedene mögliche Felder für den Namen
        const userName = user.user_name || user.name || user.username || user.display_name;
        if (userName) {
            groupUserNames.add(userName);
        }
        console.log('DEBUG: User object:', user, 'extracted name:', userName);
    });

    console.log('DEBUG: Gruppe', currentGroup, 'hat', groupUsers.length, 'Benutzer, extrahierte Namen:', Array.from(groupUserNames));

    // Debug: Prüfe Struktur der Activities
    console.log('DEBUG: Assignments für Gruppe', currentGroup, ':', assignments.length);
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

    console.log('DEBUG: Nach Filterung:', filteredAssignments.length, 'Aktivitäten übrig');

    if (filteredAssignments.length === 0) {
        container.innerHTML = `<p>Keine Daten für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>
                               <p>Debug: ${assignments.length} Aktivitäten gefunden, aber keine für Benutzer dieser Gruppe.</p>`;
        return;
    }

    let html = '<div style="overflow-x: auto;"><table id="pflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    // Header für alle Benutzer der Gruppe
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
        html += `<th style="text-align: center; min-width: 120px;">${userName}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Pflichtaufgabe/Quiz
    filteredAssignments.forEach(assignment => {
        html += '<tr>';
        html += `<td style="min-width: 250px;">`;
        const activityIcon = assignment.activity_type === 'quiz' ? '🧭' : '📝';
        const activityType = assignment.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe';
        html += `<a href="${assignment.url}" target="_blank">${activityIcon} ${assignment.title}</a>`;
        html += `<br><small style="color: #666;">Typ: ${activityType} | Kategorie: ${assignment.category_name || 'Unbekannt'}</small>`;
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
                cellContent = `<strong>${status.grade}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                cellContent = `<strong>${status.rating}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                cellContent = `<strong>${status.score}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.status === 'Zur Bewertung abgegeben') {
                cellContent = '<span style="color: #ffc107;">bewertbar</span>';
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                cellContent = '<span style="color: #dc3545;">Nicht eingereicht</span>';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';

    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('pflichtTable');

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

    let html = '<div style="overflow-x: auto;"><table id="pflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    for (let i = 1; i < tableData.headers.length; i++) {
        const userName = tableData.headers[i];
        html += `<th style="text-align: center; min-width: 120px;">${userName}</th>`;
    }
    html += '</tr></thead><tbody>';

    tableData.rows.forEach(row => {
        html += '<tr>';
        const typeIcon = row.assignment_type === 'quiz' ? '🧭' : '📝';
        html += `<td style="min-width: 250px;">`;
        html += `<a href="${row.assignment_url}" target="_blank">${typeIcon} ${row.assignment_title}</a>`;
        html += `<br><small style="color: #666;">Typ: ${row.assignment_type === 'quiz' ? 'Quiz' : 'Aufgabe'}</small>`;
        html += `</td>`;

        row.user_status.forEach(status => {
            let cellContent = '';
            let cellClass = 'progress-cell';
            let bgColor = '';

            if (status.grade && status.grade != '-') {
                cellContent = `<strong>${status.grade}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status.status === 'Zur Bewertung abgegeben') {
                cellContent = '<span style="color: #ffc107;">bewertbar</span>';
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                cellContent = '<span style="color: #dc3545;">Nicht eingereicht</span>';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    makeTableSortable('pflichtTable');

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
    if (currentGrouping === 'all') {
        groupsToShow = Object.keys(dashboardData.structured_tables).filter(groupName => {
            // Überspringe ignorierte Gruppen
            return !(dashboardData.ignored_groups && dashboardData.ignored_groups.includes(groupName));
        });
    } else {
        const groupings = extractGroupings();
        groupsToShow = groupings[currentGrouping] || [];
    }

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
                    category: row.checklist_category
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

    let html = '<div style="overflow-x: auto;"><table id="allGroupsChecklistTable" class="info-table dashboard-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="checklist-name-cell">Checkliste</th>';

    // Header für alle Benutzer
    allUsers.forEach(user => {
        html += `<th colspan="2" style="text-align: center; background: linear-gradient(135deg, #667eea, #764ba2);">${user.name}<br><small>${user.group}</small></th>`;
    });
    html += '</tr>';

    // Zweite Header-Zeile
    html += '<tr class="sticky-header"><th></th>';
    allUsers.forEach(() => {
        html += '<th class="sub-header-pflicht">Pflicht</th>';
        html += '<th class="sub-header-gesamt gesamt-column">Gesamt</th>';
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Checkliste
    checklistsArray.forEach(checklist => {
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

            html += `<td class="progress-cell" style="--progress-width: ${pflichtPercent}%; --progress-color: #28a745;">${requiredProgressText}</td>`;
            html += `<td class="progress-cell gesamt-column" style="--progress-width: ${gesamtPercent}%; --progress-color: #6f42c1;">${allProgressText}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsChecklistTable');
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

    // Alle Benutzer sammeln
    let allUsersSet = new Set();
    assignments.forEach(assignment => {
        if (assignment.user_status) {
            assignment.user_status.forEach(userStatus => {
                allUsersSet.add(JSON.stringify({
                    id: userStatus.user_id,
                    name: userStatus.user_name
                }));
            });
        }
    });
    const allUsers = Array.from(allUsersSet).map(str => JSON.parse(str));

    let html = '<div style="overflow-x: auto;"><table id="allGroupsPflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    // Header für alle Benutzer
    allUsers.forEach(user => {
        html += `<th style="text-align: center; min-width: 120px;">${user.name}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Pflichtaufgabe/Quiz
    assignments.forEach(assignment => {
        html += '<tr>';
        html += `<td style="min-width: 250px;">`;
        const activityIcon = assignment.activity_type === 'quiz' ? '🧭' : '📝';
        const activityType = assignment.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe';
        html += `<a href="${assignment.url}" target="_blank">${activityIcon} ${assignment.title}</a>`;
        html += `<br><small style="color: #666;">Typ: ${activityType} | Kategorie: ${assignment.category_name || 'Unbekannt'}</small>`;
        html += `</td>`;

        // Status für jeden Benutzer
        allUsers.forEach(user => {
            // Finde den Status für diesen Benutzer in diesem Assignment
            let status = null;
            if (assignment.user_status) {
                status = assignment.user_status.find(s => s.user_id === user.id);
            }

            let cellContent = '';
            let cellClass = 'progress-cell';
            let bgColor = '';

            if (status && status.grade && status.grade !== '-') {
                // Grade vorhanden - zeige Grade-Wert
                cellContent = `<strong>${status.grade}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                cellContent = `<strong>${status.rating}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                cellContent = `<strong>${status.score}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.status === 'Zur Bewertung abgegeben') {
                // Zur Bewertung abgegeben - zeige "bewertbar"
                cellContent = '<span style="color: #ffc107;">bewertbar</span>';
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                // Nicht eingereicht
                cellContent = '<span style="color: #dc3545;">Nicht eingereicht</span>';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsPflichtTable');

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculationForAllGroups();

    // Sofortige numerische Sortierung nach Aufgabennummer
    const table = document.getElementById('allGroupsPflichtTable');
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
            sortState['allGroupsPflichtTable_0'] = 'asc';
        }
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
    generatePflichtTable();
    // Status- und Typ-Filter anwenden
    applyPflichtViewFilters();
}

// Status- und Typ-Filter für Pflichtaufgaben anwenden
function applyPflichtViewFilters() {
    const statusFilter = document.getElementById('pflichtStatusFilter');
    const typeFilter = document.getElementById('pflichtTypeFilter');

    if (!statusFilter || !typeFilter) return;

    const statusValue = statusFilter.value;
    const typeValue = typeFilter.value;

    const table = document.getElementById('pflichtTable') || document.getElementById('allGroupsPflichtTable');
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        let shouldShow = true;

        // Status-Filter anwenden
        if (statusValue !== 'all') {
            const statusCells = row.querySelectorAll('td:not(:first-child)'); // Alle Zellen außer der ersten (Aufgabenname)
            let hasMatchingStatus = false;

            statusCells.forEach(cell => {
                const cellText = cell.textContent.trim();

                if (statusValue === 'completed') {
                    // Zeige nur Zeilen mit mindestens einer eingereichten Aufgabe
                    if (cellText.includes('Nicht eingereicht')) {
                        // Zelle ist nicht eingereicht
                    } else if (cellText !== '') {
                        // Zelle hat eine Note/Status, also eingereicht
                        hasMatchingStatus = true;
                    }
                } else if (statusValue === 'pending') {
                    // Zeige nur Zeilen mit mindestens einer nicht eingereichten Aufgabe
                    if (cellText.includes('Nicht eingereicht')) {
                        hasMatchingStatus = true;
                    }
                }
            });

            if (!hasMatchingStatus) shouldShow = false;
        }

        // Typ-Filter anwenden
        if (typeValue !== 'all' && shouldShow) {
            const firstCell = row.querySelector('td:first-child');
            if (firstCell) {
                const cellText = firstCell.textContent.trim();

                if (typeValue === 'quiz') {
                    if (!cellText.includes('🧭') && !cellText.toLowerCase().includes('quiz')) {
                        shouldShow = false;
                    }
                } else if (typeValue === 'assignment') {
                    if (!cellText.includes('📝') && !cellText.toLowerCase().includes('aufgabe')) {
                        shouldShow = false;
                    }
                }
            }
        }

        row.style.display = shouldShow ? '' : 'none';
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

function getCellValue(row, columnIndex, dataType) {
    const cell = row.cells[columnIndex];
    if (!cell) return '';

    let value = cell.textContent.trim();

    // Spezielle Behandlung für Aufgaben-Titel: Emojis entfernen für die Sortierung
    if (columnIndex === 0) {
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
        header.onclick = () => sortTable(tableId, index);
    });
}

// Initial laden beim Start
document.addEventListener('DOMContentLoaded', function() {
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

// ============= ZENTRALE LEISTUNGSNACHWEISE FUNKTIONEN =============

// Zentrale Leistungsnachweise-Tabelle generieren (Zeilen = Aufgaben, Spalten = Benutzer)
function generateZentralTable() {
    const container = document.getElementById('zentralData');

    // Bei "Alle Gruppen" verwende die spezielle Funktion
    if (currentGroup === 'all') {
        generateAllGroupsZentralTable();
        return;
    }

    // Für einzelne Gruppen: Filtere Daten nach Gruppe (gleiche Logik wie generatePflichtTableFromActivities)
    console.log('DEBUG ZENTRAL: Verfügbare Gruppen:', Object.keys(dashboardData.groups || {}));
    console.log('DEBUG ZENTRAL: Gewählte Gruppe:', currentGroup);

    if (!dashboardData.groups || !dashboardData.groups[currentGroup]) {
        container.innerHTML = `<p>Gruppe "${currentGroup}" nicht gefunden.</p>
                               <p>Verfügbare Gruppen: ${Object.keys(dashboardData.groups || {}).join(', ')}</p>`;
        return;
    }

    // Zeige nur "Zentrale Leistungsnachweise" Kategorien (Kategorie-Filter entfernt)
    const categoriesToShow = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Zentrale Leistungsnachweise') || category.category_name.includes('📊'))
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

    console.log('DEBUG ZENTRAL: Gefundene Kategorien:', categoriesToShow.length);
    console.log('DEBUG ZENTRAL: Alle Aktivitäten:', allActivities.length);

    // Debug: Suche nach Review-Talk 1
    const reviewTalkActivities = allActivities.filter(activity =>
        activity.title && activity.title.includes('Review-Talk 1')
    );
    console.log('🔍 DEBUG: Review-Talk 1 activities found:', reviewTalkActivities.length);
    reviewTalkActivities.forEach(activity => {
        console.log('🔍 Review-Talk 1 activity:', {
            title: activity.title,
            activity_type: activity.activity_type,
            user_status_count: activity.user_status ? activity.user_status.length : 0,
            user_status: activity.user_status
        });
    });

    // Benutzer der ausgewählten Gruppe (gleiche Logik wie Pflichtaufgaben)
    const groupUsers = dashboardData.groups[currentGroup].users || [];
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
        groupUserNames.add(userName);
        console.log('DEBUG ZENTRAL: User object:', user, 'extracted name:', userName);
    });

    console.log('DEBUG ZENTRAL: Gruppe', currentGroup, 'hat', groupUsers.length, 'Benutzer, extrahierte Namen:', Array.from(groupUserNames));

    // Aktivitäten filtern um nur Benutzer aus der aktuellen Gruppe zu zeigen
    const filteredActivities = allActivities.map(activity => ({
        ...activity,
        user_status: activity.user_status ? activity.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(activity => activity.user_status.length > 0);

    console.log('DEBUG ZENTRAL: Nach Filterung:', filteredActivities.length, 'Aktivitäten übrig');

    if (filteredActivities.length === 0) {
        container.innerHTML = `<p>Keine Zentrale Leistungsnachweise für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>
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
    const sortedUsers = Array.from(allUsers).sort();

    console.log('DEBUG ZENTRAL: Gefundene Benutzer:', sortedUsers);

    let html = '<div style="overflow-x: auto;"><table id="zentralTable" class="info-table dashboard-table">';
    html += '<thead><tr>';

    // Header: Aufgabe + Benutzernamen
    html += '<th style="min-width: 250px;">Aufgabe</th>';

    // Für jeden Benutzer eine Spalte mit Zeilenumbruch bei erstem Leerzeichen
    sortedUsers.forEach(userName => {
        const displayName = userName.replace(' ', '<br>');
        html += `<th style="min-width: 120px; text-align: center;">${displayName}</th>`;
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
                console.log(`DEBUG ZENTRAL: No status found for ${activity.activity_type} "${activity.title}" for user ${userName}`);
                cellContent = '❓ Nicht gefunden';
                cellClass = 'status-missing';
                bgColor = '#f8f9fa'; // Grau
            } else if (status.status === 'Nicht eingereicht' || !status.status) {
                // Nicht eingereicht - zeige "-"
                cellContent = '❌ -';
                cellClass = 'status-missing';
                bgColor = '#f8d7da'; // Rot
            } else if (status.grade && status.grade !== '-') {
                // Grade vorhanden - zeige Grade-Wert
                console.log(`DEBUG ZENTRAL: Grade found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.grade}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 GRADE SUCCESS: Review-Talk 1 grade found for ${userName}: ${status.grade}`);
                }
                cellContent = `✓ ${status.grade}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                console.log(`DEBUG ZENTRAL: Rating found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.rating}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 RATING SUCCESS: Review-Talk 1 rating found for ${userName}: ${status.rating}`);
                }
                cellContent = `✓ ${status.rating}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                console.log(`DEBUG ZENTRAL: Score found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.score}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 SCORE SUCCESS: Review-Talk 1 score found for ${userName}: ${status.score}`);
                }
                cellContent = `✓ ${status.score}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.points && status.points !== '-' && status.points !== null) {
                // Alternative: Points field for assignments
                console.log(`DEBUG ZENTRAL: Points found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.points}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 POINTS SUCCESS: Review-Talk 1 points found for ${userName}: ${status.points}`);
                }
                cellContent = `✓ ${status.points}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.result && status.result !== '-' && status.result !== null) {
                // Alternative: Result field for assignments
                console.log(`DEBUG ZENTRAL: Result found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.result}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 RESULT SUCCESS: Review-Talk 1 result found for ${userName}: ${status.result}`);
                }
                cellContent = `✓ ${status.result}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.mark && status.mark !== '-' && status.mark !== null) {
                // Alternative: Mark field for assignments
                console.log(`DEBUG ZENTRAL: Mark found for ${activity.activity_type} "${activity.title}" for user ${userName}: ${status.mark}`);
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🎯 MARK SUCCESS: Review-Talk 1 mark found for ${userName}: ${status.mark}`);
                }
                cellContent = `✓ ${status.mark}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                // Zur Bewertung abgegeben - zeige "abgegeben"
                cellContent = '⏳ abgegeben';
                cellClass = 'status-submitted';
                bgColor = '#fff3cd'; // Gelb
            } else {
                // Andere Status - Debug ALL possible grade fields
                console.log(`DEBUG ZENTRAL: Other status for ${activity.activity_type} "${activity.title}" for user ${userName}:`, {
                    status: status.status,
                    grade: status.grade,
                    rating: status.rating,
                    score: status.score,
                    points: status.points,
                    result: status.result,
                    mark: status.mark,
                    fullStatus: status
                });

                // Spezielle Debug-Ausgabe für Review-Talk 1
                if (activity.title && activity.title.includes('Review-Talk 1')) {
                    console.log(`🔍 SPECIAL DEBUG: Review-Talk 1 found for user ${userName}:`, {
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
                bgColor = '#e2e3e5'; // Grau
            }

            html += `<td class="${cellClass}" style="text-align: center; background-color: ${bgColor};">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('zentralTable');

    // Filter anwenden falls nötig
    applyZentralViewFilters();
}

// Zentrale Leistungsnachweise für alle Gruppen (Zeilen = Benutzer, Spalten = Leistungsnachweise)
function generateAllGroupsZentralTable() {
    const container = document.getElementById('zentralData');
    if (!container || !dashboardData || !dashboardData.activities_by_category) return;

    console.log('DEBUG ALL GROUPS ZENTRAL: Starting generateAllGroupsZentralTable');

    // Zeige nur "Zentrale Leistungsnachweise" Kategorien (Kategorie-Filter entfernt)
    const categoriesToShow = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Zentrale Leistungsnachweise') || category.category_name.includes('📊'))
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

    console.log('DEBUG ALL GROUPS ZENTRAL: Gefundene Aktivitäten:', allActivities.length);

    if (allActivities.length === 0) {
        container.innerHTML = '<p>Keine Zentrale Leistungsnachweise verfügbar.</p>';
        return;
    }

    // Sammle alle Benutzer aus allen Gruppen
    const allUsers = new Map(); // fullUserKey -> { userName, groupName, userId }
    if (dashboardData.groups) {
        Object.keys(dashboardData.groups).forEach(groupName => {
            // Überspringe ignorierte Gruppen
            if (dashboardData.ignored_groups && dashboardData.ignored_groups.includes(groupName)) {
                console.log(`DEBUG ALL GROUPS ZENTRAL: Skipping ignored group: ${groupName}`);
                return;
            }

            const groupUsers = dashboardData.groups[groupName].users || [];
            groupUsers.forEach(user => {
                const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
                const userId = user.user_id;
                const fullUserKey = `${userName} (${groupName})`;

                allUsers.set(fullUserKey, {
                    userName: userName,
                    groupName: groupName,
                    userId: userId
                });
            });
        });
    }

    console.log('DEBUG ALL GROUPS ZENTRAL: Gefundene Benutzer:', allUsers.size);

    // Sortiere Aktivitäten alphabetisch
    const sortedActivities = allActivities.sort((a, b) => a.title.localeCompare(b.title));

    // Sortiere Users alphabetisch
    const sortedUsers = Array.from(allUsers.values()).sort((a, b) => {
        const nameA = `${a.userName} (${a.groupName})`;
        const nameB = `${b.userName} (${b.groupName})`;
        return nameA.localeCompare(nameB);
    });

    let html = '<div style="overflow-x: auto;"><table id="allGroupsZentralTable" class="info-table dashboard-table">';
    html += '<thead><tr>';

    // Header: Benutzer + Gruppe + alle Activities
    html += '<th style="min-width: 180px;">Benutzer</th>';
    html += '<th style="min-width: 120px;">Gruppe</th>';

    sortedActivities.forEach(activity => {
        const typeIcon = activity.activity_type === 'quiz' ? '🧭' : '📝';
        const shortTitle = activity.title.length > 12 ?
            activity.title.substring(0, 12) + '...' : activity.title;

        html += `<th style="min-width: 100px; text-align: center;" title="${typeIcon} ${activity.title}">`;
        html += `<a href="${activity.url}" target="_blank">${typeIcon}<br>${shortTitle}</a>`;
        html += `</th>`;
    });
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jeden Benutzer
    sortedUsers.forEach(user => {
        html += '<tr>';

        // Benutzername mit Zeilenumbruch
        const displayName = user.userName.replace(' ', '<br>');
        html += `<td style="min-width: 180px; font-weight: 500;">${displayName}</td>`;

        // Gruppenname
        html += `<td style="min-width: 120px;">${user.groupName}</td>`;

        // Status für jede Activity (gleiche Logik wie einzelne Gruppen)
        sortedActivities.forEach(activity => {
            // Finde den Status für diesen Benutzer (gleiche Logik wie generateZentralTable)
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
                cellClass = 'status-missing';
                bgColor = '#f8f9fa'; // Grau
            } else if (status.status === 'Nicht eingereicht' || !status.status) {
                cellContent = '❌';
                cellClass = 'status-missing';
                bgColor = '#f8d7da'; // Rot
            } else if (status.grade && status.grade !== '-') {
                console.log(`DEBUG ZENTRAL ALL: Grade found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.grade}`);
                cellContent = `✓<br>${status.grade}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                console.log(`DEBUG ZENTRAL ALL: Rating found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.rating}`);
                cellContent = `✓<br>${status.rating}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                console.log(`DEBUG ZENTRAL ALL: Score found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.score}`);
                cellContent = `✓<br>${status.score}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.points && status.points !== '-' && status.points !== null) {
                // Alternative: Points field for assignments
                console.log(`DEBUG ZENTRAL ALL: Points found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.points}`);
                cellContent = `✓<br>${status.points}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.result && status.result !== '-' && status.result !== null) {
                // Alternative: Result field for assignments
                console.log(`DEBUG ZENTRAL ALL: Result found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.result}`);
                cellContent = `✓<br>${status.result}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.mark && status.mark !== '-' && status.mark !== null) {
                // Alternative: Mark field for assignments
                console.log(`DEBUG ZENTRAL ALL: Mark found for ${activity.activity_type} "${activity.title}" for user ${user.userName}: ${status.mark}`);
                cellContent = `✓<br>${status.mark}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                cellContent = '⏳';
                cellClass = 'status-submitted';
                bgColor = '#fff3cd'; // Gelb
            } else {
                cellContent = '?';
                cellClass = 'status-other';
                bgColor = '#e2e3e5'; // Grau
            }

            html += `<td class="${cellClass}" style="text-align: center; background-color: ${bgColor}; font-size: 12px;">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsZentralTable');

    // Filter anwenden
    applyZentralViewFilters();
}

// Filter für Zentrale Leistungsnachweise anwenden
function applyZentralFilters() {
    generateZentralTable();
    // Status- und Typ-Filter anwenden
    applyZentralViewFilters();
}

// Status- und Typ-Filter für Zentrale Leistungsnachweise anwenden
function applyZentralViewFilters() {
    const statusFilter = document.getElementById('zentralStatusFilter');
    const typeFilter = document.getElementById('zentralTypeFilter');

    if (!statusFilter || !typeFilter) return;

    const statusValue = statusFilter.value;
    const typeValue = typeFilter.value;

    const table = document.getElementById('zentralTable') || document.getElementById('allGroupsZentralTable');
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
function addPflichtaufgabenGradeCalculation() {
    const table = document.getElementById('pflichtTable');
    if (!table) return;

    // Prüfe ob bereits eine Notenzeile existiert
    const existingGradeRow = table.querySelector('.pflicht-grade-row');
    if (existingGradeRow) {
        existingGradeRow.remove();
    }

    const thead = table.querySelector('thead');
    if (!thead) return;

    // Berechne Noten für alle Benutzer und füge sie im Header hinzu
    const gradeRow = createPflichtaufgabenGradeHeaderRow();
    thead.appendChild(gradeRow);
}

// Erstelle eine Header-Zeile mit berechneten Noten für Pflichtaufgaben
function createPflichtaufgabenGradeHeaderRow() {
    const table = document.getElementById('pflichtTable');
    const headers = table.querySelectorAll('thead th');

    const row = document.createElement('tr');
    row.className = 'pflicht-grade-row sticky-header';
    row.style.backgroundColor = '#e8f4fd';
    row.style.fontWeight = 'bold';
    row.style.borderTop = '2px solid #007bff';

    // Erste Spalte: "Durchschnittsnote"
    const labelCell = document.createElement('th');
    labelCell.textContent = '📊 Durchschnittsnote';
    labelCell.style.fontWeight = 'bold';
    labelCell.style.color = '#007bff';
    labelCell.style.backgroundColor = '#e8f4fd';
    row.appendChild(labelCell);

    // Für jeden Benutzer eine Note berechnen (alle Spalten außer der ersten)
    for (let i = 1; i < headers.length; i++) {
        const gradeCell = document.createElement('th');
        gradeCell.style.textAlign = 'center';
        gradeCell.style.fontWeight = 'bold';
        gradeCell.style.backgroundColor = '#e8f4fd';

        const gradeResult = calculatePflichtaufgabenGradeForUser(i - 1); // i-1 weil erste Spalte der Aufgabenname ist

        if (gradeResult !== null && gradeResult.grade !== null) {
            gradeCell.textContent = `${gradeResult.grade.toFixed(1)} (${gradeResult.percent.toFixed(1)}%, n=${gradeResult.count})`;
            gradeCell.style.color = getGradeColor(gradeResult.grade);
            gradeCell.title = `Durchschnitt: ${gradeResult.percent.toFixed(1)}% aus ${gradeResult.count} bewerteten Aufgaben`;
        } else {
            gradeCell.textContent = 'n/a';
            gradeCell.style.color = '#6c757d';
            gradeCell.title = 'Keine bewerteten Aufgaben vorhanden';
        }

        row.appendChild(gradeCell);
    }

    return row;
}

// Berechne die Note für einen bestimmten Benutzer basierend auf allen bewerteten Pflichtaufgaben
function calculatePflichtaufgabenGradeForUser(userIndex) {
    const table = document.getElementById('pflichtTable');
    if (!table) return null;

    const rows = table.querySelectorAll('tbody tr:not(.pflicht-grade-row)');
    let totalPercent = 0;
    let count = 0; // Expliziter Zähler

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length > userIndex + 1) { // +1 weil erste Spalte der Aufgabenname ist
            const userCell = cells[userIndex + 1];
            const percent = extractPercentageFromCell(userCell);

            if (percent !== null) {
                totalPercent += percent;
                count++; // Zähle jede gefundene Bewertung
            }
        }
    });

    if (count === 0) return null;

    // Durchschnitt der Prozentwerte berechnen
    const averagePercent = totalPercent / count;

    // Erst jetzt in IHK-Note umwandeln
    const grade = convertPercentToIHKGrade(averagePercent);

    return {
        grade: grade,
        percent: averagePercent,
        count: count
    };
}

// Berechne Pflichtaufgaben-Durchschnittsnote für einen Benutzer basierend auf activities_by_category
function calculatePflichtaufgabenGradeForUserByName(userName, groupName) {
    if (!dashboardData || !dashboardData.activities_by_category) {
        console.log('DEBUG calculatePflichtaufgabenGradeForUserByName: No dashboard data or activities_by_category');
        return null;
    }

    let totalPercent = 0;
    let count = 0; // Expliziter Zähler

    // Finde Pflichtaufgaben-Kategorie(n)
    const pflichtCategories = dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
    );

    console.log(`DEBUG calculatePflichtaufgabenGradeForUserByName: Found ${pflichtCategories.length} Pflicht categories for user ${userName}`);

    // Durchlaufe alle Pflichtaufgaben-Kategorien
    pflichtCategories.forEach(category => {
        // Prüfe Assignments
        if (category.assignments) {
            category.assignments.forEach(assignment => {
                if (assignment.user_status) {
                    const userStatus = assignment.user_status.find(status => status.user_name === userName);
                    if (userStatus && userStatus.grade) {
                        console.log(`DEBUG: Processing assignment "${assignment.title}" for ${userName}, grade value: "${userStatus.grade}"`);
                        const percent = extractPercentageFromString(userStatus.grade);
                        if (percent !== null) {
                            console.log(`DEBUG: ✓ Found ${percent}% for ${userName} in assignment ${assignment.title}`);
                            totalPercent += percent;
                            count++; // Zähle jede gefundene Bewertung
                        } else {
                            console.log(`DEBUG: ✗ Could not extract percentage from "${userStatus.grade}" for ${userName} in assignment ${assignment.title}`);
                        }
                    }
                }
            });
        }

        // Prüfe Quizzes
        if (category.quizzes) {
            category.quizzes.forEach(quiz => {
                if (quiz.user_status) {
                    const userStatus = quiz.user_status.find(status => status.user_name === userName);
                    if (userStatus && userStatus.grade) {
                        console.log(`DEBUG: Processing quiz "${quiz.title}" for ${userName}, grade value: "${userStatus.grade}"`);
                        const percent = extractPercentageFromString(userStatus.grade);
                        if (percent !== null) {
                            console.log(`DEBUG: ✓ Found ${percent}% for ${userName} in quiz ${quiz.title}`);
                            totalPercent += percent;
                            count++; // Zähle jede gefundene Bewertung
                        } else {
                            console.log(`DEBUG: ✗ Could not extract percentage from "${userStatus.grade}" for ${userName} in quiz ${quiz.title}`);
                        }
                    }
                }
            });
        }
    });

    console.log(`DEBUG calculatePflichtaufgabenGradeForUserByName: User ${userName} has ${count} graded items`);

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
                console.log(`DEBUG: ✓ MATCH! Returning score ${entry.score} for "${entry.label}"`);
                return entry.score; // Gib den Prozentwert zurück (z.B. 70 für "** Verbesserungsbedarf", 100 für "*** Solide Umsetzung")
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
                console.log(`DEBUG: Returning ${result} based on ${starCount} stars`);
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

    // Prüfe auf Punktzahlen (z.B. "8/10")
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

    // Prüfe auf Punktzahlen (z.B. "8/10")
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
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

    // Debug für Bastian Brenner
    const isDebugCell = content && !content.includes('Nicht eingereicht') && !content.includes('bewertbar');
    if (isDebugCell) {
        console.log('DEBUG extractGradeFromCell:');
        console.log('  textContent:', content);
        console.log('  innerHTML:', innerHTML);
    }

    // Prüfe auf Sterne-Bewertungen basierend auf GradeMapping aus config.ini
    if (content.includes('*')) {
        if (isDebugCell) console.log('  -> Found star rating');
        return convertStarRatingToGrade(content);
    }

    // Prüfe auf direkte Notenwerte in <strong> Tags (z.B. Assignment-Noten und Quiz-Ergebnisse)
    const strongMatch = innerHTML.match(/<strong>([^<]+)<\/strong>/);
    if (strongMatch) {
        const gradeText = strongMatch[1].trim();
        if (isDebugCell) console.log('  -> Found strong tag:', gradeText);

        // Prüfe auf Prozentwerte
        const percentMatch = gradeText.match(/(\d+(?:\.\d+)?)%/);
        if (percentMatch) {
            const percent = parseFloat(percentMatch[1]);
            if (isDebugCell) console.log('  -> Extracted percentage from strong:', percent);
            return convertPercentToIHKGrade(percent);
        }

        // Prüfe auf direkte Notenwerte oder Prozentwerte ohne % Zeichen
        const gradeMatch = gradeText.match(/^(\d+(?:[.,]\d+)?)$/);
        if (gradeMatch) {
            const value = parseFloat(gradeMatch[1].replace(',', '.'));

            // Noten zwischen 1.0 und 6.0
            if (value >= 1.0 && value <= 6.0) {
                if (isDebugCell) console.log('  -> Extracted direct grade from strong:', value);
                return value;
            }

            // Zahlen > 6 als Prozentwerte interpretieren (Quiz-Ergebnisse ohne % Zeichen)
            if (value > 6 && value <= 100) {
                if (isDebugCell) console.log('  -> Treating number as percentage from strong:', value);
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
                if (isDebugCell) console.log('  -> Calculated percentage from points in strong:', percent);
                return convertPercentToIHKGrade(percent);
            }
        }
    }

    // Prüfe auf Prozentwerte (sowohl für Assignments als auch Quizzes)
    const percentMatch = content.match(/(\d+(?:\.\d+)?)%/);
    if (percentMatch) {
        const percent = parseFloat(percentMatch[1]);
        if (isDebugCell) console.log('  -> Found percentage:', percent);
        return convertPercentToIHKGrade(percent);
    }

    // Prüfe auf Quiz-Ergebnisse mit Punktzahl (z.B. "8/10 (80%)")
    const quizMatch = content.match(/\d+\/\d+\s*\((\d+(?:\.\d+)?)%\)/);
    if (quizMatch) {
        const percent = parseFloat(quizMatch[1]);
        if (isDebugCell) console.log('  -> Found quiz with percentage:', percent);
        return convertPercentToIHKGrade(percent);
    }

    // Prüfe auf Punktzahl ohne Prozentwert (z.B. "8/10")
    const pointsMatch = content.match(/(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)/);
    if (pointsMatch) {
        const achieved = parseFloat(pointsMatch[1]);
        const total = parseFloat(pointsMatch[2]);
        if (total > 0) {
            const percent = (achieved / total) * 100;
            if (isDebugCell) console.log('  -> Calculated percentage from points:', percent);
            return convertPercentToIHKGrade(percent);
        }
    }

    // Prüfe auf direkte Notenwerte (z.B. "2,5" oder "1.0")
    const gradeMatch = content.match(/^(\d+(?:[.,]\d+)?)$/);
    if (gradeMatch) {
        const grade = parseFloat(gradeMatch[1].replace(',', '.'));
        if (grade >= 1.0 && grade <= 6.0) {
            if (isDebugCell) console.log('  -> Found direct grade:', grade);
            return grade;
        }
    }

    if (isDebugCell) console.log('  -> No grade found, returning null');

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
function addPflichtaufgabenGradeCalculationForAllGroups() {
    const table = document.getElementById('allGroupsPflichtTable');
    if (!table) return;

    // Prüfe ob bereits eine Notenzeile existiert
    const existingGradeRow = table.querySelector('.pflicht-grade-row');
    if (existingGradeRow) {
        existingGradeRow.remove();
    }

    const thead = table.querySelector('thead');
    if (!thead) return;

    // Berechne Noten für alle Benutzer und füge sie im Header hinzu
    const gradeRow = createPflichtaufgabenGradeHeaderRowForAllGroups();
    thead.appendChild(gradeRow);
}

// Erstelle eine Header-Zeile mit berechneten Noten für Pflichtaufgaben (Alle Gruppen)
function createPflichtaufgabenGradeHeaderRowForAllGroups() {
    const table = document.getElementById('allGroupsPflichtTable');
    const headers = table.querySelectorAll('thead th');

    const row = document.createElement('tr');
    row.className = 'pflicht-grade-row sticky-header';
    row.style.backgroundColor = '#e8f4fd';
    row.style.fontWeight = 'bold';
    row.style.borderTop = '2px solid #007bff';

    // Erste Spalte: "Durchschnittsnote"
    const labelCell = document.createElement('th');
    labelCell.textContent = '📊 Durchschnittsnote';
    labelCell.style.fontWeight = 'bold';
    labelCell.style.color = '#007bff';
    labelCell.style.backgroundColor = '#e8f4fd';
    row.appendChild(labelCell);

    // Für jeden Benutzer eine Note berechnen (alle Spalten außer der ersten)
    for (let i = 1; i < headers.length; i++) {
        const gradeCell = document.createElement('th');
        gradeCell.style.textAlign = 'center';
        gradeCell.style.fontWeight = 'bold';
        gradeCell.style.backgroundColor = '#e8f4fd';

        const gradeResult = calculatePflichtaufgabenGradeForUserAllGroups(i - 1); // i-1 weil erste Spalte der Aufgabenname ist

        if (gradeResult !== null && gradeResult.grade !== null) {
            gradeCell.textContent = `${gradeResult.grade.toFixed(1)} (${gradeResult.percent.toFixed(1)}%, n=${gradeResult.count})`;
            gradeCell.style.color = getGradeColor(gradeResult.grade);
            gradeCell.title = `Durchschnitt: ${gradeResult.percent.toFixed(1)}% aus ${gradeResult.count} bewerteten Aufgaben`;
        } else {
            gradeCell.textContent = 'n/a';
            gradeCell.style.color = '#6c757d';
            gradeCell.title = 'Keine bewerteten Aufgaben vorhanden';
        }

        row.appendChild(gradeCell);
    }

    return row;
}

// Berechne die Note für einen bestimmten Benutzer basierend auf allen bewerteten Pflichtaufgaben (Alle Gruppen)
function calculatePflichtaufgabenGradeForUserAllGroups(userIndex) {
    const table = document.getElementById('allGroupsPflichtTable');
    if (!table) return null;

    const rows = table.querySelectorAll('tbody tr:not(.pflicht-grade-row)');
    let totalPercent = 0;
    let count = 0; // Expliziter Zähler

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length > userIndex + 1) { // +1 weil erste Spalte der Aufgabenname ist
            const userCell = cells[userIndex + 1];
            const percent = extractPercentageFromCell(userCell);

            if (percent !== null) {
                totalPercent += percent;
                count++; // Zähle jede gefundene Bewertung
            }
        }
    });

    if (count === 0) return null;

    // Durchschnitt der Prozentwerte berechnen
    const averagePercent = totalPercent / count;

    // Erst jetzt in IHK-Note umwandeln
    const grade = convertPercentToIHKGrade(averagePercent);

    return {
        grade: grade,
        percent: averagePercent,
        count: count
    };
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
    console.log('DEBUG: New function - collecting activities...');
    console.log('DEBUG: Categories to show:', categoriesToShow.length);

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

    console.log('DEBUG: Total activities collected:', allActivities.length);
    console.log('DEBUG: Activity types:', allActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

    // ZUSÄTZLICH: Versuche Quiz-Daten aus anderen Quellen zu extrahieren
    if (dashboardData.structured_tables && dashboardData.structured_tables[currentGroup]) {
        console.log('DEBUG: Searching for quiz data in structured_tables...');
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

        console.log('DEBUG: After adding structured_tables quizzes - Total activities:', allActivities.length);
        console.log('DEBUG: Updated activity types:', allActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

        // ZUSÄTZLICH: Durchsuche Checklisten-Daten nach Quiz-ähnlichen Aktivitäten
        if (structuredData.checklists && structuredData.checklists.rows) {
            console.log('DEBUG: Searching checklists for quiz-like activities...');
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
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name;
        if (userName) {
            groupUserNames.add(userName);
        }
    });

    // Filtere Aktivitäten, um nur Benutzer aus der aktuellen Gruppe zu zeigen
    console.log('DEBUG: Group user names:', Array.from(groupUserNames));
    const filteredActivities = allActivities.map(activity => ({
        ...activity,
        user_status: activity.user_status ? activity.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(activity => activity.user_status.length > 0);

    console.log('DEBUG: Filtered activities:', filteredActivities.length);
    console.log('DEBUG: Filtered activity types:', filteredActivities.reduce((acc, a) => { acc[a.activity_type] = (acc[a.activity_type] || 0) + 1; return acc; }, {}));

    // Debug: Zeige erste paar Aktivitäten
    filteredActivities.slice(0, 3).forEach((activity, index) => {
        console.log(`DEBUG: Activity ${index}: "${activity.title}" (${activity.activity_type}) - users: ${activity.user_status.length}`);
    });

    if (filteredActivities.length === 0) {
        container.innerHTML = `<p>Keine Daten für die ausgewählte Gruppe "${currentGroup}" verfügbar.</p>`;
        return;
    }

    // HTML generieren (gleiche Logik wie einzelne Gruppe)
    let html = '<div style="overflow-x: auto;"><table id="pflichtTable" class="info-table dashboard-table">';
    html += '<thead><tr><th style="min-width: 250px;">Pflichtaufgabe</th>';

    // Header für alle Benutzer der Gruppe
    groupUsers.forEach(user => {
        const userName = user.user_name || user.name || user.username || user.display_name || 'Unbekannt';
        html += `<th style="text-align: center; min-width: 120px;">${userName}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Zeilen für jede Aktivität
    filteredActivities.forEach(activity => {
        html += '<tr>';
        html += `<td style="min-width: 250px;">`;
        const activityIcon = activity.activity_type === 'quiz' ? '🧭' : '📝';
        const activityType = activity.activity_type === 'quiz' ? 'Quiz' : 'Aufgabe';
        html += `<a href="${activity.url}" target="_blank">${activityIcon} ${activity.title}</a>`;
        html += `<br><small style="color: #666;">Typ: ${activityType} | Kategorie: ${activity.category_name || 'Unbekannt'}</small>`;
        html += `</td>`;

        // Status für jeden Benutzer der Gruppe
        groupUsers.forEach(user => {
            let status = null;
            if (activity.user_status) {
                const userId = user.user_id || user.id;
                const userName = user.user_name || user.name || user.username || user.display_name;

                status = activity.user_status.find(s =>
                    (s.user_id && userId && s.user_id === userId) ||
                    (s.user_name && userName && s.user_name === userName)
                );
            }

            let cellContent = '';
            let cellClass = 'progress-cell';
            let bgColor = '';

            if (status && status.grade && status.grade !== '-') {
                cellContent = `<strong>${status.grade}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.rating && status.rating !== '-') {
                // Alternative: Rating field for assignments
                cellContent = `<strong>${status.rating}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.score && status.score !== '-') {
                // Alternative: Score field for assignments
                cellContent = `<strong>${status.score}</strong>`;
                bgColor = '--progress-width: 100%; --progress-color: #28a745;';
            } else if (status && status.status === 'Zur Bewertung abgegeben') {
                cellContent = '<span style="color: #ffc107;">bewertbar</span>';
                bgColor = '--progress-width: 50%; --progress-color: #ffc107;';
            } else {
                cellContent = '<span style="color: #dc3545;">Nicht eingereicht</span>';
                bgColor = '--progress-width: 0%; --progress-color: #dc3545;';
            }

            html += `<td class="${cellClass}" style="${bgColor} text-align: center;">${cellContent}</td>`;
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('pflichtTable');

    // Notenberechnung für Pflichtaufgaben hinzufügen
    addPflichtaufgabenGradeCalculation();

    // Sortierung anwenden
    const table = document.getElementById('pflichtTable');
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            rows.sort((a, b) => {
                const aVal = getSortValue(a, 0);
                const bVal = getSortValue(b, 0);

                if (aVal.match(/^\d+(\.\d+)?$/) && bVal.match(/^\d+(\.\d+)?$/)) {
                    return parseFloat(aVal) - parseFloat(bVal);
                } else {
                    return aVal.localeCompare(bVal);
                }
            });

            rows.forEach(row => tbody.appendChild(row));

            const headers = table.querySelectorAll('th');
            if (headers[0]) {
                headers[0].classList.add('sort-asc');
            }

            sortState['pflichtTable_0'] = 'asc';
        }
    }
}