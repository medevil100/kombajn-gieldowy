"""Browser-only fullscreen toggle. Static trusted script; no Python callbacks."""


SCRIPT = r"""
(() => {
  // Own this node outside Streamlit's React tree so its fixed position is not
  // covered by the app header and rerenders do not remove the exit control.
  if (!document.getElementById('ki-fullscreen-control')) {
    const root = document.createElement('div');
    root.id = 'ki-fullscreen-control';
    const toggle = document.createElement('button');
    toggle.id = 'ki-fullscreen-toggle';
    toggle.type = 'button';
    toggle.textContent = 'Pełny ekran';
    toggle.setAttribute('aria-pressed', 'false');
    const status = document.createElement('span');
    status.id = 'ki-fullscreen-note';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.hidden = true;
    root.append(toggle, status);
    document.body.appendChild(root);
  }
  const slot = '__kiFullscreenControl';
  const previous = window[slot];
  if (previous && previous.version === 1) {
    previous.sync();
    requestAnimationFrame(previous.sync);
    return;
  }
  if (previous && previous.dispose) previous.dispose();
  let busy = false;
  const button = () => document.getElementById('ki-fullscreen-toggle');
  const note = () => document.getElementById('ki-fullscreen-note');
  const active = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  const available = () => document.documentElement.requestFullscreen
    ? document.fullscreenEnabled !== false
    : Boolean(document.documentElement.webkitRequestFullscreen && document.webkitFullscreenEnabled !== false);
  function message(text) {
    const element = note();
    if (element) { element.textContent = text; element.hidden = !text; }
  }
  function sync() {
    const element = button();
    if (!element) return;
    const on = active();
    element.textContent = on ? 'Wyjdź z pełnego ekranu' : 'Pełny ekran';
    element.setAttribute('aria-pressed', String(on));
    element.setAttribute('aria-busy', String(busy));
    element.title = on ? 'Wróć do zwykłego widoku KI' : 'Wyświetl KI bez paska adresu przeglądarki';
    element.disabled = busy || (!on && !available());
    if (!on && !available()) {
      element.textContent = 'Pełny ekran niedostępny';
      element.title = 'Ta przeglądarka nie udostępnia trybu pełnoekranowego. Otwórz KI w Chrome.';
    }
  }
  async function click(event) {
    if (!(event.target instanceof Element) || !event.target.closest('#ki-fullscreen-toggle')) return;
    event.preventDefault();
    if (busy) return;
    busy = true;
    message('');
    sync();
    try {
      if (active()) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        await exit.call(document);
      } else if (document.documentElement.requestFullscreen) {
        // Keep the request in this click handler, preserving user activation.
        await document.documentElement.requestFullscreen({navigationUI: 'hide'});
      } else if (document.documentElement.webkitRequestFullscreen) {
        await document.documentElement.webkitRequestFullscreen();
      } else {
        throw new Error('Unsupported');
      }
    } catch (_) {
      message('Przeglądarka nie pozwoliła zmienić trybu ekranu. Spróbuj ponownie w Chrome.');
    } finally {
      busy = false;
      sync();
    }
  }
  document.addEventListener('click', click);
  document.addEventListener('fullscreenchange', sync);
  document.addEventListener('webkitfullscreenchange', sync);
  window[slot] = {version: 1, sync, dispose: () => {
    document.removeEventListener('click', click);
    document.removeEventListener('fullscreenchange', sync);
    document.removeEventListener('webkitfullscreenchange', sync);
  }};
  sync();
  requestAnimationFrame(sync);
})();
"""


HTML = r"""
<style>
#ki-fullscreen-control{position:fixed;top:calc(env(safe-area-inset-top,0px) + 6px);right:56px;z-index:2147483000;font-family:Arial,sans-serif}
#ki-fullscreen-toggle{min-height:44px;max-width:calc(100vw - 110px);padding:8px 12px;border:1px solid #7c9ab8;border-radius:8px;background:#274d70;color:#fff;font-size:.95rem;font-weight:600;cursor:pointer;touch-action:manipulation}
#ki-fullscreen-toggle:focus-visible{outline:3px solid #fbbf24;outline-offset:2px}
#ki-fullscreen-toggle:disabled{opacity:.7;cursor:default}
#ki-fullscreen-note{position:absolute;top:100%;right:0;width:max-content;max-width:min(80vw,340px);padding:10px;background:#4a2c16;color:#fed7aa;border:1px solid #b87333;border-radius:6px;font-size:.9rem;overflow-wrap:anywhere}
#ki-fullscreen-note[hidden]{display:none!important}
</style>
"""


def render():
    import streamlit as st
    st.html(HTML + '<script>' + SCRIPT + '</script>', unsafe_allow_javascript=True)
