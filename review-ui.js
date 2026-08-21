(function () {
  'use strict';
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>\"']/g, function (ch) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[ch]);
    });
  }
  function render(queue) {
    if (!queue || !Array.isArray(queue.items) || !queue.items.length) return;
    var root = document.createElement('section');
    root.className = 'intel-review-queue';
    root.innerHTML = '<div class="intel-review-head"><strong>人工复核队列</strong><span>高风险样本优先，不自动修改结论</span></div>' +
      '<div class="intel-review-list">' + queue.items.slice(0, 8).map(function (item) {
        var reasons = (item.reasons || []).map(function (r) { return '<span class="intel-review-reason">' + esc(r.type) + '</span>'; }).join('');
        return '<article class="intel-review-item"><div><b>' + esc(item.title) + '</b><div class="intel-review-meta">优先级 ' + esc(item.priority) + ' · ' + esc(item.trust_level) + ' trust · 情报分 ' + esc(item.intelligence_score) + '</div></div><div>' + reasons + '</div></article>';
      }).join('') + '</div>';
    var anchor = document.querySelector('main') || document.body;
    anchor.prepend(root);
  }
  fetch('review_queue.json', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(render)
    .catch(function () {});
})();
