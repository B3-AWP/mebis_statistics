/**
 * Laedt dashboard.js in eine minimale DOM-Attrappe und prueft die
 * Rechenpfade gegen echte API-Daten. Kein Browser noetig — es geht um
 * Laufzeitfehler und Zahlen, nicht um Layout.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const REPO = path.resolve(__dirname, '..');
const apiResponse = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

// --- DOM-Attrappe -------------------------------------------------
function makeEl(id) {
    const el = {
        id, value: '', textContent: '', innerHTML: '', style: {},
        classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
                     contains(c) { return this._s.has(c); } },
        children: [], appendChild(c) { this.children.push(c); },
        querySelector: () => null, querySelectorAll: () => [],
        setAttribute() {}, addEventListener() {},
        setProperty() {},
    };
    el.style.setProperty = () => {};
    return el;
}
const elements = {};
const document = {
    getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: (tag) => makeEl('created-' + tag),
    addEventListener() {},
};
const window = { addEventListener() {}, location: { href: '' } };
const consoleStub = { log() {}, warn() {}, error: console.error, debug() {}, info() {} };

const sandbox = {
    window, document, console: consoleStub,
    setTimeout: (fn) => { try { fn(); } catch (e) { /* Layout-Helfer */ } },
    fetch: () => Promise.reject(new Error('kein Netzwerk im Test')),
    Date, Math, JSON, Object, Array, String, Number, Boolean, isNaN, parseInt, parseFloat,
    Set, Map, Promise, RegExp, Error,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// Logger-Attrappe VOR dashboard.js in den Kontext legen
vm.runInContext(`var dashboardLogger = {
    info: function(){}, warn: function(){}, error: function(){}, debug: function(){},
    setBackendEnvironment: function(){}
};`, sandbox);

const dashSrc = fs.readFileSync(path.join(REPO, 'src/dashboard/static/dashboard.js'), 'utf8');
vm.runInContext(dashSrc, sandbox);
console.log('dashboard.js geladen — keine Syntax-/Initialisierungsfehler');

// let/const sind lexikalische Bindungen, keine Sandbox-Eigenschaften.
const G = (expr) => vm.runInContext(expr, sandbox);
const setG = (name, val) => { sandbox.__tmp = val; vm.runInContext(`${name} = __tmp;`, sandbox); };

// --- Test ---------------------------------------------------------
let fehler = 0;
function pruefe(name, bedingung, detail) {
    if (bedingung) { console.log(`  OK   ${name}${detail ? ' — ' + detail : ''}`); }
    else { console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); fehler++; }
}

console.log('\n== applyDashboardData ==');
G('applyDashboardData')(apiResponse);
pruefe('Plan geladen', G('plan') !== null);
pruefe('maxSchoolweeks aus Plan', G('maxSchoolweeks') === 9, `= ${G('maxSchoolweeks')}`);
pruefe('aktiver Kurs = 1. Halbjahr', G('currentHalbjahr') === 'halbjahr-1',
       `= ${G('currentHalbjahr')}`);
pruefe('gesperrter Kurs nicht aktiv', G('currentHalbjahr') !== 'halbjahr-2');

console.log('\n== getCourses ==');
const courses = G('getCourses')();
pruefe('zwei Kurse', courses.length === 2);
pruefe('HJ1 verfuegbar', courses[0].verfuegbar === true);
pruefe('HJ2 gesperrt', courses[1].verfuegbar === false && courses[1].gesperrt === true);

console.log('\n== sollAnteil (gegen js/bilanz.js) ==');
const wochen = G('plan').schienen.Schiene1.schulwochen;
const erwartet = { 0: 0.0, 1: 0.0820, 2: 0.1967, 5: 0.5410, 9: 1.0 };
for (const [w, soll] of Object.entries(erwartet)) {
    const ist = G('sollAnteil')(wochen, Number(w));
    pruefe(`sollAnteil(${w})`, Math.abs(ist - soll) < 0.001, `${ist.toFixed(4)} erwartet ${soll}`);
}

console.log('\n== getSchulwochenForScope (Kurs-Beschneidung) ==');
setG('currentHalbjahr', 'halbjahr-1');
const w1 = G('getSchulwochenForScope')('Schiene1');
pruefe('HJ1 beschnitten auf 5 Wochen', w1.length === 5, `= ${w1.length}`);
pruefe('HJ1 = 66 Stunden', w1.reduce((s, w) => s + w.stunden, 0) === 66);
setG('currentHalbjahr', 'gesamt');
pruefe('Gesamt = alle 9 Wochen', G('getSchulwochenForScope')('Schiene1').length === 9);
setG('currentHalbjahr', 'halbjahr-1');

console.log('\n== calculateQuantitaet (stundengewichtet) ==');
setG('currentGroup', 'IFA12A');
G('selectCourseScope')('halbjahr-1');
const users = G('dashboardData').groups['IFA12A'].users;
pruefe('drei Personen', users.length === 3, `= ${users.length}`);

const byName = {};
users.forEach(u => { byName[u.name] = G('calculateQuantitaet')(u, 'IFA12A', 5); });

const anna = byName['Anna Abgabe'];
const bernd = byName['Bernd Beflissen'];
const clara = byName['Clara Caeruleus'];

pruefe('Anna 10 von 58.5 Std.', anna && anna.stundenErledigt === 10 && anna.stundenGesamt === 58.5,
       anna ? `${anna.stundenErledigt}/${anna.stundenGesamt}` : 'null');
pruefe('Bernd 9 von 58.5 Std.', bernd && bernd.stundenErledigt === 9,
       bernd ? `${bernd.stundenErledigt}/${bernd.stundenGesamt}` : 'null');
pruefe('Clara 0 Std.', clara && clara.stundenErledigt === 0);

pruefe('Anna > Bernd trotz weniger Aufgaben',
       anna.value > bernd.value,
       `Anna ${anna.value}% (1 Aufgabe) vs. Bernd ${bernd.value}% (4 Aufgaben)`);
pruefe('Anna hat weniger Aufgaben als Bernd',
       anna.aufgabenErledigt < bernd.aufgabenErledigt,
       `${anna.aufgabenErledigt} vs. ${bernd.aufgabenErledigt}`);

console.log('\n== Delta in Unterrichtsstunden ==');
[['Anna', anna], ['Bernd', bernd], ['Clara', clara]].forEach(([n, q]) => {
    console.log(`  ${n}: ist=${(q.ist * 100).toFixed(1)}% soll=${q.sollProzent}% `
              + `delta=${q.deltaStunden > 0 ? '+' : ''}${q.deltaStunden} Std.`);
});
pruefe('Clara maximal im Rueckstand', clara.deltaStunden < anna.deltaStunden);

console.log('\n== calculateMitarbeitsnote ==');
const ma = G('calculateMitarbeitsnote')(users[0], 'IFA12A', 5);
pruefe('liefert Ergebnis', ma !== null);
if (ma) {
    pruefe('Quantitaet gesetzt', ma.quantitaet !== null, `${ma.quantitaet}%`);
    pruefe('Delta gesetzt', ma.deltaStunden !== null, `${ma.deltaStunden} Std.`);
    pruefe('Note im gueltigen Bereich', ma.grade === null || (ma.grade >= 1 && ma.grade <= 6),
           `Note ${ma.grade}`);
}

console.log('\n== Rendering (Laufzeitfehler-Test) ==');
try {
    G('generateHalbjahresnotenTable')(users);
    const html = elements['groupHalbjahresnotenTable'].innerHTML;
    pruefe('Tabelle erzeugt', html.length > 0, `${html.length} Zeichen`);
    pruefe('enthaelt maTable', html.includes('maTable'));
    pruefe('enthaelt Delta-Spalte', html.includes('Delta'));
    pruefe('kein MA2-Rest', !html.includes('Prognose') && !html.includes('ma2Table'));
    pruefe('alle drei Personen', users.every(u => html.includes(u.name)));
} catch (e) { pruefe('generateHalbjahresnotenTable', false, e.message); }

try {
    G('updateHalbjahrCards')(users);
    pruefe('Cards befuellt', elements['hjQuantitaetText'].textContent !== '-',
           `Quantitaet ${elements['hjQuantitaetText'].textContent}, `
         + `Delta ${elements['hjDeltaText'].textContent}, `
         + `Note ${elements['hjGradeText'].textContent}`);
} catch (e) { pruefe('updateHalbjahrCards', false, e.message); }

try {
    G('updateCourseScopeUI')();
    const nav = elements['halbjahrNav'].innerHTML;
    pruefe('Navigation erzeugt', nav.includes('1. Halbjahr') && nav.includes('2. Halbjahr'));
    pruefe('gesperrter Kurs disabled', nav.includes('disabled'));
    pruefe('kein "Gesamt" bei nur einem Kurs', !nav.includes('>Gesamt<'));
} catch (e) { pruefe('updateCourseScopeUI', false, e.message); }

console.log('\n== Wechsel auf gesperrtes Halbjahr ==');
try {
    G('selectHalbjahr')('halbjahr-2');
    pruefe('kein Absturz', true);
    pruefe('leere Huelle', G('dashboardData').verfuegbar === false);
    pruefe('Hinweis sichtbar', elements['halbjahrHinweis'].style.display === '',
           elements['halbjahrHinweis'].textContent);
} catch (e) { pruefe('selectHalbjahr(gesperrt)', false, e.message); }

console.log(fehler === 0 ? '\nALLE FRONTEND-TESTS BESTANDEN' : `\n${fehler} FEHLER`);
process.exit(fehler === 0 ? 0 : 1);
