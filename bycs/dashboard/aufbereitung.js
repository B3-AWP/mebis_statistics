// ============================================================
// aufbereitung.js — Aufbereitung des Exports fuer das Dashboard
//
// JS-Gegenstueck zu src/dashboard/backend.py (_process_dashboard_data
// und alles, was daran haengt). In ByCS gibt es keinen Flask-Server;
// diese Datei erzeugt im Browser genau die Antwort, die /api/data
// liefern wuerde. dashboard.js bleibt unveraendert.
//
// Bewusst eine Eins-zu-eins-Uebertragung — auch dort, wo das Python-
// Original Eigenheiten hat (strukturierte Tabellen ohne Personenstatus,
// IHK-Umrechnung ohne Komma-Punkte). Abweichungen wuerden das ByCS-
// und das lokale Dashboard verschiedene Zahlen zeigen lassen.
// Abgesichert durch tests/vergleiche_aufbereitung.py (Python gegen JS).
//
// Kein DOM: laeuft im Browser und in Node.
// ============================================================

(function (global) {
'use strict';

const EXPORT_SCHEMA_VERSION = 3;
const OHNE_NOTE = ['-', 'Nicht bewertet', 'Keine Bewertung'];

// --- Python-Nachbildungen ------------------------------------------------

// Liegt x * 10^n exakt auf ...,5? Geprueft am exakten Binaerwert von x
// (Mantisse * 2^Exponent), nicht am gerundeten Produkt.
function exakterGleichstand(x, n) {
    if (!Number.isFinite(x) || x === 0) return false;
    const dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, Math.abs(x));
    const bits = dv.getBigUint64(0);
    const exp = Number((bits >> 52n) & 0x7ffn);
    let mantisse = bits & ((1n << 52n) - 1n);
    let e;
    if (exp === 0) { e = -1074; } else { mantisse |= 1n << 52n; e = exp - 1075; }
    // 2 * x * 10^n = mantisse * 10^n * 2^(e+1) muss eine ungerade ganze Zahl sein
    const zaehler = mantisse * 10n ** BigInt(n);
    const p = e + 1;
    if (p > 0) return false;
    const teiler = 1n << BigInt(-p);
    return zaehler % teiler === 0n && (zaehler / teiler) % 2n === 1n;
}

// round(x, n) wie in Python: korrekt gerundet auf dem exakten Binaerwert,
// echte Gleichstaende zur geraden Ziffer (round(2.25, 1) == 2.2,
// round(66.585, 2) == 66.59, weil 66.585 binaer knapp darueber liegt).
function pyRound(x, n = 0) {
    if (exakterGleichstand(x, n)) {
        const f = 10 ** n;
        const k = Math.floor(Math.abs(x) * f);
        return Math.sign(x) * (k % 2 === 0 ? k : k + 1) / f;
    }
    return Number(x.toFixed(n));
}

// sum() wie in Python ab 3.12: Neumaier-Summation mit Fehlerausgleich.
// Einfaches Aufaddieren weicht in der letzten Binaerstelle ab — und das
// kippt eine Rundung (gesehen: Klassenschnitt 66,59 gegen 66,58).
function pySum(werte) {
    let summe = 0, ausgleich = 0;
    for (const x of werte) {
        const t = summe + x;
        if (Math.abs(summe) >= Math.abs(x)) ausgleich += (summe - t) + x;
        else ausgleich += (x - t) + summe;
        summe = t;
    }
    return ausgleich && Number.isFinite(ausgleich) ? summe + ausgleich : summe;
}

// float(s) wie in Python: streng, nicht wie parseFloat
function pyFloat(s) {
    const t = String(s).trim().replace(/_/g, '');
    if (!/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(t)) return null;
    return Number(t);
}

// str(float) wie in Python: 2.0 -> "2.0"
function pyFloatStr(x) {
    return Number.isInteger(x) ? x.toFixed(1) : String(x);
}

// f"{x:g}" fuer Stundenangaben
function formatG(x) {
    return String(Number(Number(x).toPrecision(6)));
}

// dict.get(k, standard) wie in Python: der Standard greift nur, wenn der
// Schluessel fehlt — ein vorhandenes null bleibt null.
function hol(obj, k, standard) {
    return obj && Object.prototype.hasOwnProperty.call(obj, k) ? obj[k] : standard;
}

// Klassenkuerzel wie group_utils.extract_group_prefix
function extractGroupPrefix(name) {
    if (!name) return '';
    const m = name.match(/\b([A-Z]{2,4}\d{2}[A-Z])\b/);
    if (m) return m[1];
    if (name.includes(' - ')) return name.split(' - ')[0].trim();
    return name.trim();
}

// --- Datum ---------------------------------------------------------------

const tagNr = iso => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 : null;
};
const heuteIso = () => {
    const d = new Date(), z = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
};
const wochentag = nr => (new Date(nr * 86400000).getUTCDay() + 6) % 7;  // 0 = Montag

// plan_loader.aktuelle_woche
function aktuelleWoche(schulwochen, heute = heuteIso()) {
    let aktuell = 0;
    for (const w of schulwochen) {
        if (w.start && w.start <= heute) aktuell = w.woche;
        else break;
    }
    return aktuell;
}

// --- Plan-Zugriffe (Plan in der Form von Plan.to_dict()) -----------------

function trackFuerKlasse(plan, klasse) {
    if (!klasse) return null;
    const kzs = plan.klassen_zu_schiene || {};
    if (klasse in kzs) return kzs[klasse];
    return kzs[extractGroupPrefix(klasse)] || null;
}

// --- Titel (backend.titel_mit_planstunden) ------------------------------

const ZEITANGABE = String.raw`(?:ca\.?|~|etwa)?\s*[\d.,]+(?:\s*[-–]\s*[\d.,]+)?\s*(?:min|minuten|std|stunden|h)\s*\.?`;
const ZEIT_IM_TITEL = new RegExp(String.raw`\s*\(\s*` + ZEITANGABE + String.raw`\s*\)\s*$`, 'i');
const ZEIT_IN_KLAMMER = new RegExp(String.raw`(?<=\()([^()]*?)[,;]?\s*` + ZEITANGABE + String.raw`\s*(?=\)\s*$)`, 'i');

function titelMitPlanstunden(titel, cmid, planStunden) {
    if (!titel) return titel;
    const stunden = planStunden[String(cmid).trim()];
    if (stunden === undefined || stunden === null) return titel;
    let ohneZeit = titel.replace(ZEIT_IM_TITEL, '').trimEnd();
    if (ohneZeit === titel) {
        ohneZeit = titel.replace(ZEIT_IN_KLAMMER, '$1').split('()').join('').trimEnd();
    }
    return `${ohneZeit} (${formatG(stunden).replace('.', ',')} Std.)`;
}

function titelAufPlanstundenUmstellen(kategorien, planStunden) {
    if (!planStunden || !Object.keys(planStunden).length) return;
    for (const kat of kategorien || []) {
        for (const art of ['assignments', 'quizzes', 'checklists', 'feedbacks']) {
            for (const akt of kat[art] || []) {
                if ('title' in akt) akt.title = titelMitPlanstunden(akt.title, akt.id, planStunden);
            }
        }
    }
}

function getAssignmentDetails(kategorien) {
    const details = {};
    for (const kat of kategorien) {
        const name = kat.category_name ?? 'Unknown';
        for (const [art, typ] of [['assignments', 'assignment'], ['quizzes', 'quiz'],
                                  ['checklists', 'checklist'], ['feedbacks', 'feedback']]) {
            for (const a of kat[art] || []) {
                details[a.id] = { title: a.title, url: a.url, category_name: name, type: typ };
            }
        }
    }
    return details;
}

// --- Noten (backend.convert_grade_to_ihk u.a.) ---------------------------

const STERNE = { '**** Exzellent': 1.0, '*** Solide Umsetzung': 2.5,
                 '** Verbesserungsbedarf': 4.0, '* Nicht akzeptabel': 5.5 };

function pointsToIhkGrade(p) {
    if (p >= 92) return 1.0;
    if (p >= 81) return 2.0;
    if (p >= 67) return 3.0;
    if (p >= 50) return 4.0;
    if (p >= 30) return 5.0;
    return 6.0;
}

function convertGradeToIhk(note) {
    if (!note || OHNE_NOTE.includes(note)) return null;
    const g = String(note).trim();
    if (g in STERNE) return STERNE[g];
    if (g.includes('%')) {
        const p = pyFloat(g.replace(/%/g, '').replace(/ /g, ''));
        if (p !== null) return pointsToIhkGrade(p);
    }
    if (g.includes('/')) {
        const teile = g.split('/');
        const punkte = pyFloat(teile[0].trim()), max = pyFloat((teile[1] ?? '').trim());
        if (punkte !== null && max !== null && max !== 0) return pointsToIhkGrade(punkte / max * 100);
    }
    const zahl = pyFloat(g.replace(/,/g, '.'));
    if (zahl !== null && zahl >= 1 && zahl <= 6) return zahl;
    return null;
}

function calculateIhkGradeAverage(noten) {
    if (!noten || !noten.length) return null;
    const gueltig = noten.map(convertGradeToIhk).filter(n => n !== null);
    if (!gueltig.length) return null;
    return pyRound(pySum(gueltig) / gueltig.length, 1);
}

function roundGrade(note) {
    if (!note || OHNE_NOTE.includes(note)) return note;
    const m = /(\d+[.,]\d+|\d+)/.exec(note);
    if (m) return String(Math.floor(Number(m[1].replace(',', '.')) + 0.5));
    return note;
}

// --- Status-Suche --------------------------------------------------------

function findUserChecklistProgress(user, id) {
    for (const c of ((user.checklists || {}).individual_checklists || [])) {
        if (c.id === id) return { required_progress: c.required_progress, all_progress: c.all_progress, url: c.url };
    }
    return { required_progress: '0%', all_progress: '0%', url: '#' };
}

function findUserAssignmentStatus(user, id) {
    const acts = user.activities || {};
    for (const typ of ['assignments', 'quizzes']) {
        for (const a of acts[typ] || []) {
            if (a.id !== id) continue;
            const s = a.status || {};
            const r = {
                status: hol(s, 'status', 'Nicht eingereicht'),
                status2: hol(s, 'status2', ''),
                grade: roundGrade(hol(s, 'grade', '-')),
                submission_time: hol(s, 'submission_time', null)
            };
            if (s.unbekannt) { r.unbekannt = true; r.grund = s.grund ?? ''; }
            return r;
        }
    }
    return { status: 'Nicht eingereicht', status2: '', grade: '-', submission_time: null };
}

// --- Fortschritt je Person (backend.calculate_user_progress) -------------

function leereChecklisten() {
    return { required_100_count: 0, avg_required_progress: 0, avg_all_progress: 0,
             avg_required_progress_timed: 0, avg_all_progress_timed: 0, individual_checklists: [] };
}

function createFallbackUser(user, gruppe) {
    return {
        name: user.name ?? 'Unknown', group: gruppe,
        assignments: { reviewed_count: 0, submitted_count: 0, grades: {}, percent_submitted: 0,
                       percent_submitted_timed: 0, average_grade: null },
        checklists: leereChecklisten()
    };
}

function calculateUserProgress(user, details, kategorien, currentWeek, totalWeeks, plan, kurs) {
    const daten = {
        name: user.name, group: user.group ?? 'Unbekannt',
        assignments: { reviewed_count: 0, submitted_count: 0, grades: {}, percent_submitted: 0,
                       percent_submitted_timed: 0, average_grade: null },
        checklists: leereChecklisten()
    };
    const acts = user.activities;
    const geplante = kurs ? kurs.aufgaben : plan.kurse.flatMap(k => k.aufgaben);
    const planCmids = new Set(geplante.map(a => a.cmid));
    const pflicht = a => planCmids.has(String(a.id ?? '').trim());
    const alle = [...(acts.assignments || []).filter(pflicht), ...(acts.quizzes || []).filter(pflicht),
                  ...(acts.checklists || []).filter(pflicht), ...(acts.feedbacks || []).filter(pflicht)];
    const gesamt = planCmids.size;

    const bewertet = alle.filter(a => (a.status || {}).status2 === 'Bewertet');
    const abgegeben = alle.filter(a => (a.status || {}).status === 'Zur Bewertung abgegeben');
    daten.assignments.reviewed_count = bewertet.length;
    daten.assignments.submitted_count = abgegeben.length;
    daten.assignments.grades = { Pflichtaufgaben: [] };

    const noten = [];
    for (const a of abgegeben) {
        const d = details[a.id] || {};
        const roh = hol(a.status || {}, 'grade', 'Nicht bewertet');
        daten.assignments.grades.Pflichtaufgaben.push({
            title: d.title ?? 'N/A', grade: roundGrade(roh), url: d.url ?? '#', type: d.type ?? 'unknown'
        });
        const ihk = convertGradeToIhk(roh);
        if (ihk !== null) noten.push(ihk);
    }
    if (noten.length) daten.assignments.average_grade = calculateIhkGradeAverage(noten);

    daten.assignments.percent_submitted = gesamt > 0 ? pyRound(abgegeben.length / gesamt * 100, 2) : 0;
    const erwartet = Math.ceil((gesamt / totalWeeks) * currentWeek);
    daten.assignments.percent_submitted_timed = erwartet > 0 ? pyRound(abgegeben.length / erwartet * 100, 2) : 0;

    // Stundengewichtete Quantitaet; unbekannt zaehlt nicht als erledigt
    const stundenGesamt = pySum(geplante.map(a => a.stunden));
    const erledigt = new Set(), unbekannt = new Set();
    for (const a of alle) {
        const s = a.status || {};
        const id = String(a.id ?? '').trim();
        if (s.unbekannt) { unbekannt.add(id); continue; }
        const mitNote = ![null, undefined, '', '-', 'Nicht bewertet', 'Nicht eingereicht', 'Keine Bewertung'].includes(s.grade);
        // Entwurf: hat ein Datum, ist aber nicht eingereicht (wie pruefung.zaehlt_als_abgabe)
        const abgabe = Boolean(s.submission_time) && s.status !== 'Entwurf (nicht abgegeben)';
        if (abgabe || mitNote || s.status2 === 'Bewertet') erledigt.add(id);
    }
    const stundenErledigt = pySum(geplante.filter(a => erledigt.has(a.cmid)).map(a => a.stunden));
    const offen = geplante.filter(a => unbekannt.has(a.cmid));
    Object.assign(daten.assignments, {
        stunden_gesamt: pyRound(stundenGesamt, 2),
        stunden_erledigt: pyRound(stundenErledigt, 2),
        percent_stunden: stundenGesamt > 0 ? pyRound(stundenErledigt / stundenGesamt * 100, 2) : 0,
        aufgaben_erledigt: erledigt.size,
        aufgaben_gesamt: geplante.length,
        stunden_unbekannt: pyRound(pySum(offen.map(a => a.stunden)), 2),
        aufgaben_unbekannt: offen.length,
        unbekannte_aufgaben: offen.map(a => a.titel)
    });

    // Checklisten (Export derzeit abgeschaltet, Pfad bleibt wie im Backend)
    const checklisten = acts.checklists || [];
    const pflichtCl = checklisten.filter(c => c.is_mandatory ?? true);
    daten.checklists.required_100_count = pflichtCl.filter(c => c.progress.required_progress === '100%').length;
    for (const c of checklisten) {
        daten.checklists.individual_checklists.push({
            id: c.id, title: c.title ?? 'Unbekannt', url: c.url ?? '#',
            required_progress: c.progress.required_progress, all_progress: c.progress.all_progress,
            is_mandatory: c.is_mandatory ?? true
        });
    }
    if (pflichtCl.length) {
        const summe = feld => pySum(pflichtCl.filter(c => c.progress[feld])
            .map(c => Number(String(c.progress[feld]).replace(/%/g, ''))));
        daten.checklists.avg_required_progress = pyRound(summe('required_progress') / pflichtCl.length, 2);
        daten.checklists.avg_all_progress = pyRound(summe('all_progress') / pflichtCl.length, 2);
    }
    if (currentWeek > 0) {
        daten.checklists.avg_required_progress_timed = pyRound(daten.checklists.avg_required_progress / currentWeek * totalWeeks, 2);
        daten.checklists.avg_all_progress_timed = pyRound(daten.checklists.avg_all_progress / currentWeek * totalWeeks, 2);
    }
    return daten;
}

function calculateGroupAverages(users) {
    if (!users.length) {
        return {
            assignments: { avg_percent_submitted: 0, avg_percent_submitted_timed: 0, avg_grade: null },
            checklists: { total_required_100: 0, avg_required_progress: 0, avg_all_progress: 0,
                          avg_required_progress_timed: 0, avg_all_progress_timed: 0 }
        };
    }
    const n = users.length;
    const summe = f => pySum(users.map(f));
    const g = {
        assignments: {
            avg_percent_submitted: pyRound(summe(u => u.assignments.percent_submitted) / n, 2),
            avg_percent_submitted_timed: pyRound(summe(u => u.assignments.percent_submitted_timed) / n, 2),
            avg_grade: null
        },
        checklists: {
            total_required_100: summe(u => u.checklists.required_100_count),
            avg_required_progress: pyRound(summe(u => u.checklists.avg_required_progress) / n, 2),
            avg_all_progress: pyRound(summe(u => u.checklists.avg_all_progress) / n, 2),
            avg_required_progress_timed: 0, avg_all_progress_timed: 0
        }
    };
    const noten = users.map(u => u.assignments.average_grade).filter(x => x !== null && x !== undefined);
    if (noten.length) g.assignments.avg_grade = calculateIhkGradeAverage(noten);
    g.checklists.avg_required_progress_timed = g.checklists.avg_required_progress;
    g.checklists.avg_all_progress_timed = g.checklists.avg_all_progress;
    return g;
}

// --- Letzte Abgaben (backend.build_recent_submissions) -------------------

function countSchoolDaysSince(abgabe, wochen, heuteNr) {
    if (!abgabe) return null;
    const ab = tagNr(abgabe.slice(0, 10));
    if (ab === null) return null;
    let tage = 0;
    for (const w of wochen) {
        const start = tagNr(w.start), ende = tagNr(w.end);
        if (start === null || ende === null) continue;
        if (ende <= ab) continue;
        if (start > heuteNr) break;
        const von = Math.max(start, ab + 1), bis = Math.min(ende, heuteNr);
        for (let t = von; t <= bis; t++) if (wochentag(t) < 5) tage++;
    }
    return tage;
}

function buildRecentSubmissions(groupsData, rawGroups, maCfg, recentDays, details, refIso, kategorien, schwelle) {
    const classToTrack = (maCfg || {}).class_to_track || {};
    const schedules = (maCfg || {}).track_schedules || {};
    const refNr = tagNr(refIso);
    const rohNachName = {};
    for (const g of rawGroups) {
        if (!g.name) continue;
        rohNachName[g.name] = g;
        const k = extractGroupPrefix(g.name);
        if (!(k in rohNachName)) rohNachName[k] = g;
    }
    let pflichtKat = null;
    for (const k of kategorien || []) {
        if ((k.category_name || '').includes('Pflichtaufgaben')) { pflichtKat = k.id; break; }
    }
    const schultage = (zeit, wochen) => wochen.length ? countSchoolDaysSince(zeit, wochen, refNr) : null;
    const kalendertage = zeit => { const t = tagNr((zeit || '').slice(0, 10)); return t === null ? null : refNr - t; };
    const titelFuer = (id, akt) => (details[String(id)] || {}).title || akt.title || '?';

    const ergebnis = {};
    for (const name of Object.keys(groupsData)) {
        const track = classToTrack[name] || classToTrack[name.split(' ')[0]];
        const wochen = track ? (schedules[track] || []) : [];
        const roh = rohNachName[name] || {};
        const gueltig = new Set((groupsData[name].users || []).map(u => u.name));
        let abgaben = [];
        for (const u of roh.users || []) {
            if (gueltig.size && !gueltig.has(u.name)) continue;
            const acts = u.activities || {};
            for (const [art, typ] of [['assignments', 'assignment'], ['quizzes', 'quiz']]) {
                for (const a of acts[art] || []) {
                    const s = a.status || {};
                    const zeit = s.submission_time, st = hol(s, 'status', 'Nicht eingereicht');
                    if (!zeit || st === 'Nicht eingereicht') continue;
                    const id = a.id ?? '';
                    const d = details[String(id)] || {};
                    abgaben.push({
                        time: zeit, title: titelFuer(id, a), _key: id ? String(id) : null, _status: st,
                        is_pflicht: pflichtKat !== null && a.category_id === pflichtKat,
                        _grade: typ === 'assignment' ? (s.grade || s.rating || s.score || '-') : hol(s, 'grade', '-'),
                        category_name: d.category_name ?? '', url: d.url ?? null, activity_type: typ
                    });
                }
            }
        }
        abgaben.sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0));

        const noten = {}, stati = {}, erste = {}, reihenfolge = [];
        for (const s of abgaben) {
            const key = s._key || s.title;
            if (!(key in erste)) { erste[key] = s; reihenfolge.push(key); noten[key] = []; stati[key] = []; }
            const g = s._grade ?? '-';
            if (g && !['-', 'Nicht bewertet', 'Keine Bewertung', 'Nicht benotet'].includes(g)) noten[key].push(g);
            if (s._status) stati[key].push(s._status);
        }
        abgaben = reihenfolge.map(key => {
            const s = erste[key], gs = noten[key];
            let anzeige = null;
            if (gs.length && new Set(gs).size === 1) anzeige = gs[0];
            else if (gs.length) {
                const num = gs.map(convertGradeToIhk).filter(x => x !== null);
                anzeige = num.length ? `∅ ${pyFloatStr(pyRound(pySum(num) / num.length, 1))}` : gs[0];
            }
            const e = {};
            Object.keys(s).forEach(k => { if (!k.startsWith('_')) e[k] = s[k]; });
            e.grade_display = anzeige;
            e.is_bewertbar = stati[key].includes('Zur Bewertung abgegeben');
            return e;
        });

        const keine = !abgaben.length;
        const letzte = abgaben[0] || null;
        const seitSchul = letzte ? schultage(letzte.time, wochen) : null;
        const seitKal = letzte ? kalendertage(letzte.time) : null;
        const juengst = [];
        for (const s of abgaben) {
            const kd = kalendertage(s.time);
            if (kd !== null && kd <= recentDays) {
                juengst.push({ ...s, school_days_ago: schultage(s.time, wochen), calendar_days_ago: kd });
            } else break;
        }
        ergebnis[name] = {
            recent_submissions: juengst,
            group_id: roh.value ?? null,
            last_submission_time: letzte ? letzte.time : null,
            last_submission_title: letzte ? letzte.title : null,
            last_submission_grade: letzte ? letzte.grade_display : null,
            last_submission_category: letzte ? letzte.category_name : null,
            last_submission_url: letzte ? letzte.url : null,
            last_submission_type: letzte ? letzte.activity_type : null,
            last_submission_bewertbar: letzte ? (letzte.is_bewertbar ?? false) : false,
            last_submission_is_pflicht: letzte ? (letzte.is_pflicht ?? false) : false,
            school_days_since: seitSchul,
            calendar_days_since: seitKal,
            inactive: keine || seitSchul === null || seitSchul > schwelle,
            no_submissions: keine
        };
    }
    return ergebnis;
}

// --- Strukturierte Tabellen (backend.create_structured_tables) ----------

function createStructuredTables(groupsData, kategorien) {
    const checklisten = [], pflicht = [], zentrale = [];
    const nachTitel = (a, b) => (a.title < b.title ? -1 : a.title > b.title ? 1 : 0);
    for (const k of kategorien) {
        for (const c of k.checklists || []) {
            checklisten.push({ id: c.id, title: c.title, url: c.url ?? '#', category_name: k.category_name,
                               is_mandatory: c.is_mandatory ?? false });
        }
        if (k.category_name === '🎯Pflichtaufgaben') {
            (k.assignments || []).forEach(a => pflicht.push({ id: a.id, title: a.title, url: a.url ?? '#', type: 'assignment' }));
            (k.quizzes || []).forEach(q => pflicht.push({ id: q.id, title: q.title, url: q.url ?? '#', type: 'quiz' }));
        }
        if (k.category_name && (k.category_name.includes('Zentrale Leistungsnachweise')
                                || k.category_name.toLowerCase().includes('chart'))) {
            (k.assignments || []).forEach(a => zentrale.push({ id: a.id, title: a.title, url: a.url ?? '#', type: 'assignment' }));
            (k.quizzes || []).forEach(q => zentrale.push({ id: q.id, title: q.title, url: q.url ?? '#', type: 'quiz' }));
        }
    }
    pflicht.sort(nachTitel);
    zentrale.sort(nachTitel);

    // Wie im Backend: die verdichteten Personen haben keine activities —
    // der Status hier ist daher immer der Standardwert.
    const tabelle = (zeilen, users, kopf) => ({
        headers: [kopf, ...users.map(u => u.name)],
        rows: zeilen.map(a => ({
            assignment_id: a.id, assignment_title: a.title, assignment_url: a.url, assignment_type: a.type,
            user_status: users.map(u => ({ ...findUserAssignmentStatus(u, a.id), user_name: u.name ?? 'Unknown' }))
        }))
    });
    const erg = {};
    for (const [name, g] of Object.entries(groupsData)) {
        const users = g.users;
        erg[name] = {
            checklists: {
                headers: ['Checkliste', ...users.map(u => u.name)],
                rows: checklisten.map(c => ({
                    checklist_id: c.id, checklist_title: c.title, checklist_url: c.url,
                    checklist_category: c.category_name, is_mandatory: c.is_mandatory ?? false,
                    user_progress: users.map(u => findUserChecklistProgress(u, c.id))
                }))
            },
            pflichtaufgaben: tabelle(pflicht, users, 'Aufgabe'),
            zentrale_leistungsnachweise: tabelle(zentrale, users, 'Aufgabe')
        };
    }
    return erg;
}

// --- Kurs und Gesamt (backend._process_course_data / _process_dashboard_data)

function processCourseData(data, plan, kurs, einst, quelle) {
    const ausgeschlossen = new Set(einst.excluded_names || []);
    const ignoriert = new Set(einst.ignored_groups || []);

    const planStunden = {};
    kurs.aufgaben.forEach(a => { planStunden[String(a.cmid).trim()] = a.stunden; });
    titelAufPlanstundenUmstellen(data.activities_by_category || [], planStunden);
    const details = getAssignmentDetails(data.activities_by_category || []);

    const ersteSchiene = Object.keys(plan.schienen || {})[0];
    const schulwochen = ersteSchiene ? plan.schienen[ersteSchiene].schulwochen : [];
    const totalWeeks = schulwochen.length || 1;
    const currentWeek = schulwochen.length ? aktuelleWoche(schulwochen) : 0;

    const groupsData = {};
    for (const g of data.groups || []) {
        const roh = g.name ?? 'Unknown';
        if (ignoriert.has(roh) || !trackFuerKlasse(plan, roh)) continue;
        const name = extractGroupPrefix(roh);
        if (ignoriert.has(name)) continue;
        const users = (g.users || []).filter(u => !ausgeschlossen.has(u.name ?? ''));
        if (!users.length) continue;
        groupsData[name] = { name, value: g.value, users: [] };
        for (const u of users) {
            try {
                u.group = name;
                groupsData[name].users.push(calculateUserProgress(u, details, data.activities_by_category || [],
                                                                  currentWeek, totalWeeks, plan, kurs));
            } catch (e) {
                groupsData[name].users.push(createFallbackUser(u, name));
            }
        }
    }
    for (const g of Object.values(groupsData)) Object.assign(g, calculateGroupAverages(g.users));
    const overall = calculateGroupAverages(Object.values(groupsData).flatMap(g => g.users));
    const structured = createStructuredTables(groupsData, data.activities_by_category || []);

    let pflichtKat = null;
    const andere = [];
    for (const k of data.activities_by_category || []) {
        if ((k.category_name || '').includes('Pflichtaufgaben')) pflichtKat = k;
        else andere.push(k);
    }
    const geordnet = pflichtKat ? [pflichtKat, ...andere] : (data.activities_by_category || []);

    const eintrag = (u, s) => {
        const e = { user_name: u.name ?? '', user_id: u.id ?? '', status: s.status ?? 'Nicht eingereicht',
                    grade: s.grade ?? '-', submission_time: s.submission_time ?? null };
        if (s.unbekannt) { e.unbekannt = true; e.grund = s.grund ?? ''; }
        return e;
    };
    for (const k of geordnet) {
        for (const art of ['assignments', 'quizzes']) {
            for (const a of k[art] || []) {
                a.user_status = [];
                for (const g of data.groups || []) {
                    if (ignoriert.has(g.name ?? '')) continue;
                    for (const u of g.users || []) {
                        if (ausgeschlossen.has(u.name)) continue;
                        a.user_status.push(eintrag(u, findUserAssignmentStatus(u, a.id)));
                    }
                }
            }
        }
    }

    // Bezugsdatum: Datum aus dem Dateinamen des Exports, sonst heute
    const m = /(\d{8})_\d{6}/.exec(String(quelle || '').replace(/.*[\\/]/, ''));
    let exportDatum = heuteIso();
    if (m) {
        const iso = `${m[1].slice(0, 4)}-${m[1].slice(4, 6)}-${m[1].slice(6, 8)}`;
        if (tagNr(iso) !== null) exportDatum = iso;
    }

    const maCfg = { ...(einst.mitarbeitsnote_config || {}) };
    maCfg.class_to_track = { ...(plan.klassen_zu_schiene || {}) };
    maCfg.track_schedules = {};
    for (const [name, s] of Object.entries(plan.schienen || {})) {
        maCfg.track_schedules[name] = s.schulwochen.map(w => ({ week: w.woche, start: w.start, end: w.ende }));
    }

    return {
        verfuegbar: true,
        course_id: kurs.moodle_course_id,
        groups: groupsData,
        overall_stats: overall,
        assignment_details: details,
        categories: geordnet,
        activities_by_category: geordnet,
        structured_tables: structured,
        grade_mapping: einst.grade_mapping || {},
        mitarbeitsnote_config: maCfg,
        recent_submissions: buildRecentSubmissions(groupsData, data.groups || [], maCfg,
            einst.recent_submission_days, details, exportDatum, geordnet, einst.inactive_threshold_days),
        stunden_geplant: kurs.stunden_geplant,
        pruefbericht: data.pruefbericht || {}
    };
}

// Flask sortiert die Schluessel der JSON-Antwort (sort_keys) — das
// bestimmt u.a. die Reihenfolge der Klassen im Dashboard.
function sortiereSchluessel(wert) {
    if (Array.isArray(wert)) return wert.map(sortiereSchluessel);
    if (wert && typeof wert === 'object') {
        const erg = {};
        Object.keys(wert).sort().forEach(k => { erg[k] = sortiereSchluessel(wert[k]); });
        return erg;
    }
    return wert;
}

/**
 * Erzeugt aus einem Export (Schema 3) die Antwort von /api/data.
 *
 * @param {Object} exportDaten - Export-JSON (wird nicht veraendert)
 * @param {Object} plan - Plan in der Form von Plan.to_dict() (plan_dashboard.json)
 * @param {Object} einst - Einstellungen (einstellungen.json)
 * @param {string} quelle - Dateiname des Exports (fuer Datum und Anzeige)
 */
function aufbereiten(exportDaten, plan, einst, quelle) {
    if (!exportDaten || exportDaten.schema !== EXPORT_SCHEMA_VERSION) {
        throw new Error(`Export hat Schema ${JSON.stringify(exportDaten && exportDaten.schema)}, `
                      + `erwartet wird ${EXPORT_SCHEMA_VERSION} — bitte einen neuen Export erzeugen.`);
    }
    const data = JSON.parse(JSON.stringify(exportDaten));
    const rohGruppen = data.groups || [];
    const kurse = {};
    for (const [cid, kursDaten] of Object.entries(data.kurse || {})) {
        const kurs = plan.kurse.find(k => k.moodle_course_id === String(cid));
        if (!kurs) continue;
        const r = processCourseData({ ...kursDaten, groups: rohGruppen }, plan, kurs, einst, quelle);
        r.titel = kurs.titel;
        r.kurs_id = kurs.id;
        r.gesperrt = kurs.gesperrt;
        kurse[String(cid)] = r;
    }
    for (const kurs of plan.kurse) {
        if (kurs.moodle_course_id in kurse) continue;
        kurse[kurs.moodle_course_id] = {
            titel: kurs.titel, kurs_id: kurs.id, gesperrt: kurs.gesperrt, freischaltung: kurs.freischaltung,
            verfuegbar: false, groups: {}, overall_stats: {}, activities_by_category: [], categories: [],
            structured_tables: {}, assignment_details: {}, recent_submissions: []
        };
    }
    return sortiereSchluessel({
        schema: EXPORT_SCHEMA_VERSION,
        exported_at: data.exported_at ?? null,
        schuljahr: data.schuljahr || plan.schuljahr,
        plan,
        kurse,
        pruefbericht: data.pruefbericht || {},
        ignored_groups: [...(einst.ignored_groups || [])],
        last_updated: quelle ?? null,
        environment: einst.environment || {},
        recent_submission_days: einst.recent_submission_days
    });
}

const api = { aufbereiten, pyRound, convertGradeToIhk, roundGrade, titelMitPlanstunden, countSchoolDaysSince };
global.MebisAufbereitung = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
