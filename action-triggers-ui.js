(function () {
  const output = document.createElement('section');
  output.id = 'insureai-action-triggers';
  output.style.margin = '24px 0';
  output.innerHTML = '<h2>行动触发器</h2><p>仅用于观察与复核，不自动执行业务动作。</p><div data-triggers>加载中…</div>';
  const mount = document.querySelector('main') || document.body;
  mount.prepend(output);

  fetch('action_triggers.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error('trigger data unavailable')))
    .then(data => {
      const rows = Array.isArray(data.results) ? data.results.slice(0, 8) : [];
      const box = output.querySelector('[data-triggers]');
      if (!rows.length) {
        box.textContent = '当前没有跨情景稳健行动需要设置触发器。';
        return;
      }
      box.innerHTML = rows.map(row => {
        const t = row.trigger || {};
        return '<article style="padding:12px 0;border-bottom:1px solid #ddd">' +
          '<strong>' + escapeHtml(row.action_label || row.action_id) + '</strong>' +
          '<div>状态：' + escapeHtml(row.status || 'monitor') + ' · 适用情景：' + escapeHtml((row.scenarios || []).join(' / ')) + '</div>' +
          '<div>升级：' + escapeHtml(t.escalate || '') + '</div>' +
          '<div>降级：' + escapeHtml(t.deescalate || '') + '</div>' +
          '<div>停止：' + escapeHtml(t.stop || '') + '</div>' +
          '<div>责任角色：' + escapeHtml((row.owner_roles || []).join(' / ')) + '</div>' +
          '</article>';
      }).join('');
    })
    .catch(() => {
      output.querySelector('[data-triggers]').textContent = '行动触发器暂时不可用。';
    });

  function escapeHtml(value) {
    return String(value).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  }
})();
