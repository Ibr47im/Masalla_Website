// ============================================================
// main.js — Masalla Website JavaScript
// ============================================================

// ── Smooth Wheel Scroll (lerp-based) ──────────────────────────
(function () {
  let scrollCurrent = 0;
  let scrollTarget  = 0;
  let loopRunning   = false;
  const EASE = 0.08; // lower = slower / silkier

  function maxScroll() {
    return document.documentElement.scrollHeight - window.innerHeight;
  }

  function normalizeDelta(e) {
    let d = e.deltaY;
    if (e.deltaMode === 1) d *= 40;               // line mode (some browsers)
    if (e.deltaMode === 2) d *= window.innerHeight; // page mode
    return d;
  }

  function tick() {
    loopRunning = true;
    scrollCurrent += (scrollTarget - scrollCurrent) * EASE;
    window.scrollTo(0, scrollCurrent);
    if (Math.abs(scrollTarget - scrollCurrent) > 0.5) {
      requestAnimationFrame(tick);
    } else {
      scrollCurrent = scrollTarget;
      window.scrollTo(0, scrollTarget);
      loopRunning = false;
    }
  }

  window.addEventListener('wheel', (e) => {
    e.preventDefault();
    // Don't scroll while mobile nav is open
    if (document.body.classList.contains('nav-open')) return;
    // Re-sync if page was scrolled externally (anchor links, keyboard, etc.)
    if (Math.abs(scrollCurrent - window.scrollY) > 50) {
      scrollCurrent = scrollTarget = window.scrollY;
    }
    scrollTarget = Math.max(0, Math.min(
      scrollTarget + normalizeDelta(e),
      maxScroll()
    ));
    if (!loopRunning) tick();
  }, { passive: false });

  window.addEventListener('load', () => {
    scrollCurrent = scrollTarget = window.scrollY;
  });
}());

// ── Navbar: add frosted-glass effect on scroll ──────────────
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 60);
});

// ── Scroll Reveal: fade elements in as they enter viewport ──
const reveals = document.querySelectorAll('.reveal');

const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry, i) => {
    if (entry.isIntersecting) {
      // Stagger sibling reveals by 80ms each
      setTimeout(() => {
        entry.target.classList.add('visible');
      }, i * 80);
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

reveals.forEach(el => revealObserver.observe(el));

// ── Mobile hamburger nav ─────────────────────────────────────
const burger       = document.getElementById('nav-burger');
const mobileNav    = document.getElementById('mobile-nav');
const mobileClose  = document.getElementById('mobile-nav-close');

if (burger && mobileNav) {
  function closeNav() {
    burger.classList.remove('is-open');
    mobileNav.classList.remove('is-open');
    burger.setAttribute('aria-expanded', 'false');
    mobileNav.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nav-open');
    document.body.style.overflow = '';
  }

  // Burger toggle
  burger.addEventListener('click', () => {
    const isOpen = burger.classList.toggle('is-open');
    mobileNav.classList.toggle('is-open');
    burger.setAttribute('aria-expanded', isOpen);
    mobileNav.setAttribute('aria-hidden', !isOpen);
    document.body.classList.toggle('nav-open', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  // X close button
  if (mobileClose) mobileClose.addEventListener('click', closeNav);

  // Tap the dark backdrop (anywhere outside the content)
  mobileNav.addEventListener('click', (e) => {
    if (e.target === mobileNav) closeNav();
  });

  // Close on any nav link click
  mobileNav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', closeNav);
  });
}
