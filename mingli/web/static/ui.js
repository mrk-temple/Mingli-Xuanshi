/* 渐进增强：不用 JavaScript 时，所有体系与原生折叠入口仍可用。 */
(function () {
  'use strict';
  var filters = document.querySelector('.system-filters');
  if (filters) {
    var buttons = filters.querySelectorAll('[data-system-filter]');
    var cards = document.querySelectorAll('[data-system-family]');
    var status = document.querySelector('.filter-status');
    filters.hidden = false;
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var family = button.dataset.systemFilter, count = 0;
        buttons.forEach(function (item) { item.setAttribute('aria-pressed', String(item === button)); });
        cards.forEach(function (card) {
          card.hidden = family !== 'all' && card.dataset.systemFamily !== family;
          if (!card.hidden) count++;
        });
        status.textContent = '已展示 ' + count + ' 种观察方式';
      });
    });
  }
  var menus = document.querySelectorAll('.report-tools');
  document.addEventListener('click', function (event) {
    menus.forEach(function (menu) { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    menus.forEach(function (menu) {
      if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
    });
  });
})();


/* Shared form feedback: native validation first, then one in-flight submission. */
(function () {
  'use strict';
  var pending = new Map();
  document.querySelectorAll('a.nav-link.on,.nav-sub a.cur,.bottom-nav a.on').forEach(function (link) { link.setAttribute('aria-current','page'); });
  document.querySelectorAll('form[data-pending-message]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (form.dataset.pending === 'true') { event.preventDefault(); return; }
      form.dataset.pending = 'true'; form.setAttribute('aria-busy','true');
      var buttons = Array.from(form.querySelectorAll('button[type="submit"],input[type="submit"]'));
      pending.set(form, buttons.map(function (button) { return {button:button,html:button.innerHTML,disabled:button.disabled}; }));
      buttons.forEach(function (button) { button.disabled = true; if (button.tagName === 'BUTTON') button.textContent = '正在处理…'; });
      var status = form.querySelector('.submit-status');
      if (!status) { status=document.createElement('p');status.className='submit-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');form.appendChild(status); }
      status.textContent=form.dataset.pendingMessage;
    });
  });
  window.addEventListener('pageshow',function () {
    pending.forEach(function (buttons,form) { delete form.dataset.pending;form.removeAttribute('aria-busy');buttons.forEach(function (item) {item.button.innerHTML=item.html;item.button.disabled=item.disabled;});var status=form.querySelector('.submit-status');if(status)status.textContent=''; });
    pending.clear();
  });
})();
