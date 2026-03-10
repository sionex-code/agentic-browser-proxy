# ─────────────────────────── JavaScript Injection Scripts ───────────────────────────
# These scripts are evaluated in the browser to extract page state, elements, and text.

EXTRACT_ELEMENTS_JS = """
(() => {
  const INTERACTIVE_TAGS = new Set([
    'A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'DETAILS', 'SUMMARY'
  ]);
  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'tab', 'menuitem', 'checkbox', 'radio', 'switch',
    'textbox', 'combobox', 'searchbox', 'option', 'menuitemcheckbox',
    'menuitemradio', 'slider', 'spinbutton', 'treeitem', 'listbox'
  ]);

  const isVisible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom >= 0 &&
      rect.right >= 0 &&
      rect.top <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.left <= (window.innerWidth || document.documentElement.clientWidth) &&
      style.visibility !== 'hidden' &&
      style.display !== 'none' &&
      parseFloat(style.opacity) > 0
    );
  };

  const isInteractive = el => {
    if (INTERACTIVE_TAGS.has(el.tagName)) return true;
    const role = el.getAttribute('role');
    if (role && INTERACTIVE_ROLES.has(role)) return true;
    if (el.hasAttribute('onclick') || el.hasAttribute('tabindex')) return true;
    if (el.hasAttribute('contenteditable') && el.getAttribute('contenteditable') !== 'false') return true;
    const cursor = getComputedStyle(el).cursor;
    if (cursor === 'pointer' && el.tagName !== 'HTML' && el.tagName !== 'BODY') return true;
    return false;
  };

  const getLabel = el => {
    // Check aria-label
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel.trim();
    // Check aria-labelledby
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const labelEl = document.getElementById(labelledBy);
      if (labelEl) return labelEl.innerText?.trim();
    }
    // Check <label> for inputs
    if (el.id) {
      const label = document.querySelector(`label[for="${el.id}"]`);
      if (label) return label.innerText?.trim();
    }
    // Check title
    if (el.title) return el.title.trim();
    return null;
  };

  const getInfo = (el, idx) => {
    const rect = el.getBoundingClientRect();
    const info = {
      index: idx,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || undefined,
      interactive: isInteractive(el)
    };

    // Position (rounded)
    info.pos = `${Math.round(rect.left)},${Math.round(rect.top)}`;

    // ID & classes (compact)
    if (el.id) info.id = el.id;
    const cls = [...(el.classList || [])].slice(0, 3).join(' ');
    if (cls) info.cls = cls;

    // Label / accessible name
    const label = getLabel(el);
    if (label && label.length < 100) info.label = label;

    // Tag-specific attributes
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
      info.type = el.type || 'text';
      if (el.name) info.name = el.name;
      if (el.placeholder) info.placeholder = el.placeholder;
      if (el.value) info.value = el.value.substring(0, 100);
      info.disabled = el.disabled || undefined;
      info.readonly = el.readOnly || undefined;
      if (el.required) info.required = true;
    } else if (tag === 'SELECT') {
      info.name = el.name || undefined;
      const options = [...el.options].slice(0, 10).map(o => ({
        value: o.value,
        text: o.text.trim().substring(0, 50),
        selected: o.selected || undefined
      }));
      info.options = options;
    } else if (tag === 'A') {
      const text = el.innerText?.trim();
      if (text && text.length < 100) info.text = text;
      if (el.href && !el.href.startsWith('javascript:')) info.href = el.href;
    } else if (tag === 'BUTTON') {
      info.text = (el.innerText?.trim() || el.value || '').substring(0, 80);
      info.disabled = el.disabled || undefined;
    } else if (tag === 'IMG') {
      info.alt = el.alt || undefined;
      info.src = el.src?.substring(0, 100) || undefined;
    } else if (tag === 'IFRAME') {
      info.src = el.src?.substring(0, 100) || undefined;
      info.name = el.name || undefined;
    } else {
      const text = el.innerText?.trim();
      if (text && text.length < 80) info.text = text;
    }

    // Clean undefined values
    Object.keys(info).forEach(k => info[k] === undefined && delete info[k]);
    return info;
  };

  // Collect ALL visible elements
  const allElements = [...document.querySelectorAll('*')].filter(isVisible);

  // Separate interactive vs non-interactive
  const interactive = [];
  const nonInteractive = [];

  allElements.forEach(el => {
    if (isInteractive(el)) {
      interactive.push(el);
    } else {
      // Only keep non-interactive elements with meaningful text
      const text = el.innerText?.trim();
      const tag = el.tagName;
      if (
        (tag === 'H1' || tag === 'H2' || tag === 'H3' || tag === 'H4' ||
         tag === 'P' || tag === 'SPAN' || tag === 'LI' || tag === 'TD' ||
         tag === 'TH' || tag === 'LABEL' || tag === 'LEGEND' ||
         tag === 'IMG' || tag === 'IFRAME') &&
        (text || tag === 'IMG' || tag === 'IFRAME')
      ) {
        nonInteractive.push(el);
      }
    }
  });

  // Index: interactive first, then non-interactive (whole page)
  let idx = 0;
  const results = [];
  for (const el of interactive) {
    results.push(getInfo(el, idx++));
  }
  // Add non-interactive context (scan whole page)
  for (const el of nonInteractive) {
    results.push(getInfo(el, idx++));
  }

  return JSON.stringify(results);
})();
"""

# ─────────────────────────── Page State JS ───────────────────────────

PAGE_STATE_JS = """
(() => {
  const docEl = document.documentElement;
  const scrollTop = window.pageYOffset || docEl.scrollTop;
  const scrollHeight = docEl.scrollHeight;
  const clientHeight = docEl.clientHeight;
  const scrollPercent = scrollHeight > clientHeight
    ? Math.round((scrollTop / (scrollHeight - clientHeight)) * 100)
    : 0;

  const focused = document.activeElement;
  let focusedInfo = null;
  if (focused && focused !== document.body && focused !== docEl) {
    focusedInfo = {
      tag: focused.tagName.toLowerCase(),
      id: focused.id || undefined,
      type: focused.type || undefined,
      value: focused.value?.substring(0, 100) || undefined
    };
    Object.keys(focusedInfo).forEach(k => focusedInfo[k] === undefined && delete focusedInfo[k]);
  }

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    scrollPercent: scrollPercent,
    pageHeight: scrollHeight,
    viewportHeight: clientHeight,
    focusedElement: focusedInfo,
    hasForms: document.forms.length > 0,
    formCount: document.forms.length,
    iframeCount: document.querySelectorAll('iframe').length
  });
})();
"""

# ─────────────────────────── Page Text Extraction JS ───────────────────────────

EXTRACT_PAGE_TEXT_JS = """
(() => {
  const TEXT_TAGS = new Set([
    'SPAN', 'P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'LI', 'TD', 'TH', 'BLOCKQUOTE', 'FIGCAPTION', 'LABEL',
    'ARTICLE', 'SECTION', 'ASIDE', 'MAIN', 'HEADER', 'FOOTER',
    'CAPTION', 'DD', 'DT', 'LEGEND', 'SUMMARY', 'MARK', 'TIME', 'EM', 'STRONG'
  ]);

  const isVisible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom >= 0 &&
      rect.right >= 0 &&
      rect.top <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.left <= (window.innerWidth || document.documentElement.clientWidth) &&
      style.visibility !== 'hidden' &&
      style.display !== 'none' &&
      parseFloat(style.opacity) > 0
    );
  };

  // Get first ~2 sentences from text
  const getSnippet = (text, maxLen = 200) => {
    if (!text || text.length === 0) return null;
    text = text.replace(/\\s+/g, ' ').trim();
    if (text.length <= maxLen) return text;

    // Try to cut at sentence boundary (. ! ? followed by space or end)
    const sentencePattern = /[.!?](?:\\s|$)/g;
    let match;
    let sentenceCount = 0;
    let cutPos = maxLen;

    while ((match = sentencePattern.exec(text)) !== null) {
      sentenceCount++;
      if (sentenceCount >= 2) {
        cutPos = match.index + 1;
        break;
      }
    }

    if (cutPos > maxLen) cutPos = maxLen;
    const snippet = text.substring(0, cutPos).trim();
    return snippet + (snippet.length < text.length ? '...' : '');
  };

  const seen = new Set();
  const results = [];

  const allElements = [...document.querySelectorAll('*')].filter(el => {
    if (!TEXT_TAGS.has(el.tagName)) return false;
    if (!isVisible(el)) return false;
    return true;
  });

  for (const el of allElements) {
    // Get direct text content (not from children) to avoid duplicates
    let text = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent;
      }
    }
    text = text.replace(/\\s+/g, ' ').trim();

    // If no direct text, use innerText but only if no text-tag children
    if (!text || text.length < 15) {
      const hasTextChild = [...el.children].some(c => TEXT_TAGS.has(c.tagName));
      if (!hasTextChild) {
        text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
      }
    }

    if (!text || text.length < 15) continue; // skip very short text

    // Deduplicate
    const key = text.substring(0, 80);
    if (seen.has(key)) continue;
    seen.add(key);

    const idx = el.getAttribute('data-agent-idx');
    const snippet = getSnippet(text);
    if (snippet) {
      results.push({
        index: idx ? parseInt(idx) : null,
        tag: el.tagName.toLowerCase(),
        snippet: snippet,
        fullLength: text.length
      });
    }

    if (results.length >= 40) break; // cap to avoid overwhelming the AI
  }

  return JSON.stringify(results);
})();
"""

# ─────────────────────────── Cursor Humanization Scripts ───────────────────────────

INIT_CURSOR_JS = """
(() => {
    try {
        // Remove existing cursor if any
        const existingCursor = document.getElementById('__playwright_cursor');
        if (existingCursor) {
            existingCursor.remove();
        }

        const cursor = document.createElement('div');
        cursor.id = '__playwright_cursor';

        Object.assign(cursor.style, {
            position: 'fixed',
            top: '0px',
            left: '0px',
            width: '24px',
            height: '24px',
            zIndex: '999999',
            pointerEvents: 'none',
            backgroundImage: 'url(https://i.imgur.com/PEZdLDA.png)',
            backgroundSize: 'contain',
            backgroundRepeat: 'no-repeat',
            backgroundColor: 'transparent',
            border: 'none',
            borderRadius: '0',
            filter: 'drop-shadow(0 0 2px white)'
        });

        document.body.appendChild(cursor);

        window.__cursor_position = { x: 0, y: 0 };
        window.__move_cursor = (x, y) => {
            cursor.style.left = x + 'px';
            cursor.style.top = y + 'px';
            window.__cursor_position = { x, y };
        };

        window.__get_cursor_position = () => {
            return window.__cursor_position;
        };

        console.log("✅ Cursor humanization initialized");

    } catch (err) {
        console.error("💥 Error initializing cursor:", err);
    }
})();
"""

RESTORE_CURSOR_POSITION_JS = """
((x, y) => {
    try {
        if (window.__move_cursor) {
            window.__move_cursor(x, y);
            return true;
        }
        return false;
    } catch (err) {
        console.error("Error restoring cursor position:", err);
        return false;
    }
})
"""

GET_CURSOR_POSITION_JS = """
(() => {
    try {
        if (window.__get_cursor_position) {
            return window.__get_cursor_position();
        }
        return { x: 0, y: 0 };
    } catch (err) {
        return { x: 0, y: 0 };
    }
})();
"""
