// ============================================================
// probe.js — Machbarkeitstest fuer das Lehrkraefte-Dashboard in ByCS
//
// Ruft dieselben Moodle-Seiten ab wie der Export (exporter.py) und
// meldet, ob sie in der Sitzung der angemeldeten Lehrkraft lesbar sind,
// ob die erwarteten Tabellen da sind und ob Moodle sie auf mehrere
// Seiten aufteilt. Ausgegeben werden nur Zaehlwerte — keine Namen,
// keine Personen-IDs. Es wird nichts gespeichert und nichts gesendet.
// ============================================================

'use strict';

// window.PROBE_BASIS nur fuer den lokalen Test gegen nachgebaute Seiten
const BASIS = window.PROBE_BASIS || 'https://lernplattform.bycs.de';
const TIMEOUT_MS = 20000;

// Gleiche Regel wie src/export/pruefung.py: aus Seitenlinks nur die
// Nummer lesen; die Buchstabenleiste (.initialbar) ist ein Filter.
function seitenwerte(dokument) {
    const werte = { page: new Set(), start: new Set() };
    dokument.querySelectorAll('.pagination a[href], .paging a[href]').forEach(a => {
        if (a.closest('.initialbar')) return;
        let url;
        try { url = new URL(a.getAttribute('href'), BASIS); } catch (e) { return; }
        for (const p of ['page', 'start']) {
            const w = url.searchParams.get(p);
            if (w !== null && /^\d+$/.test(w)) werte[p].add(Number(w));
        }
    });
    return werte;
}

function seitenText(werte) {
    const teile = [];
    for (const [p, set] of Object.entries(werte)) {
        const andere = [...set].filter(w => w !== 0).sort((a, b) => a - b);
        if (andere.length) teile.push(`${p}=${andere.join(',')}`);
    }
    return teile.length ? `aufgeteilt (${teile.join('; ')})` : 'eine Seite';
}

function mitSeite(url, param, wert) {
    const u = new URL(url);
    u.searchParams.set(param, String(wert));
    return u.toString();
}

async function lade(url) {
    const start = performance.now();
    const antwort = await fetch(url, {
        credentials: 'include',
        signal: AbortSignal.timeout(TIMEOUT_MS)
    });
    const html = await antwort.text();
    return {
        status: antwort.status,
        ok: antwort.ok,
        url: antwort.url,
        anmeldeseite: /\/login\//.test(antwort.url),
        dauerMs: Math.round(performance.now() - start),
        bytes: html.length,
        dok: new DOMParser().parseFromString(html, 'text/html')
    };
}

// IDs aus Links nur intern vergleichen, nie ausgeben.
function personenIds(dok, selektor) {
    const ids = new Set();
    dok.querySelectorAll(selektor).forEach(a => {
        const m = (a.getAttribute('href') || '').match(/[?&]id=(\d+)/);
        if (m) ids.add(m[1]);
    });
    return ids;
}

// Laedt eine Folgeseite und prueft, ob sie andere Personen liefert.
async function pruefeFolgeseite(url, werte, selektor, ersteIds) {
    for (const p of ['page', 'start']) {
        const naechste = [...werte[p]].filter(w => w !== 0).sort((a, b) => a - b)[0];
        if (naechste === undefined) continue;
        const s = await lade(mitSeite(url, p, naechste));
        const ids = personenIds(s.dok, selektor);
        const neu = [...ids].filter(id => !ersteIds.has(id)).length;
        return `Folgeseite ${p}=${naechste}: ${ids.size} Zeilen, davon ${neu} neu`;
    }
    return null;
}

const ergebnisse = [];

function melde(pruefung, stufe, details) {
    ergebnisse.push({ pruefung, stufe, details });
    const tr = document.createElement('tr');
    const klasse = { OK: 'ok', WARNUNG: 'warnung', FEHLER: 'fehler' }[stufe] || '';
    tr.innerHTML = '<td></td><td></td><td></td>';
    tr.children[0].textContent = pruefung;
    tr.children[1].textContent = stufe;
    tr.children[1].className = klasse;
    tr.children[2].textContent = details;
    document.getElementById('zeilen').appendChild(tr);
}

function grundlagen(s) {
    if (s.anmeldeseite) return 'Anmeldeseite statt Inhalt';
    if (!s.ok) return `HTTP ${s.status}`;
    return null;
}

// --- Einzelpruefungen -------------------------------------------------

async function pruefeUmgebung() {
    const gleich = location.origin === BASIS;
    melde('Herkunft der Seite', gleich ? 'OK' : 'FEHLER',
          `${location.origin}${gleich ? ' = Moodle' : ' ≠ ' + BASIS + ' — Abruf mit Sitzung nicht möglich'}`);
    return gleich;
}

async function pruefeFortschritt(kursId) {
    const url = `${BASIS}/report/progress/index.php?course=${kursId}`;
    const s = await lade(url);
    const fehler = grundlagen(s);
    if (fehler) { melde('Fortschrittsbericht (Gruppen)', 'FEHLER', fehler); return []; }

    const gruppen = [...s.dok.querySelectorAll('select[name="group"] option')]
        .map(o => o.value).filter(v => v && v !== '0');
    const tabelle = s.dok.querySelector('#completion-progress');
    const zeilen = tabelle ? tabelle.querySelectorAll('tbody th[scope="row"] a').length : 0;
    const aktivitaeten = tabelle ? tabelle.querySelectorAll('thead th.completion-header a').length : 0;
    melde('Fortschrittsbericht (Kurs)', tabelle ? 'OK' : 'FEHLER',
          `${gruppen.length} Gruppen, ${zeilen} Personen auf Seite 1, ${aktivitaeten} Aktivitäten, `
          + `${seitenText(seitenwerte(s.dok))}, ${s.dauerMs} ms`);
    return gruppen;
}

// Alle Gruppen: Der Export liest die Mitglieder je Gruppe. Ob eine Klasse
// die Seitengrenze des Berichts ueberschreitet, zeigt sich nur hier.
async function pruefeGruppen(kursId, gruppen) {
    const sel = '#completion-progress tbody th[scope="row"] a';
    let groesste = 0, aufgeteilt = 0, fehlerhaft = 0, folge = null;
    for (const gruppe of gruppen) {
        const url = `${BASIS}/report/progress/index.php?course=${kursId}&group=${gruppe}`;
        const s = await lade(url);
        if (grundlagen(s)) { fehlerhaft++; continue; }
        const ids = personenIds(s.dok, sel);
        groesste = Math.max(groesste, ids.size);
        const werte = seitenwerte(s.dok);
        if (seitenText(werte) !== 'eine Seite') {
            aufgeteilt++;
            if (!folge) folge = await pruefeFolgeseite(url, werte, sel, ids);
        }
    }
    const stufe = fehlerhaft ? 'FEHLER' : (aufgeteilt ? 'WARNUNG' : 'OK');
    let details = `${gruppen.length} Gruppen, größte mit ${groesste} Personen auf Seite 1, `
                + `${aufgeteilt} aufgeteilt, ${fehlerhaft} nicht lesbar`;
    if (folge) details += `; ${folge} — Nachladen nötig, der Export macht das`;
    melde('Fortschrittsbericht (je Gruppe)', stufe, details);
}

async function pruefeBewerteruebersicht(kursId) {
    const url = `${BASIS}/grade/report/grader/index.php?id=${kursId}&groupsearchvalue=&group=0`;
    const s = await lade(url);
    const fehler = grundlagen(s);
    if (fehler) { melde('Bewerterübersicht', 'FEHLER', fehler); return {}; }

    const tabelle = s.dok.querySelector('table.gradereport-grader-table#user-grades');
    if (!tabelle) { melde('Bewerterübersicht', 'FEHLER', 'Tabelle #user-grades fehlt'); return {}; }

    const sel = 'tbody tr th a[href*="user/view.php?id="]';
    const ids = personenIds(tabelle, sel);
    const kopf = [...tabelle.querySelectorAll('th a.gradeitemheader')].map(a => a.getAttribute('href') || '');
    const assign = kopf.find(h => h.includes('mod/assign/'));
    const quiz = kopf.find(h => h.includes('mod/quiz/'));
    const werte = seitenwerte(s.dok);
    let details = `${ids.size} Personen auf Seite 1, ${kopf.length} Bewertungsspalten `
                + `(${kopf.filter(h => h.includes('mod/assign/')).length} Aufgaben, `
                + `${kopf.filter(h => h.includes('mod/quiz/')).length} Tests), ${seitenText(werte)}, ${s.dauerMs} ms`;
    const folge = await pruefeFolgeseite(url, werte, sel, ids);
    if (folge) details += `; ${folge}`;
    melde('Bewerterübersicht', folge ? 'WARNUNG' : 'OK',
          details + (folge ? ' — Nachladen nötig, der Export macht das' : ''));

    const cmid = h => (h && h.match(/[?&]id=(\d+)/) || [])[1];
    return { assign: cmid(assign), quiz: cmid(quiz) };
}

async function pruefeBewertungsseite(cmid) {
    if (!cmid) { melde('Bewertungsseite (Aufgabe)', 'WARNUNG', 'keine Aufgabe in der Bewerterübersicht gefunden'); return; }
    const url = `${BASIS}/mod/assign/view.php?id=${cmid}&action=grading&status&quickgrading=0&group=0`;
    const s = await lade(url);
    const fehler = grundlagen(s);
    if (fehler) { melde('Bewertungsseite (Aufgabe)', 'FEHLER', fehler); return; }

    const zeilen = [...s.dok.querySelectorAll('tbody tr')].filter(tr => /user\d+/.test(tr.className));
    const endbewertung = [...s.dok.querySelectorAll('th.header')]
        .some(th => (th.textContent || '').includes('Endbewertung'));
    const werte = seitenwerte(s.dok);
    let stufe = zeilen.length && endbewertung ? 'OK' : 'FEHLER';
    let details = `cmid ${cmid}: ${zeilen.length} Personen auf Seite 1, Spalte „Endbewertung" `
                + `${endbewertung ? 'vorhanden' : 'FEHLT'}, ${seitenText(werte)}, ${s.dauerMs} ms`;
    const ids = new Set(zeilen.map(tr => tr.className.match(/user(\d+)/)[1]));
    for (const p of ['page', 'start']) {
        const n = [...werte[p]].filter(w => w !== 0).sort((a, b) => a - b)[0];
        if (n === undefined) continue;
        const f = await lade(mitSeite(url, p, n));
        const fz = [...f.dok.querySelectorAll('tbody tr')].filter(tr => /user\d+/.test(tr.className));
        const neu = fz.filter(tr => !ids.has(tr.className.match(/user(\d+)/)[1])).length;
        details += `; Folgeseite ${p}=${n}: ${fz.length} Zeilen, davon ${neu} neu`;
        if (stufe === 'OK') stufe = 'WARNUNG';
        break;
    }
    melde('Bewertungsseite (Aufgabe)', stufe, details);
}

async function pruefeTestbericht(cmid) {
    if (!cmid) { melde('Testbericht', 'WARNUNG', 'kein Test in der Bewerterübersicht gefunden'); return; }
    const url = `${BASIS}/mod/quiz/report.php?id=${cmid}&mode=overview&attempts=enrolled_with`
              + `&onlygraded&group=0&onlyregraded=0&slotmarks=1&tsort=timefinish&tdir=3`;
    const s = await lade(url);
    const fehler = grundlagen(s);
    if (fehler) { melde('Testbericht', 'FEHLER', fehler); return; }
    const istBericht = (s.dok.body && s.dok.body.id || '').includes('mod-quiz-report');
    const tabelle = s.dok.getElementById('attempts');
    const zeilen = tabelle ? tabelle.querySelectorAll('tbody tr').length : 0;
    const werte = seitenwerte(s.dok);
    melde('Testbericht', istBericht ? (seitenText(werte) === 'eine Seite' ? 'OK' : 'WARNUNG') : 'FEHLER',
          `cmid ${cmid}: body-ID ${istBericht ? 'erkannt' : 'NICHT erkannt (' + (s.dok.body && s.dok.body.id) + ')'}, `
          + `${tabelle ? zeilen + ' Versuchszeilen' : 'keine Versuchstabelle'}, ${seitenText(werte)}, ${s.dauerMs} ms`);
}

async function pruefeNotenkategorien(kursId) {
    const s = await lade(`${BASIS}/grade/edit/tree/index.php?id=${kursId}`);
    const fehler = grundlagen(s);
    if (fehler) { melde('Notenkategorien', 'FEHLER', fehler); return; }
    const links = s.dok.querySelectorAll('a[href*="mod/assign/view.php"], a[href*="mod/quiz/view.php"]').length;
    const kategorien = s.dok.querySelectorAll('input.itemselect[data-toggle-selectall]').length;
    melde('Notenkategorien', links ? 'OK' : 'FEHLER', `${links} Aktivitätslinks, ${kategorien} Kategoriezeilen, ${s.dauerMs} ms`);
}

async function pruefeKursuebersicht(kursId) {
    // Moodle 5: Aktivitaetsuebersicht; das Schueler-Dashboard liest sie.
    const s = await lade(`${BASIS}/course/overview.php?id=${kursId}&expand[]=assign`);
    const fehler = grundlagen(s);
    if (fehler) { melde('Kursübersicht (Moodle 5)', 'WARNUNG', fehler); return; }
    const tabelle = s.dok.querySelector('table.course-overview-table');
    const spalten = tabelle
        ? [...new Set([...tabelle.querySelectorAll('[data-mdl-overview-item]')]
            .map(e => e.getAttribute('data-mdl-overview-item')))].join(', ')
        : '';
    melde('Kursübersicht (Moodle 5)', tabelle ? 'OK' : 'WARNUNG',
          tabelle ? `Lehrkräfte-Spalten: ${spalten}` : 'keine Übersichtstabelle (nur Information)');
}

// --- Ablauf -------------------------------------------------------------

async function starte(kursId) {
    ergebnisse.length = 0;
    document.getElementById('zeilen').innerHTML = '';
    document.getElementById('ergebnis').hidden = false;
    const fazit = document.getElementById('fazit');
    fazit.className = 'fazit';
    fazit.textContent = 'Test läuft …';

    const schritte = [
        async () => pruefeUmgebung(),
        async () => {
            const gruppen = await pruefeFortschritt(kursId);
            if (gruppen.length) await pruefeGruppen(kursId, gruppen);
        },
        async () => {
            const cmids = await pruefeBewerteruebersicht(kursId);
            await pruefeBewertungsseite(cmids.assign);
            await pruefeTestbericht(cmids.quiz);
        },
        async () => pruefeNotenkategorien(kursId),
        async () => pruefeKursuebersicht(kursId),
    ];

    for (const schritt of schritte) {
        try {
            const weiter = await schritt();
            if (weiter === false) break;
        } catch (e) {
            const grund = e.name === 'TimeoutError' ? `Zeitüberschreitung nach ${TIMEOUT_MS / 1000} s` : e.message;
            melde('Abruf', 'FEHLER', grund);
        }
    }

    const fehler = ergebnisse.filter(e => e.stufe === 'FEHLER').length;
    const warnungen = ergebnisse.filter(e => e.stufe === 'WARNUNG').length;
    fazit.className = 'fazit ' + (fehler ? 'fehler' : 'ok');
    fazit.textContent = fehler
        ? `${fehler} Prüfung(en) fehlgeschlagen — der Browser-Export wäre so nicht möglich.`
        : `Alle nötigen Seiten sind lesbar${warnungen ? ` (${warnungen} Hinweis(e) zu aufgeteilten Seiten)` : ''} — der Browser-Export ist machbar.`;

    const text = [
        `ByCS-Machbarkeitstest ${new Date().toISOString()}`,
        `Herkunft: ${location.origin}`,
        `Browser: ${navigator.userAgent}`,
        ...ergebnisse.map(e => `[${e.stufe}] ${e.pruefung}: ${e.details}`),
        `Fazit: ${fazit.textContent}`
    ].join('\n');
    const roh = document.getElementById('rohtext');
    roh.value = text;
}

document.getElementById('formular').addEventListener('submit', async (ereignis) => {
    ereignis.preventDefault();
    const knopf = document.getElementById('start');
    knopf.disabled = true;
    try {
        await starte(document.getElementById('kursId').value.trim());
    } finally {
        knopf.disabled = false;
    }
});

document.getElementById('kopieren').addEventListener('click', async () => {
    const roh = document.getElementById('rohtext');
    try {
        await navigator.clipboard.writeText(roh.value);
        document.getElementById('kopieren').textContent = 'Kopiert';
    } catch (e) {
        // Zwischenablage gesperrt: Text zum manuellen Kopieren zeigen
        roh.hidden = false;
        roh.select();
    }
});

// Kurs-ID vorbelegen, wenn die Seite direkt von der Kursseite geoeffnet
// wurde. Nur dort ist "id" die Kurs-ID — auf mod/resource/view.php waere
// es die ID dieser Datei.
try {
    const herkunft = new URL(document.referrer);
    const id = herkunft.searchParams.get('id');
    if (herkunft.origin === BASIS && herkunft.pathname === '/course/view.php'
            && id && /^\d+$/.test(id)) {
        document.getElementById('kursId').value = id;
    }
} catch (e) { /* kein Referrer */ }
