// ============================================================
// start.js — Dashboard in ByCS: ersetzt den Flask-Server
//
// dashboard.js holt seine Daten lokal von /api/data, startet den Export
// ueber /api/export/start und laedt Dateien ueber /api/load-file. In ByCS
// gibt es keinen Server. Diese Datei wird nach dashboard.js geladen und
// ersetzt genau diese drei Wege:
//
//   loadData()              -> Export im Browser (bycs/export/exporter.js)
//                              + Aufbereitung (aufbereitung.js)
//   startExportAndReload()  -> dasselbe erneut ("Aktualisieren")
//   loadFromFile(input)     -> Exportdatei lokal lesen und aufbereiten
//
// Alles Uebrige in dashboard.js bleibt unveraendert. Schuelerdaten werden
// nicht gespeichert: sie leben nur im Speicher dieser Seite; die Datei
// gibt es nur auf ausdruecklichen Klick ("Export speichern").
// ============================================================

(function () {
'use strict';

const zustand = { planRoh: null, planDashboard: null, einstellungen: null, letzterExport: null, laeuft: false };

async function ladeJson(name) {
    const antwort = await fetch(name, { cache: 'no-store' });
    if (!antwort.ok) throw new Error(`${name} nicht gefunden (HTTP ${antwort.status})`);
    return antwort.json();
}

async function ladeGrundlagen() {
    if (zustand.planDashboard) return;
    [zustand.planRoh, zustand.planDashboard, zustand.einstellungen] = await Promise.all(
        ['plan.json', 'plan_dashboard.json', 'einstellungen.json'].map(ladeJson));
}

function zeige(exportDaten, dateiname) {
    const daten = window.MebisAufbereitung.aufbereiten(
        exportDaten, zustand.planDashboard, zustand.einstellungen, dateiname);
    applyDashboardData(daten);
}

// --- Fortschritt im vorhandenen Export-Panel ------------------------------

const el = id => document.getElementById(id);

function panel(sichtbar) {
    const p = el('exportProgressPanel');
    if (p) p.style.display = sichtbar ? 'block' : 'none';
}

function setzeFortschritt(prozent, text, zusatz) {
    const balken = el('exportProgressBar');
    if (balken && typeof prozent === 'number') {
        balken.style.width = `${Math.round(prozent)}%`;
        balken.textContent = `${Math.round(prozent)}%`;
    }
    if (text && el('exportProgressMessage')) el('exportProgressMessage').textContent = text;
    if (zusatz !== undefined && el('exportEstimatedTime')) el('exportEstimatedTime').textContent = zusatz;
}

// Grobe Gewichtung der Phasen eines Kurses (Aufgaben dauern am laengsten)
function fortschrittsMelder(kursAnzahl) {
    let kurs = -1;
    const anteil = (basis, spanne, i, n) => basis + (n ? spanne * i / n : 0);
    return (text, nurZaehler) => {
        let innen = null;
        let m;
        if (/Aktivitäten und Gruppen/.test(text)) { kurs++; innen = 0.03; }
        else if ((m = /^Aufgaben (\d+)\/(\d+)/.exec(text))) {
            innen = anteil(0.05, 0.6, +m[1], +m[2]);
            if (el('exportAssignmentsProgress')) el('exportAssignmentsProgress').textContent = `${m[1]}/${m[2]}`;
        } else if ((m = /^Tests (\d+)\/(\d+)/.exec(text))) {
            innen = anteil(0.65, 0.2, +m[1], +m[2]);
            if (el('exportQuizzesProgress')) el('exportQuizzesProgress').textContent = `${m[1]}/${m[2]}`;
        } else if (/Gruppenmitglieder/.test(text)) innen = 0.87;
        else if (/Bewerterübersicht/.test(text)) innen = 0.92;
        const k = Math.max(kurs, 0);
        if (innen !== null) setzeFortschritt((k + innen) / kursAnzahl * 100, nurZaehler ? undefined : text);
        else if (!nurZaehler) setzeFortschritt(undefined, text);
    };
}

async function exportiereUndZeige() {
    if (zustand.laeuft) return;
    zustand.laeuft = true;
    const knopf = el('refreshBtn');
    if (knopf) { knopf.disabled = true; knopf.classList.add('loading'); }
    panel(true);
    if (el('exportChecklistsProgress')) el('exportChecklistsProgress').textContent = '–';
    setzeFortschritt(0, 'Export wird gestartet …', 'Liest Moodle in Ihrer Sitzung — etwa 1–2 Minuten');

    try {
        await ladeGrundlagen();
        const kurse = zustand.planRoh.kurse.filter(k => !k.gesperrt);
        const beginn = performance.now();
        const ergebnis = await window.MebisExport.exportiere(
            zustand.planRoh, kurse, fortschrittsMelder(kurse.length));
        zustand.letzterExport = ergebnis;
        zeige(ergebnis.data, ergebnis.dateiname);

        const b = ergebnis.data.pruefbericht;
        const dauer = Math.round((performance.now() - beginn) / 1000);
        setzeFortschritt(100, b.luecken.length
            ? `Fertig — ${b.luecken.length} Lücke(n), Details über der Tabelle`
            : 'Fertig — jeder Status ist bekannt',
            `${ergebnis.seiten} Seiten in ${dauer} s gelesen`);
        if (el('exportSpeichernBtn')) el('exportSpeichernBtn').hidden = false;
        setTimeout(() => panel(false), 6000);
    } catch (e) {
        setzeFortschritt(0, `Export fehlgeschlagen: ${e.message}`,
            'Läuft die Seite in ByCS (lernplattform.bycs.de)? Alternativ: „Datei laden".');
        showError('Export fehlgeschlagen: ' + e.message);
    } finally {
        zustand.laeuft = false;
        if (knopf) { knopf.disabled = false; knopf.classList.remove('loading'); }
        showLoading(false);
    }
}

// --- Ersatz fuer die Server-Wege in dashboard.js ---------------------------

window.loadData = async function () {
    showLoading(true);
    try {
        await ladeGrundlagen();
    } catch (e) {
        showLoading(false);
        showError('Dashboard unvollständig hochgeladen: ' + e.message);
        return;
    }
    await exportiereUndZeige();
};

window.startExportAndReload = exportiereUndZeige;

window.loadFromFile = async function (input) {
    if (!input.files || !input.files[0]) return;
    const datei = input.files[0];
    input.value = '';
    showLoading(true);
    try {
        await ladeGrundlagen();
        const daten = JSON.parse(await datei.text());
        zeige(daten, datei.name);
        // Auch eine geladene Datei laesst sich aufgabenweise nachladen
        zustand.letzterExport = { data: daten, dateiname: datei.name, seiten: 0 };
        if (el('exportSpeichernBtn')) el('exportSpeichernBtn').hidden = false;
    } catch (e) {
        showError('Fehler beim Laden der Datei: ' + e.message);
    } finally {
        showLoading(false);
    }
};

// Sync-Knopf im Reiter Pflichtaufgaben: eine einzelne Aufgabe oder einen
// Test neu aus Moodle lesen, in den Export eintragen, neu aufbereiten.
// Eine Aufgabe braucht nur ihre Bewertungsseite (wenige Sekunden); ein
// Test die ganze Bewerteruebersicht, weil dort der Teststatus steht.
window.pflichtSync = async function (cmid, knopf) {
    const erg = zustand.letzterExport;
    if (!erg || zustand.laeuft) return;
    zustand.laeuft = true;
    if (knopf) knopf.disabled = true;
    panel(true);
    setzeFortschritt(30, 'Lade diese Aufgabe neu aus Moodle …', '');
    try {
        await ladeGrundlagen();
        const r = await window.MebisExport.aktualisiereAktivitaet(erg.data, zustand.planRoh, cmid);
        zeige(erg.data, erg.dateiname);
        showTab('pflicht');
        const zeit = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
        setzeFortschritt(100, `„${r.titel}" um ${zeit} nachgeladen`
            + (r.luecken ? ` — ${r.luecken} Lücke(n), siehe Prüfbericht` : ''),
            'Übrige Aufgaben: Stand des letzten Gesamtexports');
        setTimeout(() => panel(false), 5000);
    } catch (e) {
        setzeFortschritt(0, `Nachladen fehlgeschlagen: ${e.message}`, '');
        if (knopf) knopf.disabled = false;
    } finally {
        zustand.laeuft = false;
    }
};

// "Export speichern": die zuletzt gelesene Exportdatei herunterladen —
// fuer den Parallelvergleich oder die PDF-Berichte (generate_reports.py).
function speichern() {
    const erg = zustand.letzterExport;
    if (!erg) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(erg.data)], { type: 'application/json' }));
    a.download = erg.dateiname;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// Moodle zeigt eine "Datei" je nach Einstellung eingebettet (Rahmen mit
// fester Hoehe) oder im Pop-up (Standard 620 x 450). Dann gibt es einen
// Knopf, der das Dashboard ins ganze Fenster holt.
function vollbildKnopf() {
    let eingebettet = false;
    try { eingebettet = window.self !== window.top; } catch (e) { eingebettet = true; }
    const popup = !eingebettet && Boolean(window.opener)
        && window.outerWidth < screen.availWidth * 0.9;
    if (!eingebettet && !popup) return null;

    const a = document.createElement('a');
    a.href = location.href;
    // Eingebettet: Moodle-Seite im selben Tab ersetzen; Pop-up: neuer Tab
    a.target = eingebettet ? '_top' : '_blank';
    a.rel = 'noopener';
    a.className = 'nav-btn nav-btn-primary';
    a.title = 'Moodle zeigt das Dashboard in einem kleinen Rahmen — im ganzen Fenster öffnen';
    a.innerHTML = '<span class="tab-text">Im ganzen Fenster öffnen</span>';
    return a;
}

document.addEventListener('DOMContentLoaded', () => {
    const laden = document.querySelector('button[onclick*="filePickerInput"]');
    if (!laden) return;
    const vollbild = vollbildKnopf();
    if (vollbild) laden.before(vollbild);
    const knopf = document.createElement('button');
    knopf.id = 'exportSpeichernBtn';
    knopf.className = 'nav-btn';
    knopf.hidden = true;
    knopf.title = 'Zuletzt gelesene Exportdatei herunterladen (enthält Schülernamen)';
    // Symbol aus dem vorhandenen Sprite (es gibt kein eigenes Download-Symbol)
    knopf.innerHTML = '<svg class="icon" width="18" height="18" aria-hidden="true"><use href="#icon-csv"></use></svg>'
                    + '<span class="tab-text">Export speichern</span>';
    knopf.addEventListener('click', speichern);
    laden.after(knopf);
});
})();
