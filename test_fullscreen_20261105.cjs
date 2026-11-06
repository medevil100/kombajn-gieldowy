const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'fullscreen_control.py'), 'utf8');
const script = source.match(/SCRIPT = r"""\r?\n([\s\S]*?)"""/)[1];

class Element {
  constructor(id) { this.id = id; this.attributes = {}; this.hidden = true; this.disabled = false; }
  closest(selector) { return selector === '#' + this.id ? this : null; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

function environment() {
  const elements = {
    'ki-fullscreen-control': new Element('ki-fullscreen-control'),
    'ki-fullscreen-toggle': new Element('ki-fullscreen-toggle'),
    'ki-fullscreen-note': new Element('ki-fullscreen-note')
  };
  const listeners = new Map();
  const calls = {enter: 0, exit: 0};
  const doc = {
    fullscreenEnabled: true, fullscreenElement: null, documentElement: {},
    getElementById: id => elements[id],
    addEventListener: (kind, fn) => {
      if (!listeners.has(kind)) listeners.set(kind, new Set());
      listeners.get(kind).add(fn);
    },
    removeEventListener: (kind, fn) => listeners.get(kind)?.delete(fn)
  };
  const fire = (kind, event = {}) => Promise.all([...listeners.get(kind) || []].map(fn => fn(event)));
  doc.documentElement.requestFullscreen = async options => {
    assert.equal(options.navigationUI, 'hide');
    calls.enter++;
    doc.fullscreenElement = doc.documentElement;
    await fire('fullscreenchange');
  };
  doc.exitFullscreen = async function () {
    assert.equal(this, doc);
    calls.exit++;
    doc.fullscreenElement = null;
    await fire('fullscreenchange');
  };
  const context = vm.createContext({window: {}, document: doc, Element, requestAnimationFrame: fn => fn()});
  const run = () => vm.runInContext(script, context);
  return {elements, listeners, calls, doc, run, fire,
          button: () => elements['ki-fullscreen-toggle'],
          click: () => fire('click', {target: elements['ki-fullscreen-toggle'], preventDefault() {}})};
}

async function main() {
  {
    const e = environment(); e.run();
    assert.equal(e.button().textContent, 'Pełny ekran');
    await e.click();
    assert.equal(e.doc.fullscreenElement, e.doc.documentElement);
    assert.equal(e.button().textContent, 'Wyjdź z pełnego ekranu');
    assert.equal(e.button().attributes['aria-pressed'], 'true');
    await e.click();
    assert.equal(e.doc.fullscreenElement, null);
    assert.equal(e.button().textContent, 'Pełny ekran');
    assert.deepEqual(e.calls, {enter: 1, exit: 1});
    console.log('OK: wejście i wyjście tym samym przyciskiem');
  }
  {
    const e = environment(); e.run(); await e.click();
    e.doc.fullscreenElement = null;
    await e.fire('fullscreenchange');
    assert.equal(e.button().textContent, 'Pełny ekran');
    assert.equal(e.button().attributes['aria-pressed'], 'false');
    console.log('OK: wyjście przeglądarką aktualizuje napis');
  }
  {
    const e = environment(); e.run(); await e.click();
    e.elements['ki-fullscreen-toggle'] = new Element('ki-fullscreen-toggle');
    e.run(); e.run();
    assert.equal(e.listeners.get('click').size, 1);
    assert.equal(e.button().textContent, 'Wyjdź z pełnego ekranu');
    await e.click();
    assert.deepEqual(e.calls, {enter: 1, exit: 1});
    console.log('OK: ponowne renderowanie nie powiela obsługi kliknięć');
  }
  {
    const e = environment(); let release;
    e.doc.documentElement.requestFullscreen = () => {
      e.calls.enter++;
      return new Promise(resolve => {release = resolve;});
    };
    e.run(); const pending = e.click();
    assert.equal(e.button().disabled, true);
    e.elements['ki-fullscreen-toggle'] = new Element('ki-fullscreen-toggle');
    e.run(); await e.click();
    assert.equal(e.calls.enter, 1);
    assert.equal(e.button().disabled, true);
    e.doc.fullscreenElement = e.doc.documentElement;
    release(); await pending;
    assert.equal(e.button().disabled, false);
    assert.equal(e.button().textContent, 'Wyjdź z pełnego ekranu');
    console.log('OK: podwójne dotknięcie i odświeżenie podczas przełączania');
  }
  {
    const e = environment();
    e.doc.documentElement.requestFullscreen = async () => {throw new Error('Denied');};
    e.run(); await e.click();
    assert.equal(e.button().disabled, false);
    assert.equal(e.button().attributes['aria-pressed'], 'false');
    assert.equal(e.elements['ki-fullscreen-note'].hidden, false);
    assert.match(e.elements['ki-fullscreen-note'].textContent, /Przeglądarka nie pozwoliła/);
    console.log('OK: odmowa nie udaje włączonego trybu i pokazuje komunikat');
  }
  {
    const e = environment(); e.doc.fullscreenEnabled = false; e.run();
    assert.equal(e.button().disabled, true);
    assert.equal(e.button().textContent, 'Pełny ekran niedostępny');
    console.log('OK: brak obsługi pełnego ekranu');
  }
}

main().catch(error => {console.error(error); process.exitCode = 1;});
