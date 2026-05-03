(function () {
  const KEY = 'color-theme';
  const EMOJI_RE = /\p{Emoji_Presentation}/gu;

  /* Wrap emoji characters in spans so light mode can re-invert just them */
  function wrapEmojis(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) {
      const p = n.parentElement;
      if (!p) continue;
      const tag = p.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      if (p.classList.contains('emoji-fix')) continue;
      if (p.closest('#theme-toggle')) continue;
      EMOJI_RE.lastIndex = 0;
      if (EMOJI_RE.test(n.nodeValue)) nodes.push(n);
    }
    nodes.forEach(n => {
      const re = new RegExp(EMOJI_RE.source, EMOJI_RE.flags);
      const frag = document.createDocumentFragment();
      let last = 0, m;
      while ((m = re.exec(n.nodeValue)) !== null) {
        if (m.index > last) frag.appendChild(document.createTextNode(n.nodeValue.slice(last, m.index)));
        const s = document.createElement('span');
        s.className = 'emoji-fix';
        s.textContent = m[0];
        frag.appendChild(s);
        last = m.index + m[0].length;
      }
      if (last < n.nodeValue.length) frag.appendChild(document.createTextNode(n.nodeValue.slice(last)));
      n.parentNode.replaceChild(frag, n);
    });
  }

  function apply(mode) {
    document.documentElement.classList.toggle('light', mode === 'light');
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = mode === 'light' ? '🌙' : '☀️';
  }

  /* Apply before first paint to avoid flash */
  const saved = localStorage.getItem(KEY) || 'dark';
  if (saved === 'light') document.documentElement.classList.add('light');

  document.addEventListener('DOMContentLoaded', function () {
    /* Wrap emojis already in the DOM */
    wrapEmojis(document.body);

    /* Watch for dynamically added nodes (rendered cards etc.) */
    const obs = new MutationObserver(mutations => {
      mutations.forEach(m => {
        m.addedNodes.forEach(node => {
          if (node.nodeType === Node.ELEMENT_NODE) wrapEmojis(node);
        });
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });

    /* Inject toggle button */
    const btn = document.createElement('button');
    btn.id = 'theme-toggle';
    btn.title = '切换亮色/暗色';
    btn.textContent = saved === 'light' ? '🌙' : '☀️';
    btn.addEventListener('click', function () {
      const next = document.documentElement.classList.contains('light') ? 'dark' : 'light';
      localStorage.setItem(KEY, next);
      apply(next);
    });
    document.body.appendChild(btn);
  });
})();
