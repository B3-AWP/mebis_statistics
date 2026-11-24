// ============================================================
// exporter.js — Moodle-Export im Browser (Lehrkraefte-Sitzung)
//
// Gegenstueck zu src/export/exporter.py: liest dieselben Moodle-Seiten,
// wendet dieselben Pruefschichten an (src/export/pruefung.py) und
// erzeugt dieselbe Export-JSON im Schema 3. Statt Selenium: fetch in
// der Sitzung der angemeldeten Lehrkraft, DOMParser statt Browserfenster.
//
// Wer hier eine Regel aendert, aendert sie auch in exporter.py — der
// Parallelvergleich (tests/vergleiche_exporte.py) deckt Abweichungen auf.
// ============================================================

// Gekapselt: Die Datei laeuft auch neben dashboard.js (ByCS-Dashboard);
// nach aussen geht nur window.MebisExport.
(function () {
'use strict';

// window.EXPORT_BASIS nur fuer den lokalen Test gegen nachgebaute Seiten
const BASIS = window.EXPORT_BASIS || 'https://lernplattform.bycs.de';
const EXPORT_SCHEMA_VERSION = 3;
// Gleichzeitige Abrufe. 6 statt anfangs 4: spuerbar schneller, ohne ByCS
// mit einer Lehrkraft-Sitzung uebermaessig zu belasten.
const PARALLEL = 6;
const VERSUCHE = 3;          // wie @retry(max_retries=3) im Exporter
const TIMEOUT_MS = 30000;
const MAX_SEITEN = 50;       // wie pruefung.MAX_SEITEN
const STATUS_UNBEKANNT = 'Unbekannt';
const STATUS_ENTWURF = 'Entwurf (nicht abgegeben)';   // wie pruefung.STATUS_ENTWURF
const ZAEHLWERTE_SCHLUESSEL = 'mebis-export-zaehlwerte';

class SeiteUnvollstaendig extends Error {}
class ExportValidationError extends Error {}

const statistik = { seiten: 0, nachgeladen: 0 };

// --- Hilfen ---------------------------------------------------------------

const pause = ms => new Promise(r => setTimeout(r, ms));

function grundText(e) {
    if (e instanceof SeiteUnvollstaendig) return e.message;
    if (e && e.name === 'TimeoutError') return `Zeitüberschreitung nach ${TIMEOUT_MS / 1000} s`;
    return `${(e && e.name) || 'Fehler'}: ${(e && e.message) || e}`.split('\n')[0].slice(0, 200);
}

// Sichtbarer Text wie Seleniums .text: Hilfstexte fuer Screenreader
// (accesshide/sr-only) entfernt, Leerraum zusammengefasst. DOMParser
// rendert nicht — innerText gaebe es hier nicht verlaesslich.
function txt(el) {
    if (!el) return null;
    const kopie = el.cloneNode(true);
    kopie.querySelectorAll('.accesshide, .sr-only, .visually-hidden, script, style, [hidden]')
        .forEach(e => e.remove());
    return (kopie.textContent || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
}

function idAus(href, muster = /[?&]id=(\d+)/) {
    const m = (href || '').match(muster);
    return m ? m[1] : null;
}

// Wie group_utils.extract_group_prefix
function klassenKuerzel(name) {
    if (!name) return '';
    const m = name.match(/\b([A-Z]{2,4}\d{2}[A-Z])\b/);
    if (m) return m[1];
    if (name.includes(' - ')) return name.split(' - ')[0].trim();
    return name.trim();
}

// --- Datum (wie exporter.parse_german_datetime) ----------------------------

const MONATE = { Januar: 1, Februar: 2, 'März': 3, April: 4, Mai: 5, Juni: 6, Juli: 7,
                 August: 8, September: 9, Oktober: 10, November: 11, Dezember: 12 };
const WOCHENTAGE = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];

function isoDatum(j, m, t, h = 0, min = 0) {
    const d = new Date(j, m - 1, t, h, min);
    if (d.getFullYear() !== j || d.getMonth() !== m - 1 || d.getDate() !== t
        || h > 23 || min > 59) return null;
    const z = n => String(n).padStart(2, '0');
    return `${j}-${z(m)}-${z(t)}T${z(h)}:${z(min)}:00`;
}

function parseDeutschesDatum(text) {
    if (!text || ['Keine Abgabe', '-', ''].includes(text)) return null;
    const s = text.trim().replace(/\s+/g, ' ');
    let m;
    // "Dienstag, 23. September 2025, 07:46"
    if ((m = s.match(/^(\S+), (\d{1,2})\. (\S+) (\d{4}), (\d{1,2}):(\d{2})$/))
            && WOCHENTAGE.includes(m[1]) && MONATE[m[3]]) {
        return isoDatum(+m[4], MONATE[m[3]], +m[2], +m[5], +m[6]);
    }
    // "24. September 2025 08:12"
    if ((m = s.match(/^(\d{1,2})\. (\S+) (\d{4}) (\d{1,2}):(\d{2})$/)) && MONATE[m[2]]) {
        return isoDatum(+m[3], MONATE[m[2]], +m[1], +m[4], +m[5]);
    }
    // "09.01.2026 14:30"
    if ((m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4}) (\d{1,2}):(\d{2})$/))) {
        return isoDatum(+m[3], +m[2], +m[1], +m[4], +m[5]);
    }
    // "09.01.2026"
    if ((m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/))) {
        return isoDatum(+m[3], +m[2], +m[1]);
    }
    return null;
}

// Wie exporter.feedback_als_datum: nur ein Feld, das ausschliesslich ein
// Datum enthaelt, ueberschreibt das Abgabedatum.
const FEEDBACK_DATUM = /^(?:\p{L}+,\s*)?\d{1,2}\.\s*(?:\d{1,2}\.\s*|\p{L}+\s+)\d{4}(?:,?\s+\d{1,2}:\d{2})?$/u;

function feedbackAlsDatum(feedback) {
    if (!feedback) return null;
    let text = feedback;
    if (text.includes('<')) {
        // Textknoten mit Leerzeichen verbinden — wie get_text(" ") in Python
        const dok = new DOMParser().parseFromString(text, 'text/html');
        const teile = [];
        const gang = dok.createTreeWalker(dok.body, NodeFilter.SHOW_TEXT);
        while (gang.nextNode()) teile.push(gang.currentNode.nodeValue);
        text = teile.join(' ');
    }
    text = text.replace(/\s+/g, ' ').trim();
    return FEEDBACK_DATUM.test(text) ? parseDeutschesDatum(text) : null;
}

// --- Abruf (Ebene 1: Seite) ----------------------------------------------

async function abrufen(url) {
    const antwort = await fetch(url, { credentials: 'include', signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (/\/login\//.test(antwort.url)) {
        throw new SeiteUnvollstaendig('Anmeldeseite statt Inhalt — Sitzung abgelaufen?');
    }
    if (!antwort.ok) throw new SeiteUnvollstaendig(`HTTP ${antwort.status}`);
    const html = await antwort.text();
    statistik.seiten++;
    const dok = new DOMParser().parseFromString(html, 'text/html');
    pruefeNamensfilter(dok);
    return dok;
}

// Wie pruefung.ohne_namensfilter: Die Buchstabenleiste ist ein Filter, den
// Moodle im Konto speichert. Jeder Abruf einer Personentabelle setzt ihn
// leer — tifirst/tilast (Bewertungsseite, Testbericht, Fortschritt) und
// sifirst/silast (Bewerteruebersicht, Singleview). Unbekannte Parameter
// ignoriert Moodle.
const NAMENSFILTER_PARAMETER = ['tifirst', 'tilast', 'sifirst', 'silast'];

function ohneNamensfilter(url) {
    const u = new URL(url);
    NAMENSFILTER_PARAMETER.forEach(p => u.searchParams.set(p, ''));
    return u.toString();
}

// Wie pruefung.pruefe_namensfilter: nur bei eindeutigem Befund — ein
// ausgewaehlter Buchstabe — ist die Seite unvollstaendig.
function pruefeNamensfilter(dok) {
    const buchstaben = [...dok.querySelectorAll('.initialbar li.active')]
        .filter(li => !li.classList.contains('initialbarall'))
        .map(li => (li.textContent || '').trim())
        .filter(t => t && !['alle', 'all'].includes(t.toLowerCase()));
    if (buchstaben.length) {
        throw new SeiteUnvollstaendig(`Namensfilter aktiv (${buchstaben.join(', ')}) — `
            + 'in Moodle in der Buchstabenleiste „Alle“ wählen');
    }
}

// Laedt eine Seite und liest sie; beides wird bei Fehlern wiederholt
// (wie @retry um die Lesefunktionen in exporter.py).
async function ladeGeprueft(url, lies) {
    let letzter;
    for (let v = 1; v <= VERSUCHE; v++) {
        try {
            const dok = await abrufen(url);
            return { dok, wert: lies ? lies(dok) : dok };
        } catch (e) {
            letzter = e;
            if (v < VERSUCHE) await pause(2000 * 2 ** (v - 1));
        }
    }
    throw letzter instanceof SeiteUnvollstaendig ? letzter : new SeiteUnvollstaendig(grundText(letzter));
}

// Wie pruefung.seitenwerte: nur die Nummer aus Seitenlinks, nie den Link.
function seitenwerte(dok) {
    const werte = {};
    dok.querySelectorAll('.pagination a[href], .paging a[href]').forEach(a => {
        if (a.closest('.initialbar')) return;
        let url;
        try { url = new URL(a.getAttribute('href'), BASIS); } catch (e) { return; }
        for (const p of ['page', 'start']) {
            const w = url.searchParams.get(p);
            if (w !== null && /^\d+$/.test(w)) (werte[p] = werte[p] || new Set()).add(Number(w));
        }
    });
    return werte;
}

function seitenUrl(url, param, wert) {
    const u = new URL(url);
    u.searchParams.set(param, String(wert));
    return u.toString();
}

// Wie exporter.lade_alle_seiten (samt Zuruecksetzen des Namensfilters)
async function ladeAlleSeiten(url, lies) {
    url = ohneNamensfilter(url);
    const ergebnisse = [];
    const erste = await ladeGeprueft(url, lies);
    ergebnisse.push(erste.wert);

    const basisParams = new URL(url).searchParams;
    const geladen = {};
    for (const p of ['page', 'start']) {
        const w = basisParams.get(p);
        geladen[p] = new Set([w && /^\d+$/.test(w) ? Number(w) : 0]);
    }
    const gefunden = seitenwerte(erste.dok);
    const offen = () => {
        const liste = [];
        for (const [p, set] of Object.entries(gefunden)) {
            for (const w of set) if (!geladen[p].has(w)) liste.push([p, w]);
        }
        return liste.sort((a, b) => a[0].localeCompare(b[0]) || a[1] - b[1]);
    };

    let naechste = offen();
    while (naechste.length) {
        if (ergebnisse.length >= MAX_SEITEN) {
            throw new SeiteUnvollstaendig(`mehr als ${MAX_SEITEN} Seiten — Seitenleiste unerwartet`);
        }
        const [p, w] = naechste[0];
        const seite = await ladeGeprueft(seitenUrl(url, p, w), lies);
        ergebnisse.push(seite.wert);
        geladen[p].add(w);
        statistik.nachgeladen++;
        for (const [q, set] of Object.entries(seitenwerte(seite.dok))) {
            gefunden[q] = gefunden[q] || new Set();
            set.forEach(x => gefunden[q].add(x));
        }
        naechste = offen();
    }
    return ergebnisse;
}

// Arbeitet eine Liste mit begrenzter Parallelitaet ab, Reihenfolge bleibt.
async function parallel(liste, anzahl, arbeit) {
    const ergebnisse = new Array(liste.length);
    let naechster = 0;
    async function arbeiter() {
        while (naechster < liste.length) {
            const i = naechster++;
            ergebnisse[i] = await arbeit(liste[i], i);
        }
    }
    await Promise.all(Array.from({ length: Math.min(anzahl, liste.length) }, arbeiter));
    return ergebnisse;
}

// --- Lesen der einzelnen Seiten ------------------------------------------

function selectOptionen(dok, name) {
    const sel = dok.querySelector(`select[name="${name}"]`);
    return sel ? [...sel.querySelectorAll('option')].map(o => ({ value: o.getAttribute('value'), name: txt(o) })) : [];
}

// Fortschrittsbericht: Aktivitaeten aus den Spaltenkoepfen
function aktivitaetenAusFortschritt(dok) {
    const akt = { assignments: [], checklists: [], feedbacks: [], quizzes: [] };
    const gesehen = new Set();
    const typen = [['mod/assign/view.php?id=', 'assignments'], ['mod/checklist/view.php?id=', 'checklists'],
                   ['mod/feedback/view.php?id=', 'feedbacks'], ['mod/quiz/view.php?id=', 'quizzes']];
    dok.querySelectorAll('#completion-progress thead th.completion-header a').forEach(a => {
        const href = a.getAttribute('href') || '';
        for (const [muster, typ] of typen) {
            if (!href.includes(muster)) continue;
            const id = idAus(href);
            if (id && !gesehen.has(id)) {
                akt[typ].push({ id, title: a.getAttribute('title'), url: new URL(href, BASIS).toString() });
                gesehen.add(id);
            }
        }
    });
    return { akt, gesehen };
}

// Quiz-Index ergaenzt Tests ohne Abschlussverfolgung (wie Methode 3)
function quizzeAusIndex(dok, akt, gesehen) {
    dok.querySelectorAll("a[href*='mod/quiz/view.php']").forEach(a => {
        const href = a.getAttribute('href') || '';
        const id = idAus(href);
        if (!id || gesehen.has(id)) return;
        const titel = (a.textContent || '').trim() || a.getAttribute('title') || `Quiz ${id}`;
        akt.quizzes.push({ id, title: titel, url: new URL(href, BASIS).toString() });
        gesehen.add(id);
    });
}

// Notenkategorien (wie get_all_activity_categories)
function kategorienAusNotenbuch(dok) {
    const daten = {};
    dok.querySelectorAll('a.gradeitemheader').forEach(a => {
        let tr = null;
        for (let el = a.parentElement; el; el = el.parentElement) if (el.tagName === 'TR') tr = el;
        if (!tr) return;
        const katId = tr.getAttribute('data-parent-category');
        const katTr = dok.getElementById('grade-item-' + katId);
        const input = katTr ? katTr.querySelector('input.itemselect') : null;
        const id = idAus(a.getAttribute('href'), /\?id=(\d+)/);
        if (!input || !id) return;
        daten[id] = {
            category_id: katId,
            category_name: input.getAttribute('data-toggle-selectall'),
            grade_item_id: tr.getAttribute('data-itemid') || null
        };
    });
    return daten;
}

// Gruppenmitglieder einer Seite des Fortschrittsberichts
function liesGruppenseite(dok) {
    const tabelle = dok.querySelector('#completion-progress');
    if (!tabelle) {
        if (!dok.querySelector('select[name="group"]')) throw new SeiteUnvollstaendig('Fortschrittsbericht nicht erkannt');
        return [];
    }
    const users = [];
    tabelle.querySelectorAll('tbody th[scope="row"] a').forEach(a => {
        const id = idAus(a.getAttribute('href'));
        if (id) users.push({ id, name: txt(a) });
    });
    return users;
}

// Bewertungsseite (wie get_assignment_status + _bewertungszeilen_auswerten)
function liesBewertungsseite(dok) {
    if (!dok.querySelector('tbody')) throw new SeiteUnvollstaendig('Bewertungstabelle nicht gefunden');
    let gradeCol = null, timeCol = null;
    dok.querySelectorAll('th.header').forEach(h => {
        const t = txt(h);
        const cls = (h.getAttribute('class') || '').split(/\s+/).filter(Boolean);
        const sortby = h.getAttribute('data-sortby') || '';
        if (t.includes('Endbewertung')) gradeCol = cls[1] || null;
        if (t.includes('Zuletzt geändert (Abgabe)') || sortby.includes('timesubmitted')) timeCol = cls[1] || null;
    });
    if (!gradeCol) throw new SeiteUnvollstaendig("Spalte 'Endbewertung' nicht gefunden");
    const feld = (row, sel) => { const el = row.querySelector(sel); return el ? txt(el) : null; };
    return [...dok.querySelector('tbody').querySelectorAll('tr')].map(row => ({
        cls: row.getAttribute('class') || '',
        status: feld(row, 'div.submissionstatussubmitted'),
        entwurf: !!row.querySelector('div.submissionstatusdraft'),
        status2: feld(row, 'div.submissiongraded'),
        submission: feld(row, 'div.assignsubmission_onlinetext .no-overflow p'),
        grade: feld(row, 'td.cell.' + gradeCol),
        time: timeCol ? feld(row, 'td.cell.' + timeCol) : null
    }));
}

const OHNE_NOTE = ['Keine Bewertung', '-', ''];

function bewertungszeilenAuswerten(zeilen) {
    const ergebnis = [], gesehen = new Set();
    for (const row of zeilen) {
        const m = row.cls.match(/user(\d+)/);
        if (!m || gesehen.has(m[1])) continue;
        gesehen.add(m[1]);
        // Entwurf: gespeichert, nicht eingereicht — hat trotzdem ein Datum
        let status = row.status ?? (row.entwurf ? STATUS_ENTWURF : 'Nicht eingereicht');
        let status2 = row.status2 ?? 'Nicht bewertet';
        const grade = row.grade ?? 'Keine Bewertung';
        if (grade && !OHNE_NOTE.includes(grade)) {
            if (status === 'Nicht eingereicht' || status === STATUS_ENTWURF) status = 'Zur Bewertung abgegeben';
            if (status2 === 'Nicht bewertet') status2 = 'Bewertet';
        }
        ergebnis.push({
            user_id: m[1], status, status2,
            submission: row.submission ?? 'Keine Abgabe',
            submission_time: row.time !== null ? parseDeutschesDatum(row.time) : null,
            grade_options: [], grade
        });
    }
    return ergebnis;
}

// Singleview: Feedback-Datum je Person (wie get_singleview_feedback_dates)
function liesSingleview(dok) {
    const tabelle = dok.querySelector('table#singleview-grades');
    if (!tabelle) throw new SeiteUnvollstaendig('Singleview-Tabelle nicht gefunden');
    const daten = {};
    tabelle.querySelectorAll('tbody tr').forEach(row => {
        const id = idAus((row.querySelector("a[href*='user/view.php?id=']") || {}).getAttribute?.('href'),
                         /user\/view\.php\?id=(\d+)/);
        const zelle = row.querySelector('td.cell.c4');
        if (!id || !zelle) return;
        let text = txt(zelle);
        if (!text) { const ta = zelle.querySelector('textarea'); if (ta) text = ta.value || ta.textContent || ''; }
        if (!text) { const inp = zelle.querySelector("input[type='text']"); if (inp) text = inp.getAttribute('value') || ''; }
        const datum = feedbackAlsDatum(text);
        if (datum) daten[id] = datum;
    });
    return daten;
}

// Testbericht: [user_id, Beendet-Text] je Versuchszeile
function liesTestbericht(dok) {
    if (!(dok.body && (dok.body.id || '').includes('mod-quiz-report'))) {
        throw new SeiteUnvollstaendig('Testbericht nicht erkannt');
    }
    const tabelle = dok.getElementById('attempts');
    if (!tabelle) return [];
    let spalte = null;
    for (const th of tabelle.querySelectorAll('th')) {
        const t = txt(th), sortby = th.getAttribute('data-sortby') || '';
        if (t.includes('Beendet') || sortby.includes('timefinish')) {
            const m = (th.getAttribute('class') || '').match(/\bc\d+\b/);
            if (m) { spalte = m[0]; break; }
        }
    }
    spalte = spalte || 'c7';
    const tbody = tabelle.querySelector('tbody');
    if (!tbody) return [];
    const zeilen = [];
    tbody.querySelectorAll('tr').forEach(row => {
        const link = row.querySelector("td.cell.c2 a[href*='user/view.php?id=']")
                  || row.querySelector("td.cell.c1 a[href*='user/view.php?id=']")
                  || row.querySelector("td a[href*='user/view.php?id=']");
        if (!link) return;
        const zelle = row.querySelector('td.cell.' + spalte);
        zeilen.push([idAus(link.getAttribute('href')), zelle ? txt(zelle) : null]);
    });
    return zeilen;
}

// Bewerteruebersicht (wie get_grader_report_data)
function liesBewerteruebersicht(dok) {
    const tabelle = dok.querySelector('table.gradereport-grader-table#user-grades');
    if (!tabelle) throw new SeiteUnvollstaendig('Tabelle der Bewerterübersicht nicht gefunden');
    const spalten = {};
    tabelle.querySelectorAll('th a.gradeitemheader').forEach(a => {
        const href = a.getAttribute('href') || '';
        const th = a.closest('th');
        const cm = th && (th.className || '').match(/\b(c\d+)\b/);
        const id = idAus(href);
        const typ = href.includes('mod/quiz/') ? 'quiz' : href.includes('mod/assign/') ? 'assignment' : null;
        if (!cm || !id || !typ || spalten[cm[1]]) return;
        spalten[cm[1]] = { id, type: typ, title: a.getAttribute('title') || a.textContent, url: href };
    });
    const aktivitaeten = {};
    Object.entries(spalten).forEach(([col, info]) => {
        aktivitaeten[info.id] = { type: info.type, title: info.title, url: info.url, column_class: col, grades: {} };
    });
    // Wie extractGradeText in exporter.py. Im Bearbeitungsmodus traegt
    // jede Zelle ein Eingabefeld und eine versteckte Beschriftung
    // ("<Name> <Aktivitaet> Bewertung") — die darf nie als Note gelesen
    // werden (Befund aus dem Parallelvergleich vom 17.11.2026).
    const noteAus = zelle => {
        const el = zelle.querySelector('.gradevalue, .gradetext');
        if (el) return el.textContent.trim();
        const eingabe = zelle.querySelector('input[type="text"], input:not([type])');
        if (eingabe) return (eingabe.getAttribute('value') || '').trim() || '-';
        const kopie = zelle.cloneNode(true);
        kopie.querySelectorAll('.accesshide, .sr-only, .visually-hidden, label, .dropdown, button, '
                             + '.dropdown-menu, [role="menu"], input, select').forEach(e => e.remove());
        let t = '';
        kopie.childNodes.forEach(n => { if (n.nodeType === 3) t += n.textContent; });
        if (t.trim()) return t.trim();
        const rest = kopie.textContent.replace(/Zellaktionen/g, '').trim().split('\n')[0].trim();
        return rest || '-';
    };
    const personen = [];
    const bearbeitungsmodus = Boolean(dok.body && dok.body.classList.contains('editing'))
        || Boolean(tabelle.querySelector('td input[type="text"]'));
    tabelle.querySelectorAll('tbody tr').forEach(row => {
        const link = row.querySelector('th a[href*="user/view.php?id="]');
        const uid = link && idAus(link.getAttribute('href'));
        if (!uid) return;
        personen.push(uid);
        row.querySelectorAll('td').forEach(zelle => {
            const cm = (zelle.className || '').match(/\b(c\d+)\b/);
            if (cm && spalten[cm[1]]) aktivitaeten[spalten[cm[1]].id].grades[uid] = noteAus(zelle);
        });
    });
    return { aktivitaeten, personen, bearbeitungsmodus };
}

// --- Pruefschichten (wie pruefung.py) ------------------------------------

function unbekannterStatus(userId, grund) {
    return { user_id: userId, status: STATUS_UNBEKANNT, status2: STATUS_UNBEKANNT,
             submission: STATUS_UNBEKANNT, submission_time: null, grade_options: [],
             grade: '-', unbekannt: true, grund };
}

function giltFuerGruppe(aufgabenGruppen, gruppenname) {
    if (!aufgabenGruppen || aufgabenGruppen === 'all') return true;
    return klassenKuerzel(aufgabenGruppen) === klassenKuerzel(gruppenname);
}

function hatAbgabe(s) {
    if (s.unbekannt) return false;
    const mitNote = ![null, undefined, '', '-', 'Nicht bewertet', 'Nicht eingereicht', 'Keine Bewertung'].includes(s.grade);
    const abgabe = Boolean(s.submission_time) && s.status !== STATUS_ENTWURF;
    return abgabe || mitNote || s.status2 === 'Bewertet';
}

function zaehlwerte(exp) {
    const kursVon = {}, erg = {};
    Object.entries(exp.kurse || {}).forEach(([kid, k]) => (k.activities_by_category || []).forEach(kat =>
        ['assignments', 'quizzes'].forEach(t => (kat[t] || []).forEach(a => { kursVon[String(a.id)] = String(kid); }))));
    (exp.groups || []).forEach(g => {
        const klasse = klassenKuerzel(g.name || '');
        (g.users || []).forEach(u => {
            const acts = u.activities || {};
            [...(acts.assignments || []), ...(acts.quizzes || [])].forEach(a => {
                const key = `${kursVon[String(a.id)] || '?'}/${a.id}`;
                const z = ((erg[key] = erg[key] || {})[klasse] = erg[key][klasse] || { abgegeben: 0, bewertet: 0, unbekannt: 0 });
                const s = a.status || {};
                if (s.unbekannt) { z.unbekannt++; return; }
                if (hatAbgabe(s)) z.abgegeben++;
                if (s.status2 === 'Bewertet') z.bewertet++;
            });
        });
    });
    return erg;
}

function vergleicheZaehlwerte(alt, neu, titel) {
    const meldungen = [];
    Object.keys(alt).sort().forEach(key => {
        const cmid = key.split('/').pop();
        const name = titel[cmid] || `cmid ${cmid}`;
        if (!neu[key]) { meldungen.push(`${name}: fehlt im neuen Export (war im letzten Lauf enthalten)`); return; }
        Object.keys(alt[key]).sort().forEach(klasse => {
            const vorher = alt[key][klasse], jetzt = neu[key][klasse];
            if (!jetzt) { meldungen.push(`${name}, ${klasse}: Klasse fehlt im neuen Export`); return; }
            if (jetzt.unbekannt) return;
            for (const f of ['abgegeben', 'bewertet']) {
                if (jetzt[f] < vorher[f]) meldungen.push(`${name}, ${klasse}: ${f} ${vorher[f]} → ${jetzt[f]}`);
            }
        });
    });
    return meldungen;
}

function fuehreGruppenZusammen(ziel, quelle) {
    const gruppen = new Map(ziel.map(g => [g.name, g]));
    for (const g of quelle) {
        const vorhanden = gruppen.get(g.name);
        if (!vorhanden) { ziel.push(g); gruppen.set(g.name, g); continue; }
        const personen = new Map(vorhanden.users.map(u => [u.id, u]));
        for (const u of g.users) {
            const bekannt = personen.get(u.id);
            if (!bekannt) { vorhanden.users.push(u); personen.set(u.id, u); continue; }
            for (const [typ, eintraege] of Object.entries(u.activities || {})) {
                const liste = (bekannt.activities[typ] = bekannt.activities[typ] || []);
                const ids = new Set(liste.map(e => e.id));
                eintraege.forEach(e => { if (!ids.has(e.id)) liste.push(e); });
            }
        }
    }
}

// --- Bausteine: eine Aufgabe, ein Test, die Bewerteruebersicht -------------
//
// Gesamtexport (exportiereKurs) und Nachladen einer einzelnen Aktivitaet
// (aktualisiereAktivitaet) nutzen dieselben Bausteine — sonst liefen die
// Regeln auseinander.

// Eine Aufgabe lesen (wie process_assignment_parallel)
async function liesAufgabe(a, kursId) {
    try {
        // Keine Gruppenabfrage mehr (wie exporter.py): Die Aufgabenseite
        // lieferte stets "all", die Bewertungsseite wird mit group=0 gelesen.
        const gruppen = 'all';
        const seiten = await ladeAlleSeiten(`${a.url}&action=grading&status&quickgrading=0&group=0`, liesBewertungsseite);
        const status = bewertungszeilenAuswerten(seiten.flat());
        if (a.grade_item_id) {
            let daten = {};
            try {
                daten = (await ladeGeprueft(ohneNamensfilter(`${BASIS}/grade/report/singleview/index.php?id=${kursId}`
                    + `&userid=0&itemid=${a.grade_item_id}&item=grade&page=0&perpage=0`), liesSingleview)).wert;
            } catch (e) { /* Datum ist Ergaenzung */ }
            status.forEach(s => { if (daten[s.user_id]) s.submission_time = daten[s.user_id]; });
            for (const s of status) {
                if (s.submission_time === null && s.grade && !OHNE_NOTE.includes(s.grade)) {
                    try {
                        const h = await ladeGeprueft(`${BASIS}/grade/report/history/index.php?id=${kursId}`
                            + `&showreport=1&itemid=${a.grade_item_id}&userids=${s.user_id}&tsort=timemodified&tdir=3`);
                        const zelle = h.dok.querySelector('table.gradereport_history tbody tr:first-child td.c0');
                        const t = zelle ? txt(zelle) : '';
                        if (t && t !== '-') s.submission_time = parseDeutschesDatum(t);
                    } catch (e) { /* wie Python: kein Datum */ }
                }
            }
        }
        return { status, gruppen, grund: null };
    } catch (e) {
        return { status: null, gruppen: 'all', grund: grundText(e) };
    }
}

// Abgabezeiten eines Tests (wie process_quiz_parallel)
async function liesTestzeiten(q, kursId, hinweise) {
    const zeiten = {};
    try {
        const url = `${BASIS}/mod/quiz/report.php?id=${q.id}&mode=overview&attempts=enrolled_with`
                  + `&onlygraded&group=0&onlyregraded=0&slotmarks=1&tsort=timefinish&tdir=3`;
        for (const [uid, roh] of (await ladeAlleSeiten(url, liesTestbericht)).flat()) {
            if (!uid || zeiten[uid] || !roh) continue;
            const d = parseDeutschesDatum(roh);
            if (d) zeiten[uid] = d;
        }
    } catch (e) {
        hinweise.push(`Test '${q.title}': Abgabezeiten unvollständig (${grundText(e)})`);
    }
    if (q.grade_item_id) {
        try {
            const daten = (await ladeGeprueft(ohneNamensfilter(`${BASIS}/grade/report/singleview/index.php?id=${kursId}`
                + `&userid=0&itemid=${q.grade_item_id}&item=grade&page=0&perpage=0`), liesSingleview)).wert;
            Object.entries(daten).forEach(([uid, d]) => { if (!zeiten[uid]) zeiten[uid] = d; });
        } catch (e) { /* Datum ist Ergaenzung */ }
    }
    return zeiten;
}

// Bewerteruebersicht, alle Teilseiten (Teststatus fuer alle Tests)
async function liesBewerteruebersichtKomplett(kursId, hinweise) {
    const grader = {}, graderPersonen = new Set();
    let graderGrund = null;
    try {
        for (const seite of await ladeAlleSeiten(`${BASIS}/grade/report/grader/index.php?id=${kursId}&groupsearchvalue=&group=0`,
                                                 liesBewerteruebersicht)) {
            seite.personen.forEach(p => graderPersonen.add(p));
            if (seite.bearbeitungsmodus && !hinweise.some(h => h.startsWith('Bearbeitungsmodus'))) {
                hinweise.push('Bearbeitungsmodus war in Moodle eingeschaltet — Noten wurden aus den '
                            + 'Eingabefeldern gelesen. Für den Export am besten ausschalten.');
            }
            Object.entries(seite.aktivitaeten).forEach(([id, d]) => {
                const z = (grader[id] = grader[id] || { ...d, grades: {} });
                Object.assign(z.grades, d.grades);
            });
        }
    } catch (e) {
        graderGrund = grundText(e);
    }
    return { grader, graderPersonen, graderGrund };
}

/**
 * Traegt den Status der angegebenen Aktivitaeten bei allen Personen ein —
 * mit Abgleich (Ebene 2) — und liefert die Luecken dazu.
 *
 * Vorhandene Eintraege derselben Aktivitaet werden ersetzt; andere
 * Aktivitaeten einer Person bleiben unberuehrt. So dient die Funktion dem
 * Gesamtexport wie dem Nachladen einer einzelnen Aufgabe.
 *
 * @param {Object[]} gruppen - Gruppen mit users (werden veraendert)
 * @param {{assignments: Object[], quizzes: Object[]}} akt - zu setzende Aktivitaeten
 * @param {Object} k - Kontext: planCmids, imPlan, aufgaben {id: liesAufgabe-Ergebnis},
 *                     testZeiten, grader, graderPersonen, graderGrund
 * @returns {Object[]} Luecken
 */
function setzeStatus(gruppen, akt, k) {
    const luecken = [];
    for (const a of akt.assignments) {
        const r = k.aufgaben[a.id];
        if (r.status === null) {
            luecken.push({ cmid: a.id, titel: a.title || a.id, typ: 'assign', personen: 'alle', grund: r.grund || 'unbekannt' });
        }
    }
    const testsUnbekannt = {};
    for (const q of akt.quizzes) {
        if (!k.planCmids.has(q.id)) continue;
        if (k.graderGrund) testsUnbekannt[q.id] = `Bewerterübersicht: ${k.graderGrund}`;
        else if (!k.grader[q.id]) testsUnbekannt[q.id] = 'keine Spalte in der Bewerterübersicht';
        if (testsUnbekannt[q.id]) {
            luecken.push({ cmid: q.id, titel: q.title || q.id, typ: 'quiz', personen: 'alle', grund: testsUnbekannt[q.id] });
        }
    }

    const ersetze = (liste, eintrag) => {
        const i = liste.findIndex(e => e.id === eintrag.id);
        if (i >= 0) liste.splice(i, 1, eintrag); else liste.push(eintrag);
    };
    const entferne = (liste, id) => {
        const i = liste.findIndex(e => e.id === id);
        if (i >= 0) liste.splice(i, 1);
    };

    const fehltInAufgabe = {}, fehltInUebersicht = new Set();
    const planTestsDabei = akt.quizzes.some(q => k.planCmids.has(q.id));
    for (const g of gruppen) {
        const abgleichen = k.imPlan(g.name);
        for (const u of g.users) {
            u.activities = u.activities || { assignments: [], checklists: [], feedbacks: [], quizzes: [] };
            for (const a of akt.assignments) {
                const r = k.aufgaben[a.id];
                let s = null;
                if (r.status === null) {
                    s = unbekannterStatus(u.id, r.grund || 'unbekannt');
                } else {
                    s = r.status.find(x => x.user_id === u.id) || null;
                    if (!s && abgleichen && giltFuerGruppe(r.gruppen, g.name)) {
                        s = unbekannterStatus(u.id, 'fehlt in der Bewertungstabelle');
                        (fehltInAufgabe[a.id] = fehltInAufgabe[a.id] || new Set()).add(u.id);
                    }
                }
                if (s) ersetze(u.activities.assignments, { id: a.id, status: s, category_id: a.category_id, category_name: a.category_name });
                else entferne(u.activities.assignments, a.id);
            }
            const fehltZeile = abgleichen && !k.graderGrund && !k.graderPersonen.has(u.id);
            if (fehltZeile && planTestsDabei) fehltInUebersicht.add(u.id);
            for (const q of akt.quizzes) {
                let s = null;
                if (testsUnbekannt[q.id]) s = unbekannterStatus(u.id, testsUnbekannt[q.id]);
                else if (fehltZeile && k.planCmids.has(q.id)) s = unbekannterStatus(u.id, 'fehlt in der Bewerterübersicht');
                else if (k.grader[q.id] && u.id in k.grader[q.id].grades) {
                    const grade = k.grader[q.id].grades[u.id];
                    const offen = grade === '-' || grade === '' || grade.includes('Nicht bewertet');
                    s = { user_id: u.id,
                          status: offen ? 'Nicht eingereicht' : 'Zur Bewertung abgegeben',
                          status2: offen ? 'Nicht bewertet' : 'Bewertet',
                          submission: offen ? 'Nicht abgeschlossen' : 'Quiz abgeschlossen',
                          submission_time: (k.testZeiten[q.id] || {})[u.id] || null,
                          grade_options: [], grade };
                }
                if (s) ersetze(u.activities.quizzes, { id: q.id, status: s, category_id: q.category_id, category_name: q.category_name });
                else entferne(u.activities.quizzes, q.id);
            }
        }
    }
    Object.keys(fehltInAufgabe).sort().forEach(aid => {
        const a = akt.assignments.find(x => x.id === aid);
        luecken.push({ cmid: aid, titel: a ? a.title : aid, typ: 'assign',
                       personen: [...fehltInAufgabe[aid]].sort(), grund: 'fehlt in der Bewertungstabelle' });
    });
    if (fehltInUebersicht.size) {
        akt.quizzes.forEach(q => {
            if (k.planCmids.has(q.id) && !testsUnbekannt[q.id]) {
                luecken.push({ cmid: q.id, titel: q.title || q.id, typ: 'quiz',
                               personen: [...fehltInUebersicht].sort(), grund: 'fehlt in der Bewerterübersicht' });
            }
        });
    }
    return luecken;
}

function kontext(kursRoh, plan) {
    return {
        planCmids: new Set((kursRoh.aufgaben || []).map(a => String(a.cmid))),
        imPlan: name => Boolean((plan.klassenZuSchiene || {})[klassenKuerzel(name)]),
        aufgaben: {}, testZeiten: {}, grader: {}, graderPersonen: new Set(), graderGrund: null
    };
}

// --- Kurs exportieren (wie export_course) --------------------------------

async function exportiereKurs(kurs, plan, melde) {
    const kursId = kurs.moodleCourseId;
    const hinweise = [];
    const k = kontext(kurs, plan);
    const basisUrl = `${BASIS}/report/progress/index.php`;

    melde(`Kurs ${kurs.titel}: Aktivitäten und Gruppen`);
    // Ohne Namensfilter: Findet er niemanden, fehlt die Tabelle samt Aktivitaeten
    const fort = await ladeGeprueft(ohneNamensfilter(`${basisUrl}?course=${kursId}`), dok => {
        if (!dok.querySelector('select[name="group"]')) throw new SeiteUnvollstaendig('Fortschrittsbericht nicht erkannt');
        return dok;
    });
    const gruppenOptionen = selectOptionen(fort.dok, 'group');
    const { akt, gesehen } = aktivitaetenAusFortschritt(fort.dok);
    try {
        quizzeAusIndex((await ladeGeprueft(`${BASIS}/mod/quiz/index.php?id=${kursId}`)).dok, akt, gesehen);
    } catch (e) {
        hinweise.push(`Quiz-Index nicht lesbar (${grundText(e)}) — Tests ohne Abschlussverfolgung fehlen`);
    }
    akt.checklists = [];  // wie EXPORT_CHECKLISTS = False

    const kategorien = (await ladeGeprueft(`${BASIS}/grade/edit/tree/index.php?id=${kursId}`, dok => {
        if (!dok.querySelector('a.gradeitemheader')) throw new SeiteUnvollstaendig('Notenkategorien nicht gefunden');
        return kategorienAusNotenbuch(dok);
    })).wert;

    const nachKategorie = [];
    for (const typ of ['assignments', 'checklists', 'feedbacks', 'quizzes']) {
        for (const a of akt[typ]) {
            Object.assign(a, kategorien[a.id] || { category_id: '-1', category_name: 'nicht bewertet' });
            let kat = nachKategorie.find(x => x.id === a.category_id);
            if (!kat) {
                kat = { id: a.category_id, category_name: a.category_name,
                        assignments: [], checklists: [], feedbacks: [], quizzes: [] };
                nachKategorie.push(kat);
            }
            kat[typ].push(a);
        }
    }

    // Aufgaben
    let erledigt = 0;
    await parallel(akt.assignments, PARALLEL, async (a) => {
        k.aufgaben[a.id] = await liesAufgabe(a, kursId);
        a.groups = k.aufgaben[a.id].gruppen;
        melde(`Aufgaben ${++erledigt}/${akt.assignments.length}`, true);
    });

    // Tests: Abgabezeiten
    erledigt = 0;
    await parallel(akt.quizzes, PARALLEL, async (q) => {
        k.testZeiten[q.id] = await liesTestzeiten(q, kursId, hinweise);
        melde(`Tests ${++erledigt}/${akt.quizzes.length}`, true);
    });

    // Gruppenmitglieder
    melde(`Kurs ${kurs.titel}: Gruppenmitglieder`);
    const gruppen = [], gruppenFehler = [];
    await parallel(gruppenOptionen.filter(g => g.value !== '0'), PARALLEL, async (g) => {
        try {
            const seiten = await ladeAlleSeiten(`${basisUrl}?course=${kursId}&group=${g.value}`, liesGruppenseite);
            const eindeutig = new Map();
            seiten.flat().forEach(u => { if (!eindeutig.has(u.id)) eindeutig.set(u.id, u); });
            gruppen.push({ name: g.name, value: g.value, users: [...eindeutig.values()] });
        } catch (e) {
            if (k.imPlan(g.name)) gruppenFehler.push(`${g.name}: ${grundText(e)}`);
            else hinweise.push(`Gruppe '${g.name}' nicht ladbar (${grundText(e)}) — nicht im Plan, ohne Auswirkung`);
        }
    });
    // Reihenfolge wie im Auswahlfeld, unabhaengig von der Abrufreihenfolge
    gruppen.sort((a, b) => gruppenOptionen.findIndex(o => o.value === a.value) - gruppenOptionen.findIndex(o => o.value === b.value));

    // Bewerteruebersicht
    melde(`Kurs ${kurs.titel}: Bewerterübersicht`);
    Object.assign(k, await liesBewerteruebersichtKomplett(kursId, hinweise));

    // Zusammenfuehren mit Abgleich (Ebene 2)
    gruppen.forEach(g => g.users.forEach(u => {
        u.activities = { assignments: [], checklists: [], feedbacks: [], quizzes: [] };
    }));
    const luecken = setzeStatus(gruppen, akt, k);

    // Validierung (kritisch = Kurs unbrauchbar)
    const fehler = gruppenFehler.map(f => `Gruppenmitglieder nicht ladbar — ${f}`);
    if (!akt.assignments.length && !akt.quizzes.length) fehler.push('Keine Aktivitäten gefunden');
    if (!gruppen.length) fehler.push('Keine Gruppen gefunden');
    else if (!gruppen.some(g => g.users.length)) fehler.push('Keine Benutzer in Gruppen gefunden');
    if (akt.assignments.length && !akt.assignments.some(a => k.aufgaben[a.id].status !== null)) {
        fehler.push('Assignments gefunden, aber keine einzige Bewertungsseite lesbar');
    }
    if (fehler.length) throw new ExportValidationError(`Kurs ${kursId}: ${fehler.join('; ')}`);

    return {
        activities_by_category: nachKategorie,
        groups: gruppen,
        activityincludes: selectOptionen(fort.dok, 'activityinclude'),
        activitysections: selectOptionen(fort.dok, 'activitysection'),
        course_id: String(kursId),
        titel: kurs.titel,
        pruefbericht: {
            luecken, hinweise,
            personen_gruppen: gruppen.reduce((n, g) => n + g.users.length, 0),
            personen_bewerteruebersicht: k.graderPersonen.size
        }
    };
}

/**
 * Laedt eine einzelne Aufgabe oder einen Test neu und traegt das Ergebnis
 * in einen vorhandenen Export ein (wird veraendert).
 *
 * Gelesen wird mit denselben Bausteinen und Pruefregeln wie beim
 * Gesamtexport. Ein Test braucht dafuer die ganze Bewerteruebersicht
 * (dort steht der Teststatus), eine Aufgabe nur ihre Bewertungsseite.
 * Die Luecken dieser Aktivitaet im Pruefbericht werden ersetzt; der
 * Verlaufsvergleich bleibt unveraendert (er gehoert zum Gesamtlauf).
 *
 * @param {Object} exportDaten - Export im Schema 3
 * @param {Object} plan - plan.json (roh)
 * @param {string} cmid - Aktivitaet
 * @returns {Promise<{titel: string, luecken: number, typ: string}>}
 */
async function aktualisiereAktivitaet(exportDaten, plan, cmid) {
    cmid = String(cmid);
    let kursId = null, aktivitaet = null, typ = null;
    for (const [kid, kursDaten] of Object.entries(exportDaten.kurse || {})) {
        for (const kat of kursDaten.activities_by_category || []) {
            for (const t of ['assignments', 'quizzes']) {
                const a = (kat[t] || []).find(x => String(x.id) === cmid);
                if (a) { kursId = kid; aktivitaet = a; typ = t; }
            }
        }
    }
    if (!aktivitaet) throw new Error(`Aktivität ${cmid} steht nicht im Export`);
    const kursRoh = (plan.kurse || []).find(x => String(x.moodleCourseId) === kursId) || { aufgaben: [] };

    const hinweise = [];
    const k = kontext(kursRoh, plan);
    const akt = { assignments: [], quizzes: [] };
    if (typ === 'assignments') {
        k.aufgaben[cmid] = await liesAufgabe(aktivitaet, kursId);
        aktivitaet.groups = k.aufgaben[cmid].gruppen;
        akt.assignments.push(aktivitaet);
    } else {
        const [zeiten, uebersicht] = await Promise.all([
            liesTestzeiten(aktivitaet, kursId, hinweise),
            liesBewerteruebersichtKomplett(kursId, hinweise)
        ]);
        k.testZeiten[cmid] = zeiten;
        Object.assign(k, uebersicht);
        akt.quizzes.push(aktivitaet);
    }

    const luecken = setzeStatus(exportDaten.groups || [], akt, k);

    // Pruefbericht: Luecken dieser Aktivitaet ersetzen
    const kursBericht = exportDaten.kurse[kursId].pruefbericht || (exportDaten.kurse[kursId].pruefbericht = { luecken: [], hinweise: [] });
    kursBericht.luecken = (kursBericht.luecken || []).filter(l => String(l.cmid) !== cmid).concat(luecken);
    const bericht = exportDaten.pruefbericht || (exportDaten.pruefbericht = { luecken: [], hinweise: [], verlauf: [], fehlende_kurse: [] });
    bericht.luecken = (bericht.luecken || []).filter(l => !(String(l.cmid) === cmid && String(l.kurs) === kursId))
        .concat(luecken.map(l => ({ ...l, kurs: kursId })));
    for (const h of hinweise) {
        if (!(bericht.hinweise || []).includes(h)) (bericht.hinweise = bericht.hinweise || []).push(h);
    }
    return { titel: aktivitaet.title || cmid, luecken: luecken.length, typ };
}

// --- Gesamtlauf (wie main) -------------------------------------------------

function ortsZeit(d = new Date()) {
    const z = n => String(n).padStart(2, '0');
    return {
        iso: `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`,
        datei: `${d.getFullYear()}${z(d.getMonth() + 1)}${z(d.getDate())}_${z(d.getHours())}${z(d.getMinutes())}${z(d.getSeconds())}`
    };
}

async function exportiere(plan, kurse, melde) {
    statistik.seiten = 0;
    statistik.nachgeladen = 0;
    const kursDaten = {}, gruppen = [], fehlendeKurse = [];

    for (const kurs of kurse) {
        try {
            const daten = await exportiereKurs(kurs, plan, melde);
            fuehreGruppenZusammen(gruppen, daten.groups);
            delete daten.groups;
            kursDaten[String(kurs.moodleCourseId)] = daten;
        } catch (e) {
            melde(`Kurs '${kurs.titel}' übersprungen: ${grundText(e)}`);
            fehlendeKurse.push(kurs.titel);
        }
    }
    if (!Object.keys(kursDaten).length) throw new Error('Kein Kurs konnte exportiert werden.');

    const zeit = ortsZeit();
    const data = { schema: EXPORT_SCHEMA_VERSION, exported_at: zeit.iso, schuljahr: plan.schuljahr,
                   kurse: kursDaten, groups: gruppen };

    // Verlauf: Zaehlwerte (nicht personenbezogen) gegen den letzten Lauf in
    // diesem Browser. Fehlt der Speicher, entfaellt nur der Vergleich.
    const titel = {};
    Object.values(kursDaten).forEach(k => k.activities_by_category.forEach(kat =>
        ['assignments', 'quizzes'].forEach(t => kat[t].forEach(a => { titel[String(a.id)] = a.title || ''; }))));
    const neu = zaehlwerte(data);
    let verlauf = [], vergleichMit = null;
    try {
        const alt = JSON.parse(localStorage.getItem(ZAEHLWERTE_SCHLUESSEL) || 'null');
        if (alt && alt.werte) {
            verlauf = vergleicheZaehlwerte(alt.werte, neu, titel);
            vergleichMit = `Browser-Lauf vom ${alt.zeit}`;
        }
        localStorage.setItem(ZAEHLWERTE_SCHLUESSEL, JSON.stringify({ zeit: zeit.iso, werte: neu }));
    } catch (e) { /* kein Speicher: kein Vergleich */ }

    data.pruefbericht = {
        luecken: Object.entries(kursDaten).flatMap(([kid, k]) => k.pruefbericht.luecken.map(l => ({ ...l, kurs: kid }))),
        hinweise: Object.values(kursDaten).flatMap(k => k.pruefbericht.hinweise),
        fehlende_kurse: fehlendeKurse,
        verlauf,
        vergleich_mit: vergleichMit,
        seiten_nachgeladen: statistik.nachgeladen
    };
    return { data, dateiname: `output_${zeit.datei}.json`, seiten: statistik.seiten };
}

window.MebisExport = { exportiere, aktualisiereAktivitaet, parseDeutschesDatum, feedbackAlsDatum, klassenKuerzel, seitenwerte };
})();
