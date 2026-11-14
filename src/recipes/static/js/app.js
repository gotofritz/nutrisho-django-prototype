// Browser-side behaviour for every page (#62). base.html loads this file once,
// deferred and after htmx, so it is served from 'self' under the
// Content-Security-Policy and needs no inline script. Every page gets the
// whole file: hx-boost swaps <body> without reloading <head>, so a
// page-specific script would be missing after a boosted visit. Each listener
// is delegated to the document and does nothing on a page without its markup.
//
// Templates opt in with data attributes instead of onclick=/hx-on:
//   data-cancel-draft="<row selector>"  removes an unsaved draft row
//   data-close-panel="<panel id>"       empties a panel, refocuses its toggle
//   data-panel-toggle="<panel id>"      a second click closes the open panel;
//                                       its aria-expanded follows the panel
//   data-position-in / -of / -row       a draft posts its place in the list
//   data-split-at="<textarea name>"     posts the cursor offset for a split
//   data-indeterminate="true"           a checkbox shows the dashed state
//   data-clear-history                  drops htmx's localStorage snapshots
//   data-dismiss-toast                  removes the toast it sits in
//   data-toast-text                     a toast's text, read out on arrival
//   data-escape                         Escape in its form presses it (Cancel)
//
// Not opt-in: resting on any control shows the keys that work it (#60).
(function () {
  'use strict';

  // --- Textareas grow with their text ---------------------------------------

  function resizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  }
  function initTextareas(root) {
    (root || document).querySelectorAll('textarea').forEach(resizeTextarea);
  }
  document.addEventListener('DOMContentLoaded', function () { initTextareas(); });
  document.addEventListener('input', function (e) {
    if (e.target.tagName === 'TEXTAREA') resizeTextarea(e.target);
  });

  // --- Bulk selection panels (steps and ingredients) ------------------------

  function syncStepsPanel() {
    var panel = document.getElementById('steps-panel');
    if (!panel) return;
    var n = document.querySelectorAll('.step-select:checked').length;
    panel.hidden = n < 1;
    document.getElementById('steps-merge').disabled = n < 2;
    document.getElementById('steps-panel-count').textContent =
      n + (n === 1 ? ' step selected' : ' steps selected');
  }
  function hideReassignPanel() {
    var panel = document.getElementById('reassign-panel');
    if (panel) panel.hidden = true;
  }
  document.addEventListener('htmx:afterSettle', function (e) {
    initTextareas(e.detail.elt);
    syncStepsPanel();
    if (document.querySelectorAll('.ingredient-select:checked').length === 0) {
      hideReassignPanel();
    }
  });
  document.addEventListener('change', function (e) {
    if (e.target.matches('.ingredient-select')) {
      var n = document.querySelectorAll('.ingredient-select:checked').length;
      var panel = document.getElementById('reassign-panel');
      if (panel) panel.hidden = n < 1;
    }
    if (e.target.matches('.step-select')) {
      syncStepsPanel();
      announce(document.getElementById('steps-panel-count').textContent);
    }
    if (e.target.id === 'reassign-target') {
      var ni = document.getElementById('new-group-name');
      if (ni) ni.hidden = e.target.value !== 'new';
    }
  });
  document.addEventListener('click', function (e) {
    if (e.target.id === 'steps-cancel') {
      document.querySelectorAll('.step-select:checked').forEach(function (cb) {
        cb.checked = false;
      });
      syncStepsPanel();
    }
    if (e.target.id === 'reassign-cancel') {
      document.querySelectorAll('.ingredient-select:checked').forEach(function (cb) {
        cb.checked = false;
      });
      hideReassignPanel();
    }
  });

  // --- Save-error banner (#37) ----------------------------------------------
  // A failed htmx request is not swapped (see htmx-config), so an open edit
  // form keeps its text; this banner tells the user the change did not land.

  function showSaveError(detail, hint) {
    var banner = document.getElementById('save-error');
    if (!banner) return;
    var verb = detail.requestConfig && detail.requestConfig.verb;
    var what = verb === 'get' ? 'That did not load.' : 'Your change was not saved.';
    document.getElementById('save-error-message').textContent = what + ' ' + hint;
    banner.hidden = false;
  }
  document.addEventListener('htmx:responseError', function (e) {
    var status = e.detail.xhr.status;
    showSaveError(e.detail, status === 403 || status === 404
      ? 'Reload the page and try again.'
      : 'Please try again.');
  });
  ['htmx:sendError', 'htmx:timeout'].forEach(function (name) {
    document.addEventListener(name, function (e) {
      showSaveError(e.detail, 'Check your connection and try again.');
    });
  });
  document.addEventListener('htmx:afterRequest', function (e) {
    var verb = e.detail.requestConfig && e.detail.requestConfig.verb;
    var banner = document.getElementById('save-error');
    if (banner && e.detail.successful && verb !== 'get') banner.hidden = true;
  });
  document.addEventListener('click', function (e) {
    if (e.target.id === 'save-error-dismiss') {
      document.getElementById('save-error').hidden = true;
    }
  });

  // --- Toasts (#75) ---------------------------------------------------------
  // "Deleted X. Undo" arrives with the next page; its text goes through the
  // live region, since a region rendered with its text is often not read out.

  document.addEventListener('click', function (e) {
    var dismiss = e.target.closest('[data-dismiss-toast]');
    if (dismiss) dismiss.closest('[data-toast]').remove();
  });

  // --- Announcements (#61) --------------------------------------------------
  // Polite announcements go through one live region that is always in the
  // page: a region swapped in with its text already set is often not read
  // out. Messages queued in the same moment are read together.

  var announceQueue = [];
  function announce(message) {
    var region = document.getElementById('a11y-status');
    message = (message || '').replace(/\s+/g, ' ').trim();
    if (!region || !message) return;
    if (!announceQueue.length) {
      region.textContent = '';
      setTimeout(function () {
        region.textContent = announceQueue.join(' ');
        announceQueue = [];
      }, 100);
    }
    announceQueue.push(message);
  }
  // Sent by the delete views in HX-Trigger, since a deleted row just vanishes.
  document.addEventListener('announce', function (e) {
    announce(e.detail && e.detail.message);
  });

  // --- Focus after a swap (#61) ---------------------------------------------
  // htmx itself refocuses an element whose id survives the swap (the move
  // buttons) and focuses [autofocus] in new content (edit forms, panels). Any
  // other swap that removes the focused element (Save, Cancel, Delete) drops
  // focus to <body>, so the spot is remembered before the swap and focus goes
  // to whatever took its place, or failing that to its nearest neighbour.

  var FOCUSABLE = 'a[href], button, input:not([type="hidden"]), select, textarea, [tabindex]';
  var focusSpot = null;
  function focusLost() {
    var a = document.activeElement;
    return !a || a === document.body || !a.isConnected;
  }
  function spotOf(el) {
    var chain = [];
    for (var p = el.parentElement; p && p !== document.body; p = p.parentElement) chain.push(p);
    return { el: el, prev: el.previousElementSibling, chain: chain };
  }
  function visible(el) {
    return el.getClientRects().length > 0 && !el.disabled;
  }
  function first(root, selector) {
    if (root.matches(selector) && visible(root)) return root;
    var found = root.querySelectorAll(selector);
    for (var i = 0; i < found.length; i++) if (visible(found[i])) return found[i];
    return null;
  }
  function focusInto(el) {
    // An editable display (.editable) is what Save and Cancel bring back.
    var to = first(el, '.editable') || first(el, FOCUSABLE);
    if (!to) return false;
    if (!to.matches(FOCUSABLE)) to.setAttribute('tabindex', '-1');
    to.focus();
    return document.activeElement === to;
  }
  function focusNear(spot) {
    var parent = spot.chain[0];
    // What sits where the removed element was: its replacement, or else the
    // next sibling; then the previous sibling, then the ancestors.
    var inPlace = spot.prev && spot.prev.isConnected
      ? spot.prev.nextElementSibling
      : (parent && parent.isConnected ? parent.firstElementChild : null);
    var candidates = [spot.el, inPlace, spot.prev].concat(spot.chain);
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      if (c && c.isConnected && focusInto(c)) return;
    }
  }
  document.addEventListener('htmx:beforeSwap', function (e) {
    var t = e.detail.target;
    var a = document.activeElement;
    focusSpot = t && t !== document.body && a && a !== document.body && t.contains(a)
      ? spotOf(t)
      : null;
  });
  // The swap has happened by now; [autofocus] is applied later, on settle,
  // and still wins.
  document.addEventListener('htmx:afterRequest', function () {
    var spot = focusSpot;
    focusSpot = null;
    if (spot && focusLost()) focusNear(spot);
  });

  // A boosted page swap (or the back button) is a new page: focus its
  // <h1 tabindex="-1">, unless an [autofocus] field already took focus, and
  // announce the title when no heading was focused.
  function pageArrived() {
    var heading = document.querySelector('h1[tabindex="-1"]');
    if (heading && focusLost()) {
      heading.focus();
    } else {
      announce(document.title);
    }
  }
  document.addEventListener('htmx:historyRestore', pageArrived);
  document.addEventListener('htmx:afterSettle', function (e) {
    var root = e.target;
    // A form re-rendered with errors (an inline 422, or a boosted full-page
    // POST) puts the cursor on the first invalid field, which
    // aria-describedby ties to its error message.
    var invalid = first(root, '[aria-invalid="true"]');
    if (invalid) {
      invalid.focus();
    } else if (root === document.body && e.detail.boosted) {
      pageArrived();
    }
    if (root === document.body) return;
    // Counts and "Saved" in swapped content are read out.
    if (root.matches('[data-announce]')) announce(root.textContent);
    root.querySelectorAll('[data-announce]').forEach(function (el) {
      announce(el.textContent);
    });
  });

  // --- Drafts and panels ----------------------------------------------------

  document.addEventListener('click', function (e) {
    // An unsaved draft row is removed without a request.
    var cancel = e.target.closest('[data-cancel-draft]');
    if (cancel) {
      var row = cancel.closest(cancel.dataset.cancelDraft);
      var spot = spotOf(row);
      row.remove();
      focusNear(spot);
    }
    // A panel's Cancel hands focus back to the toggle that opened it.
    var close = e.target.closest('[data-close-panel]');
    if (close) {
      var panelId = close.dataset.closePanel;
      var panel = document.getElementById(panelId);
      if (panel) panel.innerHTML = '';
      syncPanelToggles();
      var toggle = document.querySelector('[aria-controls="' + panelId + '"]');
      if (toggle) toggle.focus();
    }
  });
  // Escape in an inline editor presses its Cancel (#60), which puts the line
  // back and, through the focus handling above, focus on it.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || e.defaultPrevented || !e.target.closest) return;
    var form = e.target.closest('form');
    var cancel = form && form.querySelector('[data-escape]');
    if (cancel) {
      e.preventDefault();
      cancel.click();
    }
  });
  // A toggle says whether its panel is open: open means the panel has content.
  function syncPanelToggles() {
    document.querySelectorAll('[data-panel-toggle]').forEach(function (toggle) {
      var panel = document.getElementById(toggle.dataset.panelToggle);
      var open = Boolean(panel && panel.innerHTML.trim());
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  document.addEventListener('htmx:afterSettle', syncPanelToggles);
  // A panel toggle loads its panel; clicked again while the panel is open, it
  // empties the panel instead of loading it a second time.
  document.addEventListener('htmx:beforeRequest', function (e) {
    var toggle = e.target.closest('[data-panel-toggle]');
    if (!toggle) return;
    var panel = document.getElementById(toggle.dataset.panelToggle);
    if (panel && panel.innerHTML.trim()) {
      panel.innerHTML = '';
      syncPanelToggles();
      e.preventDefault();
    }
  });

  // --- Values computed when a request is made -------------------------------

  document.addEventListener('htmx:configRequest', function (e) {
    var params = e.detail.parameters;
    // A draft posts its place among its siblings, so the server inserts it
    // where it is on screen however many drafts are open.
    var draft = e.target.closest('[data-position-in]');
    if (draft) {
      var rows = draft.closest(draft.dataset.positionIn).querySelectorAll(draft.dataset.positionOf);
      params.position = Array.prototype.indexOf.call(rows, draft.closest(draft.dataset.positionRow));
    }
    // Split at the cursor, counted in code points as the server counts.
    var split = e.target.closest('[data-split-at]');
    if (split) {
      var t = split.form.elements[split.dataset.splitAt];
      params.split_at = Array.from(t.value.slice(0, t.selectionStart)).length;
    }
  });

  // --- Key hints (#60) ------------------------------------------------------
  // A pointer that rests on a control, or keyboard focus that stays on one,
  // shows after a pause which keys work it: Enter for a link, Enter or Space
  // for a button, Space for a tick box, and in an editor's field the Enter and
  // Escape of its Save and Cancel. It is visual help only (aria-hidden): a
  // screen reader already says what a control is. Any key, a press, leaving
  // the control or scrolling puts it away; the pointer may move onto it
  // (WCAG 1.4.13). A titled control shows its title in the hint, and loses
  // the attribute while hovered, so the browser's tooltip cannot cover it.

  var KEY_HINT_DELAY = 2000;
  var HINTED = 'a[href], button, input, select, textarea, summary, label';
  var hintTimer = null;
  var hintAnchor = null;
  var hintTitled = null;
  var pressed = null; // a control just pressed gets no hint until left

  function hintBox() {
    var box = document.getElementById('key-hint');
    if (!box) {
      // Made on demand: a boosted visit replaces <body>, and the box with it.
      box = document.createElement('div');
      box.id = 'key-hint';
      box.className = 'key-hint';
      box.setAttribute('aria-hidden', 'true');
      box.hidden = true;
      document.body.appendChild(box);
    }
    return box;
  }
  function lowerFirst(text) {
    text = (text || '').replace(/\s+/g, ' ').trim();
    return text.charAt(0).toLowerCase() + text.slice(1);
  }
  // [{keys: [...], does: '...'}] for a control, or [] when no key works it.
  function keysFor(el) {
    if (el.disabled) return [];
    var type = (el.getAttribute('type') || '').toLowerCase();
    var form = el.form || el.closest('form');
    if (el.matches('a[href]')) return [{ keys: ['Enter'], does: 'to open' }];
    if (el.matches('button, summary, input[type="submit"], input[type="button"], input[type="reset"]')) {
      var does = el.matches('.editable') ? 'to edit'
        : el.hasAttribute('aria-expanded') || el.matches('summary') ? 'to open or close'
          : 'to press';
      var hints = [{ keys: ['Enter', 'Space'], does: does }];
      if (el.hasAttribute('data-escape')) {
        hints.push({ keys: ['Esc'], does: 'from any field of this form' });
      }
      return hints;
    }
    if (type === 'checkbox') return [{ keys: ['Space'], does: 'to tick or untick' }];
    if (type === 'radio') {
      return [{ keys: ['Space'], does: 'to choose' }, { keys: ['↑', '↓'], does: 'to move between choices' }];
    }
    if (type === 'hidden') return [];
    if (el.matches('select')) return [{ keys: ['↑', '↓'], does: 'to change' }];
    // A field: Enter submits its form (not in a textarea), Escape cancels.
    var fieldHints = [];
    var submit = form && form.querySelector('button[type="submit"], button:not([type]), input[type="submit"]');
    if (submit && !el.matches('textarea')) {
      fieldHints.push({ keys: ['Enter'], does: 'to ' + lowerFirst(submit.textContent || submit.value) });
    }
    var cancel = form && form.querySelector('[data-escape]');
    if (cancel) fieldHints.push({ keys: ['Esc'], does: 'to ' + lowerFirst(cancel.textContent) });
    return fieldHints;
  }
  function fillHint(box, title, hints) {
    box.textContent = '';
    if (title) {
      var p = document.createElement('p');
      p.className = 'key-hint-title';
      p.textContent = title;
      box.appendChild(p);
    }
    hints.forEach(function (hint) {
      var line = document.createElement('p');
      hint.keys.forEach(function (key, i) {
        if (i) line.appendChild(document.createTextNode(' or '));
        var kbd = document.createElement('kbd');
        kbd.textContent = key;
        line.appendChild(kbd);
      });
      line.appendChild(document.createTextNode(' ' + hint.does));
      box.appendChild(line);
    });
  }
  // Above the control, or below it when there is no room; inside the window.
  function placeHint(box, anchor) {
    var r = anchor.getBoundingClientRect();
    var gap = 6;
    var w = box.offsetWidth;
    var h = box.offsetHeight;
    var top = r.top - h - gap >= 0 ? r.top - h - gap : r.bottom + gap;
    var left = Math.max(gap, Math.min(r.left, document.documentElement.clientWidth - w - gap));
    box.style.top = top + 'px';
    box.style.left = left + 'px';
  }
  function restoreTitle() {
    if (hintTitled && hintTitled.hasAttribute('data-key-hint-title')) {
      hintTitled.setAttribute('title', hintTitled.getAttribute('data-key-hint-title'));
      hintTitled.removeAttribute('data-key-hint-title');
    }
    hintTitled = null;
  }
  function hideHint() {
    clearTimeout(hintTimer);
    hintTimer = null;
    hintAnchor = null;
    restoreTitle();
    var box = document.getElementById('key-hint');
    if (box) box.hidden = true;
  }
  function showHint(anchor) {
    if (!anchor.isConnected) return;
    var control = anchor.matches('label') ? anchor.control : anchor;
    var hints = control ? keysFor(control) : [];
    var title = hintTitled ? hintTitled.getAttribute('data-key-hint-title') : '';
    if (!hints.length) return;
    var box = hintBox();
    fillHint(box, title, hints);
    box.hidden = false;
    placeHint(box, anchor);
  }
  function startHint(anchor, titled) {
    hideHint();
    hintAnchor = anchor;
    // The browser's own tooltip would show first and cover the hint.
    if (titled && titled.hasAttribute('title')) {
      titled.setAttribute('data-key-hint-title', titled.getAttribute('title'));
      titled.removeAttribute('title');
      hintTitled = titled;
    }
    hintTimer = setTimeout(function () { showHint(anchor); }, KEY_HINT_DELAY);
  }
  function insideHint(node) {
    var box = document.getElementById('key-hint');
    return Boolean(node && box && box.contains(node));
  }
  document.addEventListener('pointerover', function (e) {
    if (e.pointerType === 'touch' || !e.target.closest) return;
    var anchor = e.target.closest(HINTED);
    if (!anchor || anchor === hintAnchor || anchor === pressed) return;
    if (insideHint(e.target)) return;
    pressed = null;
    var titled = e.target.closest('[title]');
    startHint(anchor, titled && anchor.contains(titled) ? titled : null);
  });
  document.addEventListener('pointerout', function (e) {
    if (pressed && !(e.relatedTarget && pressed.contains(e.relatedTarget))) pressed = null;
    if (e.pointerType === 'touch' || !hintAnchor) return;
    var to = e.relatedTarget;
    if (to && (hintAnchor.contains(to) || insideHint(to))) return;
    if (insideHint(e.target) || hintAnchor.contains(e.target)) hideHint();
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target;
    // Focus from a click shows no hint; from the keyboard (or a text field) it does.
    if (!el.matches || !el.matches(HINTED) || !el.matches(':focus-visible')) return;
    startHint(el, null);
  });
  document.addEventListener('focusout', function (e) {
    if (e.target === hintAnchor) hideHint();
  });
  document.addEventListener('keydown', hideHint, true);
  document.addEventListener('pointerdown', function (e) {
    pressed = e.target.closest ? e.target.closest(HINTED) : null;
    hideHint();
  }, true);
  document.addEventListener('scroll', hideHint, true);
  document.addEventListener('htmx:beforeSwap', function (e) {
    if (hintAnchor && e.detail.target && e.detail.target.contains(hintAnchor)) hideHint();
  });

  // --- New content, on page load and after every swap -----------------------

  htmx.onLoad(function (root) {
    if (!root.querySelectorAll) return;
    // indeterminate is a DOM property with no HTML attribute, so the dashed
    // "some selected" state cannot be rendered server-side.
    root.querySelectorAll('[data-indeterminate]').forEach(function (box) {
      box.indeterminate = box.dataset.indeterminate === 'true';
    });
    // Log-out and session expiry land on the login page: drop htmx's page
    // snapshots so the Back button cannot replay a recipe from localStorage on
    // a shared device.
    root.querySelectorAll('[data-toast-text]').forEach(function (el) {
      announce(el.textContent + (el.parentElement.querySelector('form') ? ' Undo is available.' : ''));
    });
    if (root.querySelector('[data-clear-history]')) {
      try { localStorage.removeItem('htmx-history-cache'); } catch (err) { /* storage off */ }
    }
  });
})();
