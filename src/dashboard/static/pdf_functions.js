
// ============================================================================
// PDF Code-Review Modal Functions
// ============================================================================

// Globale Variable für abwesende Personen
let absentPersons = [];

// Globale Variable für deaktivierte Gruppen
let disabledGroups = [];

function updatePdfSliderProgress(slider) {
    // Aktualisiere Anzeige
    document.getElementById('pdfCurrentWeekDisplay').textContent = slider.value;

    // Berechne Fortschritt in Prozent
    const min = parseInt(slider.min);
    const max = parseInt(slider.max);
    const value = parseInt(slider.value);
    const progress = ((value - min) / (max - min)) * 100;

    // Setze CSS-Variable für Fortschrittsanzeige
    slider.style.setProperty('--pdf-slider-progress', progress + '%');
}

function openPdfReviewModal() {
    console.log("openPdfReviewModal called");
    const modal = document.getElementById("pdfReviewModal");
    if (modal) {
        const today = new Date().toISOString().split("T")[0];
        const dateInput = document.getElementById("reviewDate");
        if (dateInput) {
            dateInput.value = today;
        }
        const currentWeekValue = parseInt(document.getElementById("referenceWeekSlider")?.value || maxSchoolweeks);
        const pdfWeekSlider = document.getElementById("pdfWeekSlider");
        if (pdfWeekSlider) {
            pdfWeekSlider.max = maxSchoolweeks;
            pdfWeekSlider.value = currentWeekValue;
            document.getElementById("pdfCurrentWeekDisplay").textContent = currentWeekValue;
            document.getElementById("pdfWeekSliderMax").textContent = maxSchoolweeks;
            // Initialisiere Fortschrittsanzeige
            updatePdfSliderProgress(pdfWeekSlider);
        }
        absentPersons = [];
        disabledGroups = [];
        loadPersonsList();
        modal.style.display = "flex";
        console.log("PDF Review Modal opened");
    } else {
        console.error("PDF Review Modal not found!");
    }
}

function closePdfReviewModal() {
    const modal = document.getElementById("pdfReviewModal");
    if (modal) {
        modal.style.display = "none";
    }
}

function selectReviewNr(nr) {
    document.querySelectorAll(".pdf-review-nr-btn").forEach(btn => {
        btn.classList.remove("active");
    });
    const selectedBtn = document.querySelector(`.pdf-review-nr-btn[data-review="${nr}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add("active");
    }
}

function loadPersonsList() {
    const personsList = document.getElementById("pdfPersonsList");
    if (!personsList) return;
    personsList.innerHTML = "";
    if (!dashboardData || !dashboardData.groups) {
        personsList.innerHTML = "<p style='color: #999; text-align: center; padding: 20px;'>Keine Daten verfügbar</p>";
        return;
    }
    if (currentGroup === "all") {
        let groups = Object.keys(dashboardData.groups).filter(g => g !== "all");
        if (currentGrouping !== "all") {
            groups = groups.filter(groupName => groupName.startsWith(currentGrouping));
        }
        if (groups.length === 0) {
            personsList.innerHTML = "<p style='color: #999; text-align: center; padding: 20px;'>Keine Gruppen in dieser Gruppierung</p>";
            return;
        }
        groups.forEach(groupName => {
            const groupData = dashboardData.groups[groupName];
            if (!groupData || !groupData.users) return;
            const groupDiv = document.createElement("div");
            groupDiv.className = "pdf-person-group";
            const groupTitle = document.createElement("div");
            groupTitle.className = "pdf-group-name";
            groupTitle.dataset.group = groupName;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "pdf-group-checkbox";
            checkbox.checked = true;
            checkbox.addEventListener("click", (e) => {
                e.stopPropagation();
                toggleGroupDisabled(groupName);
            });
            const groupNameSpan = document.createElement("span");
            groupNameSpan.textContent = groupName;
            groupTitle.appendChild(checkbox);
            groupTitle.appendChild(groupNameSpan);
            groupTitle.addEventListener("click", () => {
                checkbox.checked = !checkbox.checked;
                toggleGroupDisabled(groupName);
            });
            groupDiv.appendChild(groupTitle);
            groupData.users.forEach(user => {
                if (user && user.name) {
                    const personItem = createPersonItem(user.name, groupName);
                    groupDiv.appendChild(personItem);
                }
            });
            personsList.appendChild(groupDiv);
        });
    } else {
        const groupData = dashboardData.groups[currentGroup];
        if (groupData && groupData.users) {
            groupData.users.forEach(user => {
                if (user && user.name) {
                    const personItem = createPersonItem(user.name, currentGroup);
                    personsList.appendChild(personItem);
                }
            });
        }
    }
}

function createPersonItem(personName, groupName) {
    const item = document.createElement("div");
    item.className = "pdf-person-item";
    item.textContent = personName;
    item.title = "Klicken um Abwesenheit zu markieren";
    item.dataset.person = personName;
    item.dataset.group = groupName;
    item.addEventListener("click", () => {
        togglePersonAbsence(item, personName);
    });
    return item;
}

function togglePersonAbsence(item, personName) {
    const isAbsent = item.classList.toggle("absent");
    if (isAbsent) {
        item.title = "Abwesend - Klicken um anwesend zu setzen";
        if (!absentPersons.includes(personName)) {
            absentPersons.push(personName);
        }
    } else {
        item.title = "Klicken um Abwesenheit zu markieren";
        absentPersons = absentPersons.filter(p => p !== personName);
    }
    console.log("Abwesende Personen:", absentPersons);
}

function toggleGroupDisabled(groupName) {
    const groupTitle = document.querySelector(`.pdf-group-name[data-group="${groupName}"]`);
    if (!groupTitle) return;
    const checkbox = groupTitle.querySelector(".pdf-group-checkbox");
    const isDisabled = !checkbox.checked;
    if (isDisabled) {
        groupTitle.classList.add("disabled");
        if (!disabledGroups.includes(groupName)) {
            disabledGroups.push(groupName);
        }
    } else {
        groupTitle.classList.remove("disabled");
        disabledGroups = disabledGroups.filter(g => g !== groupName);
    }
    console.log("Deaktivierte Gruppen:", disabledGroups);
}

async function generatePdfReview() {
    const reviewNrBtn = document.querySelector(".pdf-review-nr-btn.active");
    const reviewNr = reviewNrBtn ? reviewNrBtn.dataset.review : "1";
    const reviewDate = document.getElementById("reviewDate").value;
    const pdfWeek = parseInt(document.getElementById("pdfWeekSlider").value);
    if (!reviewDate) {
        alert("Bitte wählen Sie ein Datum aus.");
        return;
    }
    const generateBtn = document.getElementById("generatePdfBtn");
    const originalBtnContent = generateBtn.innerHTML;
    try {
        generateBtn.disabled = true;
        generateBtn.classList.add("loading");

        console.log(`Generating PDF Review: Review-Nr=${reviewNr}, Date=${reviewDate}, Week=${pdfWeek}, Absent=${absentPersons}, Disabled Groups=${disabledGroups}`);

        generateBtn.innerHTML = "<span class='btn-spinner'></span>";

        const pdfData = {
            reviewNr: reviewNr,
            reviewDate: reviewDate,
            absentPersons: absentPersons,
            disabledGroups: disabledGroups,
            grouping: currentGrouping,
            group: currentGroup,
            week: pdfWeek,
            maxWeeks: dashboardData && dashboardData.max_schoolweeks ? dashboardData.max_schoolweeks : 9,
            exportDate: dashboardData && dashboardData.last_updated ? dashboardData.last_updated : "",
            groupData: dashboardData && dashboardData.groups ? dashboardData.groups[currentGroup] : null,
            structuredTables: dashboardData && dashboardData.structured_tables ? dashboardData.structured_tables[currentGroup] : null
        };

        // Bei "Alle Gruppen": füge allGroups und allStructuredTables hinzu
        if (currentGroup === "all" && dashboardData && dashboardData.groups) {
            console.log("All groups selected - backend will merge all PDFs into one");
            let filteredGroups = {};
            let filteredStructuredTables = {};
            Object.keys(dashboardData.groups).forEach(groupName => {
                if (groupName === "all") return;
                if (currentGrouping !== "all" && !groupName.startsWith(currentGrouping)) {
                    return;
                }
                filteredGroups[groupName] = dashboardData.groups[groupName];
                if (dashboardData.structured_tables && dashboardData.structured_tables[groupName]) {
                    filteredStructuredTables[groupName] = dashboardData.structured_tables[groupName];
                }
            });
            console.log(`Filtered groups by grouping '${currentGrouping}':`, Object.keys(filteredGroups));
            pdfData.allGroups = filteredGroups;
            pdfData.allStructuredTables = filteredStructuredTables;
            pdfData.isAllGroups = true;
        }

        console.log("PDF Data being sent:", pdfData);

        const response = await fetch("/api/generate-review-pdf", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(pdfData)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "PDF-Generierung fehlgeschlagen");
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const filename = currentGroup === "all"
            ? `Code_Review_${currentGrouping}_Review${reviewNr}.pdf`
            : `Code_Review_${currentGroup}_Review${reviewNr}.pdf`;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        console.log("PDF Review generated successfully");
        closePdfReviewModal();
        alert("PDF wurde erfolgreich erstellt!");

    } catch (error) {
        console.error(`Error generating PDF: ${error.message}`);
        alert(`Fehler beim Erstellen der PDF: ${error.message}`);
    } finally {
        generateBtn.disabled = false;
        generateBtn.classList.remove("loading");
        generateBtn.innerHTML = originalBtnContent;
    }
}
