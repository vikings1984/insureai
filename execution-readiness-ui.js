(function () {
  const url = 'execution_readiness.json';
  fetch(url).then(r => r.ok ? r.json() : null).then(data => {
    if (!data || !Array.isArray(data.results) || !data.results.length) return;
    const host = document.createElement('section');
    host.className = 'execution-readiness';
    host.innerHTML = '<h2>决策准备度</h2><p>可交付给负责人复核，但不会自动执行。</p>';
    data.results.slice(0, 8).forEach(row => {
      const card = document.createElement('article');
      card.innerHTML = '<strong>' + (row.action_label || row.action_id) + '</strong>' +
        '<div>负责人：' + (row.owner_roles || []).join('、') + '</div>' +
        '<div>所需输入：' + (row.required_inputs || []).join('、') + '</div>' +
        '<div>截止：' + (row.deadline || '待定') + ' · 成本：' + (row.cost_class || 'unknown') + '</div>' +
        '<div>状态：待人工确认</div>';
      host.appendChild(card);
    });
    document.body.appendChild(host);
  }).catch(() => {});
})();
