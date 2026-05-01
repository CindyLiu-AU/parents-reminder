(function () {
  const KEY = 'color-theme';

  function apply(mode) {
    document.documentElement.classList.toggle('light', mode === 'light');
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = mode === 'light' ? '🌙' : '☀️';
  }

  // Apply before first paint to avoid flash of wrong theme
  const saved = localStorage.getItem(KEY) || 'dark';
  if (saved === 'light') document.documentElement.classList.add('light');

  document.addEventListener('DOMContentLoaded', function () {
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
