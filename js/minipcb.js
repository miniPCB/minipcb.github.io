/* miniPCB global UI helpers: tabs + lightbox */
(function () {
  // --- Tabs ---
  function showTab(id, btn) {
    var panes = document.querySelectorAll('.tab-content');
    var tabs  = document.querySelectorAll('.tabs .tab');

    panes.forEach(function (el) {
      if (el.getAttribute('data-hidden') === 'true') return;
      var isActive = el.id === id;
      el.classList.toggle('active', isActive);
      el.setAttribute('aria-hidden', isActive ? 'false' : 'true');
    });

    tabs.forEach(function (el) { el.classList.remove('active'); });

    // Prefer passed-in button; otherwise try to find a matching tab by data attribute
    if (btn) {
      btn.classList.add('active');
    } else {
      var auto = document.querySelector('.tabs .tab[data-tab="' + id + '"]');
      if (auto) auto.classList.add('active');
    }
  }

  function initTabs() {
    // Event delegation for buttons using data-tab (recommended)
    var tabsContainer = document.querySelector('.tabs');
    if (tabsContainer) {
      tabsContainer.addEventListener('click', function (e) {
        var t = e.target.closest('.tab');
        if (!t) return;
        var targetId = t.getAttribute('data-tab');
        if (targetId) {
          e.preventDefault();
          showTab(targetId, t);
          // update URL hash (optional)
          if (history && history.replaceState) {
            history.replaceState(null, '', '#' + targetId);
          } else {
            location.hash = targetId;
          }
        }
      });
    }

    // On load: if URL hash matches a pane, open it; else keep any .tab.active/.tab-content.active
    var hash = (location.hash || '').replace('#', '');
    var hashPane = hash ? document.getElementById(hash) : null;
    if (hashPane && hashPane.getAttribute('data-hidden') !== 'true') {
      showTab(hash);
      return;
    }
    var currentActive = document.querySelector('.tab-content.active');
    if (currentActive && currentActive.getAttribute('data-hidden') !== 'true') {
      showTab(currentActive.id);
      return;
    }
    // Fallback: first tab/pane
    var firstPane = document.querySelector('.tab-content:not([data-hidden="true"])');
    if (firstPane) showTab(firstPane.id);
  }

  // --- Lightbox ---
  var lb, lbImg;

  function openLightbox(imgEl) {
    if (!lb || !lbImg || !imgEl) return;
    var src = (imgEl.dataset && imgEl.dataset.full) ? imgEl.dataset.full : imgEl.src;
    lbImg.src = src;
    lb.classList.add('open');
    lb.setAttribute('aria-hidden', 'false');
    document.body.classList.add('no-scroll');
  }

  function closeLightbox() {
    if (!lb || !lbImg) return;
    lb.classList.remove('open');
    lb.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('no-scroll');
    setTimeout(function () { lbImg.src = ''; }, 150);
  }

  function initLightbox() {
    lb    = document.getElementById('lightbox');
    lbImg = document.getElementById('lightbox-img');

    if (!lb || !lbImg) return;

    // Click to close (backdrop only)
    lb.addEventListener('click', function (e) {
      if (e.target === lb) closeLightbox();
    });

    // Esc to close
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && lb.classList.contains('open')) closeLightbox();
    });

    // Make any .zoomable image open the lightbox
    document.querySelectorAll('img.zoomable').forEach(function (img) {
      img.style.cursor = img.style.cursor || 'zoom-in';
      img.addEventListener('click', function () { openLightbox(img); });
    });
  }

  // Expose functions for pages that still use inline onclick handlers
  window.showTab = showTab;
  window.openLightbox = openLightbox;
  window.closeLightbox = closeLightbox;

  // Init on DOM ready
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initLightbox();
  });
})();
