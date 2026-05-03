(function () {
  const PAGES = [
    { id: 'home',       href: 'index.html',      icon: '🏠', label: '首页' },
    { id: 'reminders',  href: 'reminders.html',  icon: '📋', label: '提醒' },
    { id: 'spending',   href: 'spending.html',   icon: '🎁', label: '花费' },
    { id: 'apps',       href: 'apps.html',       icon: '📱', label: '应用' },
    { id: 'flashcards', href: 'flashcards.html', icon: '📖', label: '单词' },
  ];

  document.addEventListener('DOMContentLoaded', function () {
    const nav = document.createElement('nav');
    nav.className = 'bottom-nav';
    nav.innerHTML = PAGES.map(p => `
      <a href="${p.href}" class="bottom-nav-item${window.NAV_ACTIVE === p.id ? ' active' : ''}">
        <span class="bnav-icon">${p.icon}</span>
        <span class="bnav-label">${p.label}</span>
      </a>`).join('');
    document.body.appendChild(nav);
  });
})();
