/* 命理玄师 · 首页动效层（原生 JS，零依赖）
   星尘背景 / 渐进入场 / 3D 倾斜 / 涟漪扩散 —— prefers-reduced-motion 时全部静默 */
(function () {
  'use strict';

  var root = document.documentElement;
  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── 1. 渐进入场：.reveal 元素按 --ri 序号错峰浮现（间隔 150ms）── */
  function stageReveal() {
    var nodes = document.querySelectorAll('.reveal');
    if (reduceMotion || !('IntersectionObserver' in window)) {
      nodes.forEach(function (n) { n.classList.add('in'); });
      return;
    }
    var seen = new WeakSet();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting || seen.has(e.target)) return;
        seen.add(e.target);
        var el = e.target;
        var ri = parseInt(el.style.getPropertyValue('--ri') || '0', 10);
        setTimeout(function () { el.classList.add('in'); }, ri * 150);
        io.unobserve(el);
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    nodes.forEach(function (n) { io.observe(n); });
  }

  /* ── 2. 动态星尘：缓慢漂移 + 明暗呼吸的粒子（模拟天象流转）── */
  function starfield() {
    var canvas = document.getElementById('starfield');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = 0, h = 0, stars = [];

    function seed() {
      stars = [];
      var count = Math.max(36, Math.min(150, Math.round(w * h / 9000)));
      for (var i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: Math.random() * 1.3 + 0.3,
          vx: (Math.random() - 0.5) * 0.12,   /* 缓慢漂移 */
          vy: (Math.random() - 0.5) * 0.07,
          tw: Math.random() * Math.PI * 2,    /* 闪烁相位 */
          ts: 0.004 + Math.random() * 0.011,
          warm: Math.random() < 0.08          /* 少量朱砂色星 */
        });
      }
    }

    function resize() {
      var rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function palette() {
      var dark = root.getAttribute('data-theme') === 'dark';
      return dark
        ? { base: '211, 178, 124', warm: '217, 124, 99', alpha: 0.55 }
        : { base: '126, 98, 53', warm: '163, 62, 40', alpha: 0.30 };
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      var c = palette();
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        s.x += s.vx; s.y += s.vy;
        if (s.x < -4) s.x = w + 4; else if (s.x > w + 4) s.x = -4;
        if (s.y < -4) s.y = h + 4; else if (s.y > h + 4) s.y = -4;
        s.tw += s.ts;
        var a = c.alpha * (0.5 + 0.5 * Math.sin(s.tw));
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + (s.warm ? c.warm : c.base) + ', ' + a.toFixed(3) + ')';
        ctx.fill();
      }
    }

    var timer = null;
    function onResize() {
      clearTimeout(timer);
      timer = setTimeout(resize, 160);
    }

    resize();
    if (reduceMotion) { draw(); return; }   /* 静态一帧，不做动画 */
    window.addEventListener('resize', onResize);
    (function loop() { draw(); requestAnimationFrame(loop); })();
  }

  /* ── 3. 3D 悬停倾斜：沿 X/Y 轴随鼠标偏转，附带光泽跟随 ── */
  function tilt() {
    if (reduceMotion) return;
    if (window.matchMedia && window.matchMedia('(hover: none)').matches) return;
    document.querySelectorAll('.tilt').forEach(function (card) {
      var raf = null;
      card.addEventListener('pointermove', function (e) {
        var rect = card.getBoundingClientRect();
        var px = (e.clientX - rect.left) / rect.width - 0.5;
        var py = (e.clientY - rect.top) / rect.height - 0.5;
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(function () {
          card.style.setProperty('--rx', (-py * 3.2).toFixed(2) + 'deg');
          card.style.setProperty('--ry', (px * 4.6).toFixed(2) + 'deg');
          card.style.setProperty('--mx', ((px + 0.5) * 100).toFixed(1) + '%');
          card.style.setProperty('--my', ((py + 0.5) * 100).toFixed(1) + '%');
        });
      });
      card.addEventListener('pointerleave', function () {
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
      });
    });
  }

  /* ── 4. 沉浸式入口：点击主按钮 → 全屏涟漪扩散 → 再行跳转 ── */
  function orbRipple() {
    var orb = document.querySelector('.ask-orb');
    if (!orb || reduceMotion) return;
    orb.addEventListener('click', function (e) {
      if (e.detail === 0) return;            /* 键盘激活：直接跳转 */
      e.preventDefault();
      var el = document.createElement('span');
      el.className = 'orb-ripple';
      el.style.left = e.clientX + 'px';
      el.style.top = e.clientY + 'px';
      document.body.appendChild(el);
      el.addEventListener('animationend', function () { el.remove(); });
      setTimeout(function () { window.location.href = orb.href; }, 460);
    });
  }

  /* ── 启动 ── */
  function init() {
    try { stageReveal(); } catch (e) {}
    try { starfield(); } catch (e) {}
    try { tilt(); } catch (e) {}
    try { orbRipple(); } catch (e) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
