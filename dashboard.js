// Dashboard JavaScript
let dashboardData = null;
let currentGroup = 'all';
let currentGrouping = 'all'; // New: current grouping selection
let currentWeek = 10;
let totalWeeks = 40;
let checklistViewType = 'both'; // New: track checklist column view setting
let sortState = {}; // Track sorting state for different tables

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

        // Debug: JSON-Struktur analysieren
        console.log('=== DASHBOARD DATA LOADED ===');
        console.log('Data structure:', {
            hasActivitiesByCategory: !!dashboardData.activities_by_category,
            categoriesCount: dashboardData.activities_by_category ? dashboardData.activities_by_category.length : 'undefined',
            sampleCategory: dashboardData.activities_by_category ? dashboardData.activities_by_category[0] : 'none'
        });

        if (dashboardData.activities_by_category && dashboardData.activities_by_category.length > 0) {
            const firstCategory = dashboardData.activities_by_category[0];
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
    const avgRequiredProgress = users.reduce((sum, user) => sum + user.checklists.avg_required_progress, 0) / totalUsers;
    const avgAllProgress = users.reduce((sum, user) => sum + user.checklists.avg_all_progress, 0) / totalUsers;
    const avgRequiredProgressTimed = users.reduce((sum, user) => sum + user.checklists.avg_required_progress_timed, 0) / totalUsers;
    const avgAllProgressTimed = users.reduce((sum, user) => sum + user.checklists.avg_all_progress_timed, 0) / totalUsers;

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
    const maxWeeks = 10; // Entspricht dem max-Wert des Sliders

    // Durchschnittliche erledigte Anzahl pro Person berechnen
    const avgCompletedChecklists = users.length > 0 ?
        users.reduce((sum, user) => sum + user.checklists.required_100_count, 0) / users.length : 0;
    const avgCompletedPflichtaufgaben = users.length > 0 ?
        users.reduce((sum, user) => sum + user.assignments.submitted_count, 0) / users.length : 0;

    // Erwartete Anzahl für die ausgewählte Referenzwoche
    // Bei Woche 10 (Maximum) sollten alle Checklisten/Aufgaben erwartet werden
    const expectedChecklistsForWeek = Math.ceil((totalChecklists / maxWeeks) * currentWeek);
    const expectedPflichtaufgabenForWeek = Math.ceil((totalPflichtaufgaben / maxWeeks) * currentWeek);

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
    const currentProgressType = document.querySelector('input[name="progressType"]:checked').value;
    const progressValue = currentProgressType === 'pflicht' ?
        groupStats.checklists.avg_required_progress_timed :
        groupStats.checklists.avg_all_progress_timed;

    document.getElementById('avgCompletionText').textContent = progressValue + '%';
    document.getElementById('avgCompletionBar').style.width = Math.min(progressValue, 100) + '%';

    // Durchschnittsnote
    const avgGradeElement = document.getElementById('avgGradeText');
    if (groupStats.assignments.avg_grade !== null) {
        avgGradeElement.textContent = groupStats.assignments.avg_grade.toFixed(2);
    } else {
        avgGradeElement.textContent = '-';
    }

    // Pflichtaufgaben-Statistiken - zeigt durchschnittlich erledigte vs. erwartete für gewählte Woche
    document.getElementById('pflichtCompletedCount').textContent = avgCompletedPflichtaufgaben.toFixed(1);
    document.getElementById('pflichtTotalCount').textContent = expectedPflichtaufgabenForWeek;
    document.getElementById('pflichtCompletionPercentage').textContent = percentPflichtaufgaben.toFixed(2) + '%';

    // Pflicht Progress Ring aktualisieren
    updateProgressRing('pflichtCompletionRing', Math.min(percentPflichtaufgaben, 100));

    // Durchschnittsnote Pflichtaufgaben
    const pflichtAvgGradeElement = document.getElementById('pflichtAverageGrade');
    if (groupStats.assignments.avg_grade !== null) {
        pflichtAvgGradeElement.textContent = groupStats.assignments.avg_grade.toFixed(2);
    } else {
        pflichtAvgGradeElement.textContent = '-';
    }

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
    const avgRequiredProgress = users.reduce((sum, user) => sum + user.checklists.avg_required_progress, 0) / totalUsers;
    const avgAllProgress = users.reduce((sum, user) => sum + user.checklists.avg_all_progress, 0) / totalUsers;

    // Durchschnittsnote berechnen
    const gradesArray = users
        .map(user => user.assignments.average_grade)
        .filter(grade => grade !== null && grade !== undefined);
    const avgGrade = gradesArray.length > 0 ? gradesArray.reduce((sum, grade) => sum + grade, 0) / gradesArray.length : null;

    // Erwartete Werte für aktuelle Referenzwoche
    const { totalChecklists, totalPflichtaufgaben } = getTotalCounts();
    const maxWeeks = 10; // Entspricht dem max-Wert des Sliders
    const expectedChecklistsForWeek = Math.ceil((totalChecklists / maxWeeks) * currentWeek);
    const expectedPflichtaufgabenForWeek = Math.ceil((totalPflichtaufgaben / maxWeeks) * currentWeek);

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

    let html = '<div style="overflow-x: auto;"><table id="groupComparisonTable" class="info-table dashboard-table comparison-table">';
    html += '<thead><tr class="sticky-header">';
    html += '<th class="group-name-cell">Gruppe</th>';
    html += '<th>Personen</th>';
    html += '<th>Ø Checklisten<br>100%</th>';
    html += '<th>Ø Pflichtaufgaben<br>eingereicht</th>';
    html += '<th>Ø Fortschritt<br>Pflicht %</th>';
    html += '<th>Ø Note</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    // Statistiken für jede Gruppe berechnen und anzeigen
    groupsToShow.forEach(groupName => {
        const groupData = dashboardData.groups[groupName];
        const stats = calculateStatsForGroup(groupName, groupData);

        const gradeText = stats.avgGrade !== null ? stats.avgGrade.toFixed(2) : '-';

        // Zeige die gleichen Werte wie in den Cards:
        // "Ø Checklisten 100%" = avgCompletedChecklists (wie completedCount in der Card)
        // "Ø Pflichtaufgaben eingereicht" = avgCompletedPflichtaufgaben (wie pflichtCompletedCount in der Card)

        html += '<tr>';
        html += `<td class="group-name-cell"><strong>${stats.groupName}</strong></td>`;
        html += `<td style="text-align: center;">${stats.userCount}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(stats.avgCompletedChecklists * 10, 100)}%; --progress-color: #28a745;">${stats.avgCompletedChecklists.toFixed(1)}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(stats.avgCompletedPflichtaufgaben * 10, 100)}%; --progress-color: #fd7e14;">${stats.avgCompletedPflichtaufgaben.toFixed(1)}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${stats.avgRequiredProgress}%; --progress-color: #6f42c1;">${stats.avgRequiredProgress.toFixed(1)}%</td>`;
        html += `<td style="text-align: center; font-weight: bold;">${gradeText}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('groupComparisonTable');
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
    html += '<th>Ø Gesamt (%)</th>';
    html += '<th>Eingereichte Aufgaben</th>';
    html += '<th>Ø Note</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    users.forEach(user => {
        const gradeText = user.assignments.average_grade !== null ?
            user.assignments.average_grade.toFixed(2) : '-';

        html += '<tr>';
        html += `<td class="person-name"><strong>${user.name}</strong></td>`;
        html += `<td class="progress-cell" style="--progress-width: ${Math.min(user.checklists.required_100_count * 10, 100)}%; --progress-color: #28a745;">${user.checklists.required_100_count}</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${user.checklists.avg_required_progress}%; --progress-color: #007bff;">${user.checklists.avg_required_progress}%</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${user.checklists.avg_all_progress}%; --progress-color: #6f42c1;">${user.checklists.avg_all_progress}%</td>`;
        html += `<td class="progress-cell" style="--progress-width: ${user.assignments.percent_submitted}%; --progress-color: #fd7e14;">${user.assignments.submitted_count}</td>`;
        html += `<td style="text-align: center; font-weight: bold;">${gradeText}</td>`;
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

    // Für einzelne Gruppen: Filtere Daten nach Gruppe

    if (!dashboardData.groups || !dashboardData.groups[currentGroup]) {
        container.innerHTML = `<p>Gruppe "${currentGroup}" nicht gefunden.</p>
                               <p>Verfügbare Gruppen: ${Object.keys(dashboardData.groups || {}).join(', ')}</p>`;
        return;
    }

    // Kategorie-Filter anwenden (gleiche Logik wie bei generateAllGroupsPflichtTable)
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

    // Sammle sowohl assignments als auch quizzes aus den gewählten Kategorien
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

    if (assignments.length === 0) {
        container.innerHTML = '<p>Keine Aktivitäten für die gewählte Kategorie verfügbar.</p>';
        return;
    }

    // Benutzer der aktuellen Gruppe sammeln
    const groupUsers = dashboardData.groups[currentGroup].users;

    // Prüfe verschiedene mögliche Benutzer-Name-Felder
    const groupUserNames = new Set();
    groupUsers.forEach(user => {
        // Versuche verschiedene mögliche Felder für den Namen
        const userName = user.user_name || user.name || user.username || user.display_name;
        if (userName) {
            groupUserNames.add(userName);
        }
    });


    // Assignments filtern um nur Benutzer aus der aktuellen Gruppe zu zeigen
    const filteredAssignments = assignments.map(assignment => ({
        ...assignment,
        user_status: assignment.user_status ? assignment.user_status.filter(userStatus =>
            groupUserNames.has(userStatus.user_name)
        ) : []
    })).filter(assignment => assignment.user_status.length > 0);


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

    // Sofortige numerische Sortierung nach Aufgabennummer
    const table = document.getElementById('pflichtTable');
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            // Sortiere Zeilen numerisch nach Aufgabennummer (falls vorhanden), sonst alphabetisch
            rows.sort((a, b) => {
                const aVal = getCellValue(a, 0, 'text');
                const bVal = getCellValue(b, 0, 'text');

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
        groupsToShow = Object.keys(dashboardData.structured_tables);
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

    // Sofortige numerische Sortierung nach Aufgabennummer
    const table = document.getElementById('allGroupsPflichtTable');
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            // Sortiere Zeilen numerisch nach Aufgabennummer (falls vorhanden), sonst alphabetisch
            rows.sort((a, b) => {
                const aVal = getCellValue(a, 0, 'text');
                const bVal = getCellValue(b, 0, 'text');

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
            if (columnIndex === 0 && aVal.match(/^\d+(\.\d+)?$/) && bVal.match(/^\d+(\.\d+)?$/)) {
                result = parseFloat(aVal) - parseFloat(bVal);
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

    let value;

    // Für die erste Spalte: Extrahiere nur den Link-Text, nicht den gesamten Zellinhalt
    if (columnIndex === 0) {
        const link = cell.querySelector('a');
        value = link ? link.textContent.trim() : cell.textContent.trim();
    } else {
        value = cell.textContent.trim();
    }

    // Spezielle Behandlung für Aufgaben-Titel: Numerische Sortierung nach Aufgabennummer
    if (columnIndex === 0) {
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
        value = cleanValue.replace(/^Pflicht:\s*/, '');
    }

    // Spezielle Behandlung für verschiedene Datentypen
    if (dataType === 'number' || value.match(/^[\d.,%-]+$/)) {
        return value.replace(/[^\d.-]/g, '');
    }

    return value;
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

// Zentrale Leistungsnachweise-Tabelle generieren (Zeilen = Personen, Spalten = Aufgaben)
function generateZentralTable() {
    const container = document.getElementById('zentralData');
    if (!container || !dashboardData || !dashboardData.structured_tables) return;

    // Bei "Alle Gruppen" alle Zentrale Leistungsnachweise von allen Benutzern anzeigen
    if (currentGroup === 'all') {
        generateAllGroupsZentralTable();
        return;
    }

    const tableData = dashboardData.structured_tables[currentGroup]?.zentrale_leistungsnachweise;

    if (!tableData) {
        container.innerHTML = '<p>Keine Daten für die ausgewählte Gruppe verfügbar.</p>';
        return;
    }

    // Transponiere die Daten: Von (Aufgaben als Zeilen, Benutzer als Spalten) zu (Benutzer als Zeilen, Aufgaben als Spalten)
    const assignments = tableData.rows;
    const userNames = tableData.headers.slice(1); // Entferne "Aufgabe" Header

    let html = '<div style="overflow-x: auto;"><table id="zentralTable" class="info-table dashboard-table">';
    html += '<thead><tr>';

    // Header: Benutzer + Aufgabentitel
    html += '<th style="min-width: 180px;">Benutzer</th>';

    // Für jede Aufgabe eine Spalte mit Status/Note
    assignments.forEach(assignment => {
        const typeIcon = assignment.assignment_type === 'quiz' ? '🧭' : '📝';
        const fullTitle = `${typeIcon} ${assignment.assignment_title}`;
        const shortTitle = assignment.assignment_title.length > 8 ?
            assignment.assignment_title.substring(0, 8) + '...' :
            assignment.assignment_title;

        html += `<th class="zentral-assignment-header" title="${fullTitle}">`;
        html += `<a href="${assignment.assignment_url}" target="_blank">${typeIcon} ${shortTitle}</a>`;
        html += `<small>Typ: ${assignment.assignment_type === 'quiz' ? 'Quiz' : 'Aufgabe'}</small>`;
        html += `</th>`;
    });
    html += '</tr></thead>';

    html += '<tbody>';

    // Zeilen für jeden Benutzer
    userNames.forEach((userName, userIndex) => {
        html += '<tr>';

        // Benutzername
        html += `<td style="min-width: 180px; font-weight: 500;">${userName}</td>`;

        // Status für jede Aufgabe
        assignments.forEach((assignment, assignmentIndex) => {
            // Debug: Prüfe Assignment-Struktur
            console.log(`Assignment ${assignmentIndex} (${assignment.title}):`, {
                hasUserStatus: !!assignment.user_status,
                userStatusLength: assignment.user_status ? assignment.user_status.length : 'undefined',
                userIndex: userIndex,
                assignmentKeys: Object.keys(assignment)
            });

            // Prüfe ob user_status vorhanden ist
            if (!assignment.user_status || assignment.user_status.length === 0) {
                console.log(`❌ Assignment ${assignment.title}: Keine user_status Daten verfügbar`);
                // Keine user_status Daten verfügbar
                html += `<td style="background-color: #f8f9fa; text-align: center;">
                    <span style="color: #6c757d;">Keine Daten</span>
                </td>`;
                return;
            }

            const status = assignment.user_status[userIndex];
            console.log(`User ${userIndex} (${userName}) - Assignment ${assignment.title}:`, {
                status: status,
                statusValue: status ? status.status : 'undefined',
                grade: status ? status.grade : 'undefined'
            });

            let cellContent = '';
            let cellClass = '';
            let bgColor = '';

            if (status.status === 'Nicht eingereicht' || !status.status) {
                console.log(`🔴 ${userName} - ${assignment.title}: NICHT EINGEREICHT (status: ${status ? status.status : 'undefined'})`);
                // Nicht eingereicht - zeige "-"
                // Nicht eingereicht - zeige "-"
                cellContent = '❌ -';
                cellClass = 'status-missing';
                bgColor = '#f8d7da'; // Rot
            } else if (status.grade && status.grade !== '-') {
                console.log(`🟢 ${userName} - ${assignment.title}: BEWERTET (grade: ${status.grade})`);
                // Grade vorhanden - zeige Grade-Wert
                cellContent = `✓ ${status.grade}`;
                cellClass = 'status-graded';
                bgColor = '#d4edda'; // Grün
            } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                console.log(`🟡 ${userName} - ${assignment.title}: ABGEGEBEN ABER NICHT BEWERTET (status: ${status.status})`);
                // Zur Bewertung abgegeben - zeige "abgegeben"
                // Zur Bewertung abgegeben - zeige "abgegeben"
                cellContent = '⏳ abgegeben';
                cellClass = 'status-submitted';
                bgColor = '#fff3cd'; // Gelb
            } else {
                // Andere Status
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

// Zentrale Leistungsnachweise für alle Gruppen
function generateAllGroupsZentralTable() {
    const container = document.getElementById('zentralData');
    if (!container || !dashboardData || !dashboardData.structured_tables) return;

    let html = '<div style="overflow-x: auto;"><table id="allGroupsZentralTable" class="info-table dashboard-table">';
    html += '<thead><tr>';
    html += '<th style="min-width: 180px;">Benutzer</th>';
    html += '<th style="min-width: 120px;">Gruppe</th>';
    html += '<th style="min-width: 250px;">Zentrale Leistungsnachweis</th>';
    html += '<th style="text-align: center; min-width: 120px;">Status</th>';
    html += '<th style="text-align: center; min-width: 100px;">Note</th>';
    html += '</tr></thead><tbody>';

    // Sammle alle Zentrale Leistungsnachweise von allen Gruppen
    Object.keys(dashboardData.structured_tables).forEach(groupName => {
        const groupData = dashboardData.structured_tables[groupName];
        const tableData = groupData?.zentrale_leistungsnachweise;

        if (!tableData || !tableData.rows) return;

        // Ursprüngliche Struktur: Zeilen sind Aufgaben, transponiere zu Benutzer-Zeilen
        const userNames = tableData.headers.slice(1); // Entferne "Aufgabe" Header

        userNames.forEach((userName, userIndex) => {
            tableData.rows.forEach(assignment => {
                // Prüfe ob user_status vorhanden ist
                if (!assignment.user_status || assignment.user_status.length === 0) {
                    return; // Überspringe Assignment ohne Daten
                }

                const status = assignment.user_status[userIndex];
                const typeIcon = assignment.assignment_type === 'quiz' ? '🧭' : '📝';

                let statusText = '';
                let gradeText = '';
                let rowClass = '';
                let bgColor = '';

                if (status.status === 'Nicht eingereicht' || !status.status) {
                    statusText = 'Offen';
                    gradeText = '-';
                    rowClass = 'status-missing';
                    bgColor = '#f8d7da';
                } else if (status.grade && status.grade !== '-') {
                    statusText = 'Bewertet';
                    gradeText = status.grade;
                    rowClass = 'status-graded';
                    bgColor = '#d4edda';
                } else if (status.status === 'Zur Bewertung abgegeben' || status.status === 'Abgegeben') {
                    statusText = 'abgegeben';
                    gradeText = 'abgegeben';
                    rowClass = 'status-submitted';
                    bgColor = '#fff3cd';
                } else {
                    statusText = status.status || 'Unbekannt';
                    gradeText = '-';
                    rowClass = 'status-other';
                    bgColor = '#e2e3e5';
                }

                html += `<tr class="${rowClass}" style="background-color: ${bgColor};">`;
                html += `<td style="font-weight: 500;">${userName}</td>`;
                html += `<td>${groupName}</td>`;
                html += `<td style="min-width: 250px;">`;
                html += `<a href="${assignment.assignment_url}" target="_blank">${typeIcon} ${assignment.assignment_title}</a>`;
                html += `<br><small style="color: #666;">Typ: ${assignment.assignment_type === 'quiz' ? 'Quiz' : 'Aufgabe'}</small>`;
                html += `</td>`;
                html += `<td style="text-align: center;">${statusText}</td>`;
                html += `<td style="text-align: center;">${gradeText}</td>`;
                html += '</tr>';
            });
        });
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    // Tabelle sortierbar machen
    makeTableSortable('allGroupsZentralTable');

    // Sofortige alphabetische Sortierung nach Aufgabennamen (3. Spalte)
    const table = document.getElementById('allGroupsZentralTable');
    if (table) {
        const tbody = table.querySelector('tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));

            // Sortiere Zeilen alphabetisch nach dem dritten Spalteninhalt
            rows.sort((a, b) => {
                const aVal = getCellValue(a, 2, 'text');
                const bVal = getCellValue(b, 2, 'text');
                return aVal.localeCompare(bVal);
            });

            // Zeilen in sortierter Reihenfolge einfügen
            rows.forEach(row => tbody.appendChild(row));

            // Header als sortiert markieren
            const headers = table.querySelectorAll('th');
            if (headers[2]) {
                headers[2].classList.add('sort-asc');
            }

            // Sortierstatus setzen
            sortState['allGroupsZentralTable_2'] = 'asc';
        }
    }

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
            const isCompleted = row.classList.contains('status-graded');
            if (statusValue === 'completed' && !isCompleted) {
                shouldShow = false;
            } else if (statusValue === 'pending' && isCompleted) {
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