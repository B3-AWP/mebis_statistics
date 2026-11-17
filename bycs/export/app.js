// ============================================================
// app.js — Ablauf der Exportseite: Plan laden, Kurse waehlen,
// Export starten, Pruefbericht zeigen, Datei anbieten.
// ============================================================

'use strict';

let plan = null;
let ergebnis = null;

const $ = id => document.getElementById(id);

function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Minimalpruefung: genau das, was der Export braucht. Die volle
// Validierung macht das Dashboard beim Laden.
function pruefePlan(roh) {
    const fehler = [];
    if (!roh || !Array.isArray(roh.kurse)) fehler.push('„kurse" fehlt');
    if (!roh || typeof roh.klassenZuSchiene !== 'object') fehler.push('„klassenZuSchiene" fehlt');
    (roh && roh.kurse || []).forEach((k, i) => {
        if (!/^\d+$/.test(String(k.moodleCourseId || ''))) fehler.push(`kurse[${i}].moodleCourseId fehlt`);
        if (!Array.isArray(k.aufgaben)) fehler.push(`kurse[${i}].aufgaben fehlt`);
    });
    if (fehler.length) throw new Error(fehler.join('; '));
    return roh;
}

function zeigePlan(roh, quelle) {
    plan = pruefePlan(roh);
    $('planStatus').innerHTML = `Schuljahr <strong>${escapeHtml(plan.schuljahr)}</strong>, `
        + `Stand ${escapeHtml(plan.stand || '–')}, ${plan.kurse.length} Kurse — aus ${escapeHtml(quelle)}`;
    $('planWahl').hidden = true;

    $('kursListe').innerHTML = plan.kurse.map((k, i) => `
        <label class="kurs">
            <input type="checkbox" data-index="${i}" ${k.gesperrt ? '' : 'checked'}>
            ${escapeHtml(k.titel)} <span class="hinweis">(Kurs ${escapeHtml(k.moodleCourseId)},
            ${k.aufgaben.length} Pflichtaufgaben${k.gesperrt ? ', laut Plan gesperrt' : ''})</span>
        </label>`).join('');
    $('start').disabled = false;
}

async function ladePlan() {
    // plan.json liegt in derselben Datei-Aktivitaet wie diese Seite —
    // wie beim Schueler-Dashboard.
    try {
        const antwort = await fetch('plan.json', { cache: 'no-store' });
        if (!antwort.ok) throw new Error(`HTTP ${antwort.status}`);
        zeigePlan(await antwort.json(), 'plan.json neben dieser Seite');
    } catch (e) {
        $('planStatus').textContent = `plan.json neben dieser Seite nicht gefunden (${e.message}).`;
        $('planWahl').hidden = false;
    }
}

$('planDatei').addEventListener('change', async (ereignis) => {
    const datei = ereignis.target.files[0];
    if (!datei) return;
    try {
        zeigePlan(JSON.parse(await datei.text()), datei.name);
    } catch (e) {
        $('planStatus').textContent = `plan.json ungültig: ${e.message}`;
    }
});

function protokoll(text, nurFortschritt) {
    if (nurFortschritt) { $('fortschritt').textContent = text; return; }
    const li = document.createElement('li');
    li.textContent = `${new Date().toLocaleTimeString('de-DE')}  ${text}`;
    $('protokoll').appendChild(li);
}

function zeigePruefbericht(b, seiten) {
    const probleme = b.luecken.length + b.verlauf.length + b.fehlende_kurse.length;
    let html = `<p class="${probleme ? 'warnung' : 'ok'}"><strong>`
        + (probleme ? 'Export unvollständig' : 'Export geprüft: jeder Status ist bekannt')
        + `</strong> — ${seiten} Seiten gelesen, ${b.seiten_nachgeladen} Folgeseite(n) nachgeladen`
        + (b.vergleich_mit ? `, verglichen mit ${escapeHtml(b.vergleich_mit)}` : '') + '.</p>';
    const liste = (titel, eintraege) => eintraege.length
        ? `<h3>${titel}</h3><ul>${eintraege.map(e => `<li>${e}</li>`).join('')}</ul>` : '';
    html += liste('Lücken — betroffene Noten sind vorläufig', b.luecken.map(l =>
        `${escapeHtml(l.titel)} — ${l.personen === 'alle' ? 'alle' : l.personen.length + ' Person(en)'}: ${escapeHtml(l.grund)}`));
    html += liste('Rückgänge gegenüber dem letzten Lauf', b.verlauf.map(escapeHtml));
    html += liste('Fehlende Kurse', b.fehlende_kurse.map(escapeHtml));
    html += liste('Hinweise', b.hinweise.map(escapeHtml));
    $('pruefbericht').innerHTML = html;
}

$('start').addEventListener('click', async () => {
    const kurse = [...document.querySelectorAll('#kursListe input:checked')]
        .map(c => plan.kurse[Number(c.dataset.index)]);
    if (!kurse.length) return;

    $('start').disabled = true;
    $('laufBereich').hidden = false;
    $('ergebnisBereich').hidden = true;
    $('protokoll').innerHTML = '';
    const beginn = performance.now();
    try {
        ergebnis = await window.MebisExport.exportiere(plan, kurse, protokoll);
        const dauer = Math.round((performance.now() - beginn) / 1000);
        $('fortschritt').textContent = `Fertig nach ${dauer} s.`;
        zeigePruefbericht(ergebnis.data.pruefbericht, ergebnis.seiten);
        $('ergebnisBereich').hidden = false;
    } catch (e) {
        $('fortschritt').textContent = `Abgebrochen: ${e.message}`;
    } finally {
        $('start').disabled = false;
    }
});

$('herunterladen').addEventListener('click', () => {
    if (!ergebnis) return;
    const blob = new Blob([JSON.stringify(ergebnis.data)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = ergebnis.dateiname;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

ladePlan();
