// CSV Export Functionality for Mebis Statistics Dashboard
// Generates CSV export with fixed and dynamic columns based on dashboard data

// =============================================================================
// MODAL MANAGEMENT
// =============================================================================

function openCsvExportModal() {
    const modal = document.getElementById('csvExportModal');
    if (!modal) {
        console.error('CSV Export Modal not found');
        return;
    }

    // Debug: Check global variables
    console.log('CSV Modal Opening - Global Variables:', {
        currentWeek: window.currentWeek,
        maxSchoolweeks: window.maxSchoolweeks,
        currentGroup: window.currentGroup,
        currentHalbjahr: window.currentHalbjahr
    });

    // Sync slider with current week
    const csvWeekSlider = document.getElementById('csvWeekSlider');
    const csvCurrentWeekDisplay = document.getElementById('csvCurrentWeekDisplay');
    const csvWeekSliderMax = document.getElementById('csvWeekSliderMax');

    if (csvWeekSlider && csvCurrentWeekDisplay) {
        // Use defaults if values not available
        const weekValue = window.currentWeek || 9;
        const maxWeeks = window.maxSchoolweeks || 9;

        console.log('CSV Modal - Setting slider values:', { weekValue, maxWeeks });

        csvWeekSlider.value = weekValue;
        csvWeekSlider.max = maxWeeks;
        csvCurrentWeekDisplay.textContent = weekValue;
        if (csvWeekSliderMax) {
            csvWeekSliderMax.textContent = maxWeeks;
        }
        updateCsvSliderProgress(csvWeekSlider);
    }

    // Display current filter settings
    const groupingDisplay = document.getElementById('csvGroupingDisplay');
    const groupDisplay = document.getElementById('csvGroupDisplay');

    if (groupingDisplay) {
        groupingDisplay.textContent = window.currentGroup === 'all' ? 'Alle Klassen' : window.currentGroup;
    }
    if (groupDisplay) {
        groupDisplay.textContent = window.currentGroup === 'all' ? 'Alle Gruppen' : window.currentGroup;
    }

    modal.style.display = 'flex';
}

function closeCsvExportModal() {
    const modal = document.getElementById('csvExportModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function updateCsvSliderProgress(slider) {
    const currentWeekDisplay = document.getElementById('csvCurrentWeekDisplay');
    if (currentWeekDisplay) {
        currentWeekDisplay.textContent = slider.value;
    }

    // Update slider progress visual (CSS custom property)
    const min = parseFloat(slider.min) || 1;
    const max = parseFloat(slider.max) || 10;
    const value = parseFloat(slider.value);
    const progress = ((value - min) / (max - min)) * 100;
    slider.style.setProperty('--pdf-slider-progress', progress + '%');
}

// Close modal on outside click
window.addEventListener('click', function(event) {
    const modal = document.getElementById('csvExportModal');
    if (event.target === modal) {
        closeCsvExportModal();
    }
});

// =============================================================================
// PROGRESS INDICATION
// =============================================================================

let csvProgressTimeout = null;
let csvProgressPanel = null;

function showCsvProgress(percent, message) {
    // Reuse export progress panel or create custom
    csvProgressPanel = document.getElementById('exportProgressPanel');
    if (!csvProgressPanel) return;

    csvProgressPanel.style.display = 'block';
    updateCsvProgress(percent, message);
}

function updateCsvProgress(percent, message) {
    if (!csvProgressPanel) return;

    const progressBar = csvProgressPanel.querySelector('.export-progress-bar-fill');
    const progressText = csvProgressPanel.querySelector('.export-progress-text');
    const statusText = csvProgressPanel.querySelector('.export-status-text');

    if (progressBar) {
        progressBar.style.width = percent + '%';
    }
    if (progressText) {
        progressText.textContent = `${percent}%`;
    }
    if (statusText) {
        statusText.textContent = message || 'Verarbeite...';
    }
}

function hideCsvProgress() {
    if (csvProgressPanel) {
        csvProgressPanel.style.display = 'none';
    }
    csvProgressPanel = null;
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function yieldToBrowser() {
    return new Promise(resolve => setTimeout(resolve, 0));
}

function formatHjValue(value) {
    if (value === null || value === undefined) return '';
    return value.toFixed(1).replace('.', ',');
}

function formatHjGrade(grade) {
    if (grade === null || grade === undefined) return '';
    return grade.toFixed(1).replace('.', ',');
}

function extractGroupingPrefix(groupName) {
    if (!groupName || groupName === 'all') return 'Alle';
    // Extract prefix before first space or dash (e.g., "IFA12A" from "IFA12A - Team 1")
    const match = groupName.match(/^([^\s-]+)/);
    return match ? match[1] : groupName;
}

function sanitizeFilename(name) {
    if (!name) return '';
    return name.replace(/[<>:"/\\|?*]/g, '_').replace(/\s+/g, '_');
}

function generateFilename(grouping, group, week) {
    const date = new Date().toISOString().split('T')[0].replace(/-/g, ''); // YYYYMMDD
    const parts = [date, 'Export'];

    // Only include Gruppierung if specific grouping selected
    if (grouping !== 'all' && grouping !== 'Alle Gruppierungen') {
        parts.push(sanitizeFilename(grouping));
    }

    // Only include Gruppe if specific group selected
    if (group !== 'all' && group !== 'Alle Gruppen') {
        parts.push(sanitizeFilename(group));
    }

    parts.push(`Referenzwoche${week}`);

    return parts.join('_') + '.csv';
}

function extractGradeValue(userStatus) {
    if (!userStatus) return '';

    // Check multiple possible grade fields in order
    const gradeFields = ['grade', 'rating', 'score', 'points', 'result', 'mark'];
    for (const field of gradeFields) {
        const value = userStatus[field];
        if (value && value !== '-' && value !== null && value !== undefined) {
            return String(value);
        }
    }
    return '';
}

function convertGradeToPercentage(gradeString) {
    // Convert grade string to percentage value using GRADE_MAPPING from .env
    // Returns only numeric value (no "%" symbol) with German decimal separator
    if (!gradeString || gradeString === '-') {
        return '';
    }

    // Remove any "%" symbol first
    let cleanString = gradeString.replace(/%/g, '').trim();

    // Check if it's already a number (from quizzes)
    const numericMatch = cleanString.match(/^(\d+(?:[.,]\d+)?)$/);
    if (numericMatch) {
        // Already a percentage, format with German decimal separator
        const value = parseFloat(numericMatch[1].replace(',', '.'));
        return value.toFixed(1).replace('.', ',');
    }

    // Check if it contains stars (text-based grading)
    if (cleanString.includes('*')) {
        // Use GRADE_MAPPING from dashboard (loaded from .env via config.ini)
        if (window.gradeMapping && Object.keys(window.gradeMapping).length > 0) {
            // Find matching grade
            for (const [score, text] of Object.entries(window.gradeMapping)) {
                if (cleanString.includes(text)) {
                    // Return only the numeric score without "%"
                    const numericScore = parseFloat(score.replace(',', '.'));
                    return numericScore.toFixed(1).replace('.', ',');
                }
            }
        } else {
            console.warn('CSV Export: gradeMapping not available, using fallback');
            // Fallback to hardcoded mapping if window.gradeMapping not loaded
            const fallbackMapping = {
                "0": "* Nicht akzeptabel",
                "70": "** Verbesserungsbedarf",
                "100": "*** Solide Umsetzung",
                "130": "**** Exzellent"
            };
            for (const [score, text] of Object.entries(fallbackMapping)) {
                if (cleanString.includes(text)) {
                    const numericScore = parseFloat(score.replace(',', '.'));
                    return numericScore.toFixed(1).replace('.', ',');
                }
            }
        }
    }

    // Try to extract any number from the string (handles "75%", "75.5%", "75,5%", etc.)
    const extractedNumber = cleanString.match(/(\d+(?:[.,]\d+)?)/);
    if (extractedNumber) {
        const value = parseFloat(extractedNumber[1].replace(',', '.'));
        return value.toFixed(1).replace('.', ',');
    }

    // If nothing matches, return empty string (don't return original to avoid non-numeric values)
    console.warn(`CSV Export: Could not convert grade to percentage: "${gradeString}"`);
    return '';
}

function getGradeFromActivitiesByCategory(userName, assignmentId) {
    // Get grade from activities_by_category (same logic as calculatePflichtaufgabenGradeForUserByName)
    // This is where the REAL grades are stored, not in structured_tables

    if (!window.dashboardData || !window.dashboardData.activities_by_category) {
        return '';
    }

    // Find Pflichtaufgaben categories
    const pflichtCategories = window.dashboardData.activities_by_category.filter(category =>
        category.category_name && (category.category_name.includes('Pflichtaufgaben') || category.category_name.includes('🎯'))
    );

    // Search in assignments
    for (const category of pflichtCategories) {
        if (category.assignments) {
            for (const assignment of category.assignments) {
                if (assignment.id === assignmentId && assignment.user_status) {
                    const userStatus = assignment.user_status.find(status => status.user_name === userName);
                    if (!userStatus) continue;
                    const hasGrade = userStatus.grade && userStatus.grade !== '-' && userStatus.grade !== 'Nicht eingereicht';
                    if (hasGrade) {
                        return convertGradeToPercentage(userStatus.grade);
                    }
                    if (userStatus.submission_time) {
                        return 'nicht bewertet';
                    }
                }
            }
        }

        // Search in quizzes
        if (category.quizzes) {
            for (const quiz of category.quizzes) {
                if (quiz.id === assignmentId && quiz.user_status) {
                    const userStatus = quiz.user_status.find(status => status.user_name === userName);
                    if (!userStatus) continue;
                    const hasGrade = userStatus.grade && userStatus.grade !== '-' && userStatus.grade !== 'Nicht eingereicht';
                    if (hasGrade) {
                        return convertGradeToPercentage(userStatus.grade);
                    }
                    if (userStatus.submission_time) {
                        return 'nicht bewertet';
                    }
                }
            }
        }
    }

    return '';
}

function getGradeFromLeistungsnachweise(userName, assignmentId) {
    // Get grade from activities_by_category for Leistungsnachweise (zentrale exams/tests)
    // Same approach as Pflichtaufgaben - read from activities_by_category, not structured_tables

    if (!window.dashboardData || !window.dashboardData.activities_by_category) {
        return '';
    }

    // Find Leistungsnachweise categories (usually marked with specific icons or names)
    const lnwCategories = window.dashboardData.activities_by_category.filter(category =>
        category.category_name && (
            category.category_name.includes('Leistungsnachweis') ||
            category.category_name.includes('Prüfung') ||
            category.category_name.includes('Test') ||
            category.category_name.includes('📝') ||
            category.category_name.includes('🎓')
        )
    );

    // Search in assignments
    for (const category of lnwCategories) {
        if (category.assignments) {
            for (const assignment of category.assignments) {
                if (assignment.id === assignmentId && assignment.user_status) {
                    const userStatus = assignment.user_status.find(status => status.user_name === userName);
                    if (!userStatus) continue;
                    const hasGrade = userStatus.grade && userStatus.grade !== '-' && userStatus.grade !== 'Nicht eingereicht';
                    if (hasGrade) {
                        return convertGradeToPercentage(userStatus.grade);
                    }
                    if (userStatus.submission_time) {
                        return 'nicht bewertet';
                    }
                }
            }
        }

        // Search in quizzes
        if (category.quizzes) {
            for (const quiz of category.quizzes) {
                if (quiz.id === assignmentId && quiz.user_status) {
                    const userStatus = quiz.user_status.find(status => status.user_name === userName);
                    if (!userStatus) continue;
                    const hasGrade = userStatus.grade && userStatus.grade !== '-' && userStatus.grade !== 'Nicht eingereicht';
                    if (hasGrade) {
                        return convertGradeToPercentage(userStatus.grade);
                    }
                    if (userStatus.submission_time) {
                        return 'nicht bewertet';
                    }
                }
            }
        }
    }

    return '';
}

// =============================================================================
// CODE-REVIEW GRADE WITH DATE
// =============================================================================

// Gibt {percent, submissionDate} zurück, oder null wenn keine Note vorhanden
function getCodeReviewGradeWithDate(codeReviewId, userName) {
    if (!codeReviewId || !window.dashboardData || !window.dashboardData.activities_by_category) return null;
    const idStr = String(codeReviewId);

    for (const category of window.dashboardData.activities_by_category) {
        for (const list of [category.assignments || [], category.quizzes || []]) {
            for (const activity of list) {
                if (String(activity.id) !== idStr && String(activity.grade_item_id) !== idStr) continue;
                const userStatus = (activity.user_status || []).find(s => s.user_name === userName);
                if (!userStatus || !userStatus.grade || userStatus.grade === '-') return null;
                const percent = extractPercentageFromString(userStatus.grade);
                if (percent === null) return null;
                return {
                    percent,
                    submissionDate: userStatus.submission_time ? new Date(userStatus.submission_time) : null
                };
            }
        }
    }
    return null;
}

// =============================================================================
// ERROR HANDLING & VALIDATION
// =============================================================================

function validateCsvExport() {
    // Check dashboard data loaded
    if (!window.dashboardData || !window.dashboardData.structured_tables) {
        throw new Error('Keine Daten verfügbar. Bitte aktualisieren Sie das Dashboard.');
    }

    // Check group exists
    if (window.currentGroup !== 'all' && !window.dashboardData.groups[window.currentGroup]) {
        throw new Error(`Gruppe "${window.currentGroup}" nicht gefunden.`);
    }

    // Check structured data exists (only for specific group)
    if (window.currentGroup !== 'all' && !window.dashboardData.structured_tables[window.currentGroup]) {
        throw new Error('Keine strukturierten Daten für diese Gruppe verfügbar.');
    }

    // Check users exist
    let users = [];
    if (window.currentGroup === 'all') {
        users = getAllUsersAcrossGroups();
    } else {
        users = window.dashboardData.groups[window.currentGroup]?.users || [];
    }

    if (users.length === 0) {
        throw new Error('Keine Benutzer in der ausgewählten Gruppe vorhanden.');
    }

    return true;
}

// =============================================================================
// DATA COLLECTION
// =============================================================================

function getAllUsersAcrossGroups() {
    const users = [];

    // Alle Klassen (seit 2026/27 keine Team-Ebene mehr)
    const groups = Object.keys(window.dashboardData.groups).filter(g => g !== 'all');

    // Collect users from each group
    groups.forEach(groupName => {
        const groupData = window.dashboardData.groups[groupName];
        if (groupData && groupData.users) {
            groupData.users.forEach(user => {
                users.push({
                    ...user,
                    _groupName: groupName,
                    _grouping: extractGroupingPrefix(groupName)
                });
            });
        }
    });

    return users;
}

function buildHjConfig(users, group) {
    // Bestimme Klasse fuer die Schienen-Ermittlung
    const sampleGroup = (window.currentGroup !== 'all')
        ? window.currentGroup
        : (users.length > 0 ? users[0]._groupName : null);
    if (!sampleGroup) return null;

    const track = getTrackForGroup(sampleGroup);
    const sliderWeek = parseInt(document.getElementById('csvWeekSlider')?.value || 0);
    const autoWeek = getCurrentReferenceWeekForTrack(track);
    const currentWeek = sliderWeek > 0 ? sliderWeek : autoWeek;

    const prognosisAssignments = (window.mitarbeitsnoteConfig
        && window.mitarbeitsnoteConfig.prognosis_assignments) || {};
    const showReviewTalk = !!(prognosisAssignments.reviewTalk || prognosisAssignments.reviewTalk1);
    const showCodeReview = !!(prognosisAssignments.codeReview);

    // Titel des aktiven Halbjahres fuer die Spaltenbeschriftung
    const kurs = (typeof getCourse === 'function' && window.currentHalbjahr
                  && window.currentHalbjahr !== 'gesamt')
        ? getCourse(window.currentHalbjahr) : null;

    return {
        track,
        currentWeek,
        zeitraum: kurs ? kurs.titel : 'Schuljahr',
        showReviewTalk,
        showCodeReview,
        codeReviewId: prognosisAssignments.codeReview || null
    };
}

function collectCsvData(selectedWeek) {
    const group = window.currentGroup === 'all' ? 'Alle Gruppen' : window.currentGroup;
    const grouping = window.currentGroup === 'all' ? 'Alle Klassen' : window.currentGroup;

    // Get users
    let users = [];
    if (window.currentGroup === 'all') {
        users = getAllUsersAcrossGroups();
    } else {
        users = window.dashboardData.groups[window.currentGroup].users.map(user => ({
            ...user,
            _groupName: window.currentGroup,
            _grouping: extractGroupingPrefix(window.currentGroup)
        }));
    }

    // Get structured table data for current group
    // For "all groups", we'll need to collect from multiple structured tables
    let mandatoryChecklists = [];
    let pflichtRows = [];
    let examRows = [];
    let checklistHeaders = [];
    let pflichtHeaders = [];
    let examHeaders = [];

    if (window.currentGroup !== 'all') {
        const structuredData = window.dashboardData.structured_tables[window.currentGroup] || {};
        const checklistsData = structuredData.checklists;
        const pflichtData = structuredData.pflichtaufgaben;
        const examData = structuredData.zentrale_leistungsnachweise;

        // Filter mandatory checklists
        mandatoryChecklists = checklistsData?.rows?.filter(row => row.is_mandatory) || [];
        pflichtRows = pflichtData?.rows || [];
        examRows = examData?.rows || [];
        checklistHeaders = checklistsData?.headers || [];
        pflichtHeaders = pflichtData?.headers || [];
        examHeaders = examData?.headers || [];
    } else {
        // For "all groups", collect unique checklists/assignments across all groups
        mandatoryChecklists = collectAllChecklists();
        pflichtRows = collectAllPflichtaufgaben();
        examRows = collectAllLeistungsnachweise();
    }

    // Halbjahresnotenkonfiguration ermitteln
    const hjConfig = buildHjConfig(users, group);

    return {
        grouping,
        group,
        users,
        selectedWeek,
        mandatoryChecklists,
        pflichtRows,
        examRows,
        checklistHeaders,
        pflichtHeaders,
        examHeaders,
        hjConfig
    };
}

function collectAllChecklists() {
    const checklistsMap = new Map();

    Object.keys(window.dashboardData.structured_tables || {}).forEach(groupName => {
        const structuredData = window.dashboardData.structured_tables[groupName];
        const checklistsData = structuredData?.checklists;

        if (checklistsData && checklistsData.rows) {
            checklistsData.rows.forEach(row => {
                if (row.is_mandatory && row.checklist_id) {
                    // Use checklist_id as unique key
                    if (!checklistsMap.has(row.checklist_id)) {
                        checklistsMap.set(row.checklist_id, row);
                    }
                }
            });
        }
    });

    return Array.from(checklistsMap.values());
}

function collectAllPflichtaufgaben() {
    const assignmentsMap = new Map();

    Object.keys(window.dashboardData.structured_tables || {}).forEach(groupName => {
        const structuredData = window.dashboardData.structured_tables[groupName];
        const pflichtData = structuredData?.pflichtaufgaben;

        if (pflichtData && pflichtData.rows) {
            pflichtData.rows.forEach(row => {
                if (row.assignment_id) {
                    // Use assignment_id as unique key
                    if (!assignmentsMap.has(row.assignment_id)) {
                        assignmentsMap.set(row.assignment_id, row);
                    }
                }
            });
        }
    });

    return Array.from(assignmentsMap.values());
}

function collectAllLeistungsnachweise() {
    const examsMap = new Map();

    Object.keys(window.dashboardData.structured_tables || {}).forEach(groupName => {
        const structuredData = window.dashboardData.structured_tables[groupName];
        const examData = structuredData?.zentrale_leistungsnachweise;

        if (examData && examData.rows) {
            examData.rows.forEach(row => {
                if (row.assignment_id) {
                    // Use assignment_id as unique key
                    if (!examsMap.has(row.assignment_id)) {
                        examsMap.set(row.assignment_id, row);
                    }
                }
            });
        }
    });

    return Array.from(examsMap.values());
}

// =============================================================================
// CSV GENERATION - HEADERS
// =============================================================================

function buildCsvHeaders(data) {
    const headers = [
        'Gruppierung',
        'Gruppe',
        'Vorname',
        'Nachname',
        'Checklisten 100%',
        'Pflicht (%)',
        'Note',
        'Gesamt (%)',
        'Eingereichte Aufgaben',
        'Note Pflichtaufgaben'
    ];

    // Add checklist headers (sorted alphabetically)
    const sortedChecklists = [...data.mandatoryChecklists].sort((a, b) =>
        (a.checklist_title || '').localeCompare(b.checklist_title || '')
    );
    sortedChecklists.forEach(checklist => {
        headers.push(checklist.checklist_title || 'Unbekannte Checkliste');
    });

    // Add pflichtaufgaben headers (sorted alphabetically)
    const sortedPflicht = [...data.pflichtRows].sort((a, b) =>
        (a.assignment_title || '').localeCompare(b.assignment_title || '')
    );
    sortedPflicht.forEach(assignment => {
        headers.push(assignment.assignment_title || 'Unbekannte Aufgabe');
    });

    // Add leistungsnachweise headers (sorted alphabetically)
    const sortedExams = [...data.examRows].sort((a, b) =>
        (a.assignment_title || '').localeCompare(b.assignment_title || '')
    );
    sortedExams.forEach(exam => {
        headers.push(exam.assignment_title || 'Unbekannter LNW');
    });

    // Mitarbeitsnoten-Spalten des aktiven Halbjahres
    const hj = data.hjConfig;
    if (hj) {
        const p = hj.zeitraum ? `${hj.zeitraum} ` : '';
        headers.push(`${p}Quantität (%)`);
        headers.push(`${p}Delta (Std.)`);
        headers.push(`${p}Qualität (%)`);
        if (hj.showReviewTalk) headers.push(`${p}Review-Talk (%)`);
        if (hj.showCodeReview) headers.push(`${p}Code-Review (%)`);
        headers.push(`${p}Ø Mitarbeitsnote`);
    }

    return headers;
}

// =============================================================================
// CSV GENERATION - ROWS
// =============================================================================

function buildUserRow(user, data) {
    const row = [];

    // Get group name for calculations
    const userGroup = user._groupName || data.group;

    // Calculate progress using same function as dashboard's "Gesamtfortschritt pro Person" table
    const pflichtResult = calculatePflichtaufgabenProgressGesamt(user, data.selectedWeek);

    // Calculate pflichtaufgaben grade
    const pflichtGrade = calculatePflichtaufgabenGradeForUserByName(
        user.name,
        userGroup
    );

    // Split name into Vorname and Nachname
    // Use last space as delimiter: "Thomas Maria Müller" -> "Thomas Maria" + "Müller"
    const fullName = user.name || '';
    let vorname = '';
    let nachname = '';

    if (fullName) {
        const lastSpaceIndex = fullName.lastIndexOf(' ');
        if (lastSpaceIndex > 0) {
            vorname = fullName.substring(0, lastSpaceIndex);
            nachname = fullName.substring(lastSpaceIndex + 1);
        } else {
            // No space found - use entire name as Nachname
            nachname = fullName;
        }
    }

    // Fixed columns
    row.push(user._grouping || data.grouping); // Gruppierung
    row.push(userGroup); // Gruppe
    row.push(vorname); // Vorname
    row.push(nachname); // Nachname
    row.push(user.checklists?.required_100_count || 0); // Checklisten 100%

    // Pflicht (%) - same calculation as dashboard "Gesamtfortschritt pro Person"
    const pflichtValue = pflichtResult ? pflichtResult.value : 0;

    // Format mit deutschem Dezimaltrennzeichen (Komma) für Excel-Kompatibilität
    const pflichtFormatted = pflichtValue.toFixed(1).replace('.', ',');
    row.push(pflichtFormatted);

    // Note - from calculateGradeFromPflichtProgress mit deutschem Dezimaltrennzeichen
    const gradeText = calculateGradeFromPflichtProgress(pflichtValue);
    const gradeFormatted = gradeText ? gradeText.replace('.', ',') : '';
    row.push(gradeFormatted); // Note

    // Gesamt (%) - im Dashboard identisch mit Pflicht (%)
    const gesamtFormatted = pflichtFormatted;
    row.push(gesamtFormatted);

    row.push(user.assignments?.submitted_count || 0); // Eingereichte Aufgaben

    // Note Pflichtaufgaben - format as number only mit deutschem Dezimaltrennzeichen
    let pflichtGradeValue = '';
    if (pflichtGrade && pflichtGrade.grade !== null && pflichtGrade.grade !== undefined && !isNaN(pflichtGrade.grade)) {
        pflichtGradeValue = pflichtGrade.grade.toFixed(1).replace('.', ',');
    } else if (pflichtGrade && pflichtGrade.grade > 10) {
        console.error(`CSV Export ERROR - pflichtGrade is ${pflichtGrade.grade} which is > 10! Expected grade 1.0-6.0.`, {
            user: user.name,
            pflichtGrade: pflichtGrade
        });
    }
    row.push(pflichtGradeValue); // Note Pflichtaufgaben

    // Dynamic checklist columns
    const sortedChecklists = [...data.mandatoryChecklists].sort((a, b) =>
        (a.checklist_title || '').localeCompare(b.checklist_title || '')
    );

    sortedChecklists.forEach(checklist => {
        let progress = '';

        if (window.currentGroup !== 'all') {
            // Find user index in checklist headers
            const userIndex = data.checklistHeaders.findIndex(h => h === user.name);
            if (userIndex > 0 && checklist.user_progress && checklist.user_progress[userIndex - 1]) {
                progress = checklist.user_progress[userIndex - 1].required_progress || '';
            }
        } else {
            // For "all groups", need to find user's progress in their specific group
            const userGroupData = window.dashboardData.structured_tables[userGroup];
            if (userGroupData && userGroupData.checklists) {
                const checklistRow = userGroupData.checklists.rows.find(r => r.checklist_id === checklist.checklist_id);
                if (checklistRow && checklistRow.user_progress) {
                    const headers = userGroupData.checklists.headers;
                    const userIndex = headers.findIndex(h => h === user.name);
                    if (userIndex > 0 && checklistRow.user_progress[userIndex - 1]) {
                        progress = checklistRow.user_progress[userIndex - 1].required_progress || '';
                    }
                }
            }
        }

        // Format checklist progress as numeric percentage (without "%" symbol)
        row.push(progress ? convertGradeToPercentage(progress) : '');
    });

    // Dynamic pflichtaufgaben columns
    const sortedPflicht = [...data.pflichtRows].sort((a, b) =>
        (a.assignment_title || '').localeCompare(b.assignment_title || '')
    );

    console.log(`CSV Export - Pflichtaufgaben columns for ${user.name}:`, {
        totalPflichtRows: data.pflichtRows.length,
        pflichtHeaders: data.pflichtHeaders,
        firstAssignment: data.pflichtRows[0]
    });

    // Track grades for summary
    const gradesExtracted = [];

    sortedPflicht.forEach((assignment, index) => {
        let grade = '';

        if (index === 0) {
            console.log(`\n=== PFLICHTAUFGABEN LOOP START (NEW CODE LOADED!) ===`);
            console.log(`currentGroup: "${window.currentGroup}"`);
            console.log(`Taking ${window.currentGroup !== 'all' ? 'SINGLE GROUP' : 'ALL GROUPS'} path`);
        }

        if (window.currentGroup !== 'all') {
            // IMPORTANT: Get grade from activities_by_category, NOT from structured_tables
            // structured_tables has rounded/simplified values ("-"), but activities_by_category has the real grades
            grade = getGradeFromActivitiesByCategory(user.name, assignment.assignment_id);

            if (index === 0) {  // Debug first assignment
                console.log(`  Assignment "${assignment.assignment_title}":`, {
                    assignmentId: assignment.assignment_id,
                    userName: user.name,
                    gradeFromActivities: grade
                });
            }
        } else {
            // For "all groups", also get grade from activities_by_category
            grade = getGradeFromActivitiesByCategory(user.name, assignment.assignment_id);

            if (index === 0) {  // Debug first assignment for "all groups" path
                console.log(`  [ALL GROUPS PATH] Assignment "${assignment.assignment_title}":`, {
                    assignmentId: assignment.assignment_id,
                    userName: user.name,
                    userGroup: userGroup,
                    gradeFromActivities: grade
                });
            }
        }

        // Track extracted grade for summary
        gradesExtracted.push({
            title: assignment.assignment_title,
            id: assignment.assignment_id,
            grade: grade
        });

        row.push(grade);
    });

    // Log summary of all grades extracted for first user only
    if (data.users.indexOf(user) === 0) {
        console.log(`\n=== PFLICHTAUFGABEN GRADES SUMMARY FOR ${user.name} ===`);
        console.log(`Total assignments: ${gradesExtracted.length}`);
        const withGrades = gradesExtracted.filter(g => g.grade !== '');
        const withoutGrades = gradesExtracted.filter(g => g.grade === '');
        console.log(`With grades: ${withGrades.length}`);
        console.log(`Without grades (empty): ${withoutGrades.length}`);
        if (withGrades.length > 0) {
            console.log(`Assignments with grades:`, withGrades);
        }
        if (withoutGrades.length > 0 && withoutGrades.length <= 5) {
            console.log(`Assignments without grades:`, withoutGrades);
        }
    }

    // Dynamic leistungsnachweise columns
    const sortedExams = [...data.examRows].sort((a, b) =>
        (a.assignment_title || '').localeCompare(b.assignment_title || '')
    );

    sortedExams.forEach(exam => {
        let grade = '';

        // IMPORTANT: Get grade from activities_by_category, NOT from structured_tables
        // Same approach as Pflichtaufgaben - activities_by_category has the real grades
        grade = getGradeFromLeistungsnachweise(user.name, exam.assignment_id);

        row.push(grade);
    });

    // Mitarbeitsnote des aktiven Halbjahres
    const hj = data.hjConfig;
    if (hj) {
        const ma = calculateMitarbeitsnote(user, userGroup, hj.currentWeek);
        row.push(formatHjValue(ma?.quantitaet));
        row.push(ma && ma.deltaStunden !== null && ma.deltaStunden !== undefined
            ? ma.deltaStunden.toFixed(1).replace('.', ',') : '');
        row.push(formatHjValue(ma?.qualitaet));
        if (hj.showReviewTalk) row.push(formatHjValue(ma?.reviewTalk));
        if (hj.showCodeReview) row.push(formatHjValue(ma?.codeReview));
        row.push(formatHjGrade(ma?.grade));
    }

    return row;
}

async function buildCsvRowsAsync(data, progressCallback) {
    const rows = [];
    const batchSize = 10; // Process 10 users at a time

    for (let i = 0; i < data.users.length; i += batchSize) {
        const batch = data.users.slice(i, Math.min(i + batchSize, data.users.length));

        batch.forEach(user => {
            rows.push(buildUserRow(user, data));
        });

        const progress = (i + batch.length) / data.users.length;
        progressCallback(progress, i + batch.length, data.users.length);

        await yieldToBrowser();
    }

    return rows;
}

// =============================================================================
// CSV FORMATTING (RFC 4180)
// =============================================================================

function escapeCSVValue(value) {
    if (value === null || value === undefined) return '';

    let str = String(value);

    // Remove HTML tags and entities
    str = str
        .replace(/<[^>]*>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/<br\s*\/?>/gi, ' '); // Replace <br> with space

    // Wrap in quotes if contains special characters (semicolon for German CSV, quotes, newlines)
    if (str.includes(';') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
        return '"' + str.replace(/"/g, '""') + '"';
    }

    return str;
}

function generateCSVString(headers, rows) {
    const lines = [];

    // Add BOM for Excel UTF-8 compatibility
    // Use semicolon (;) as separator for German CSV format (allows comma as decimal separator)
    lines.push('\uFEFF' + headers.map(escapeCSVValue).join(';'));

    rows.forEach(row => {
        lines.push(row.map(escapeCSVValue).join(';'));
    });

    return lines.join('\r\n');
}

// =============================================================================
// DOWNLOAD
// =============================================================================

function downloadCSV(csvString, filename) {
    try {
        // Check size limit (50MB)
        if (csvString.length > 50 * 1024 * 1024) {
            throw new Error('CSV zu groß für Browser-Export (>50MB). Bitte wählen Sie eine kleinere Gruppe.');
        }

        const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        URL.revokeObjectURL(url);

    } catch (error) {
        console.error('Download error:', error);
        throw new Error('Download fehlgeschlagen: ' + error.message);
    }
}

// =============================================================================
// MAIN EXPORT FUNCTION
// =============================================================================

async function generateCsvExport() {
    const generateBtn = document.getElementById('generateCsvBtn');
    if (!generateBtn) return;

    const originalBtnContent = generateBtn.innerHTML;
    const csvWeekSlider = document.getElementById('csvWeekSlider');
    const selectedWeek = csvWeekSlider ? parseInt(csvWeekSlider.value) : currentWeek;

    const startTime = Date.now();
    let progressTimeout = null;

    try {
        // Validate before starting
        validateCsvExport();

        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="btn-spinner"></span> Verarbeite...';

        // Show progress panel after 2 seconds
        progressTimeout = setTimeout(() => {
            showCsvProgress(0, 'Sammle Daten...');
        }, 2000);

        // Phase 1: Collect data (10%)
        await yieldToBrowser();
        const data = collectCsvData(selectedWeek);
        if (progressTimeout === null) updateCsvProgress(10, 'Erstelle Header...');

        // Phase 2: Build headers (30%)
        await yieldToBrowser();
        const headers = buildCsvHeaders(data);
        if (progressTimeout === null) updateCsvProgress(30, 'Verarbeite Zeilen...');

        // Phase 3: Build rows (80%) - batch processing for large datasets
        const rows = await buildCsvRowsAsync(data, (progress, current, total) => {
            if (progressTimeout === null) {
                const percent = 30 + Math.floor(progress * 50);
                updateCsvProgress(percent, `Verarbeite Zeile ${current} von ${total}...`);
            }
        });
        if (progressTimeout === null) updateCsvProgress(80, 'Generiere CSV...');

        // Phase 4: Generate CSV string (95%)
        await yieldToBrowser();
        const csvString = generateCSVString(headers, rows);
        if (progressTimeout === null) updateCsvProgress(95, 'Starte Download...');

        // Phase 5: Download (100%)
        const filename = generateFilename(data.grouping, data.group, selectedWeek);
        downloadCSV(csvString, filename);
        if (progressTimeout === null) updateCsvProgress(100, 'Abgeschlossen!');

        // Clear timeout and hide progress
        if (progressTimeout) {
            clearTimeout(progressTimeout);
            progressTimeout = null;
        } else {
            setTimeout(() => hideCsvProgress(), 1000);
        }

        closeCsvExportModal();

        // Show success message
        console.log(`CSV Export erfolgreich: ${filename} (${rows.length} Zeilen, ${(csvString.length / 1024).toFixed(1)} KB)`);

    } catch (error) {
        if (progressTimeout) {
            clearTimeout(progressTimeout);
        }
        hideCsvProgress();

        console.error('CSV Export Error:', error);
        alert('Fehler beim CSV-Export:\n\n' + error.message);
    } finally {
        generateBtn.disabled = false;
        generateBtn.innerHTML = originalBtnContent;
    }
}
