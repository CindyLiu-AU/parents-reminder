(function () {
  const KEY = 'color-theme';
  let btn = null;

  function apply(mode) {
    document.documentElement.classList.toggle('light', mode === 'light');
    const icon = mode === 'light' ? '🌙' : '☀️';
    if (btn) btn.textContent = icon;
    document.querySelectorAll('.secondary-theme-toggle').forEach(b => b.textContent = icon);
  }

  window.toggleColorTheme = function () {
    const next = document.documentElement.classList.contains('light') ? 'dark' : 'light';
    localStorage.setItem(KEY, next);
    apply(next);
  };

  /* Apply before first paint to avoid flash */
  const saved = localStorage.getItem(KEY) || 'dark';
  if (saved === 'light') document.documentElement.classList.add('light');

  document.addEventListener('DOMContentLoaded', function () {
    btn = document.createElement('button');
    btn.id = 'theme-toggle';
    btn.title = '切换亮色/暗色';
    btn.textContent = saved === 'light' ? '🌙' : '☀️';
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      window.toggleColorTheme();
    });
    document.body.appendChild(btn);

    /* Initialise any secondary toggle buttons already in the DOM */
    const icon = saved === 'light' ? '🌙' : '☀️';
    document.querySelectorAll('.secondary-theme-toggle').forEach(b => b.textContent = icon);
  });
})();
