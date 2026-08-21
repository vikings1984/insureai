(function () {
  const escapeHtml = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  fetch('owner_risk_view.json').then(r => r.ok ? r.json() : null).then(data => {
    if (!data) return;
    const host = document.createElement('section');
    host.className = 'owner-risk-view';
    const credibility = data.credibility || {};
    const reasons = Array.isArray(credibility.reasons) ? credibility.reasons.join('、') : '未提供';
    host.innerHTML = '<h2>负责人风险视图</h2>' +
      '<p>只读展示：负责人、截止时间和下一步均需人工确认；不会自动执行行动。</p>' +
      '<div><strong>整体可信度：</strong>' + escapeHtml(credibility.status || 'unknown') + '</div>' +
      '<div><strong>可信度原因：</strong>' + escapeHtml(reasons) + '</div>';

    data.items.slice(0, 12).forEach(item => {
      const card = document.createElement('article');
      const owners = Array.isArray(item.owners) ? item.owners.join('、') : '';
      const itemReasons = Array.isArray(item.reasons) ? item.reasons.join('、') : '';
      card.innerHTML = '<strong>' + escapeHtml(item.title || item.event_id) + '</strong>' +
        '<div>负责人：' + escapeHtml(owners) + '</div>' +
        '<div>截止：' + escapeHtml(item.deadline || '待定') + '</div>' +
        '<div>下一步：' + escapeHtml(item.next_step || '人工确认') + '</div>' +
        '<div>原因：' + escapeHtml(itemReasons || '未提供') + '</div>' +
        '<div>边界：' + escapeHtml(item.approval_boundary || 'human confirmation required') + '</div>' +
        '<div>模式：仅建议，不自动执行</div>';
      host.appendChild(card);
    });
    document.body.appendChild(host);
  }).catch(() => {});
})();
