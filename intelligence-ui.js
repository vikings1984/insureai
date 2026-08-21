/* InsureAI Intelligence UI: Daily Brief + Entity Radar + Topic Trends. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const safeUrl = (u) => /^https?:\/\//i.test(u || '') ? u : '#';
  const directionLabel = { rising: '↑ 上升', stable: '→ 稳定', falling: '↓ 回落' };
  const directionClass = { rising: 'rising', stable: 'stable', falling: 'falling' };

  function renderDaily(items, stats) {
    return '<section id="daily-intelligence" aria-label="今日保险情报">' +
      '<div class="di-head"><div><div class="di-kicker">INSUREAI INTELLIGENCE</div><h2>今日保险情报</h2><p>不追求更多新闻，只突出值得关注的行业变化。</p></div><div class="di-stats">' + esc(stats?.event_count || 0) + ' 个事件</div></div>' +
      '<div class="di-list">' + items.map((e, i) => {
        const s = e.scores || {}, x = e.insight || {};
        const evidence = Array.isArray(x.evidence) && x.evidence.length ? x.evidence[0] : null;
        return '<article class="di-item"><div class="di-rank">0' + (i + 1) + '</div><div class="di-body"><div class="di-meta">' + esc(e.topic_label || '保险行业') + ' · ' + esc(e.event_type || 'industry_update') + ' · 情报分 ' + esc(s.intelligence_score || 0) + ' · 置信度 ' + esc(s.confidence || 0) + '%</div><h3>' + esc(e.title) + '</h3><div class="di-grid"><div><b>发生了什么</b><p>' + esc(x.what_happened || e.title) + '</p></div><div><b>为什么重要</b><p>' + esc(x.why_it_matters || '') + '</p></div><div><b>影响谁</b><p>' + esc(x.who_is_affected || '') + '</p></div><div><b>接下来关注</b><p>' + esc(x.what_to_watch || '') + '</p></div></div>' + (Array.isArray(e.entities) && e.entities.length ? '<div class="di-entities">' + e.entities.slice(0, 5).map(v => '<span>' + esc(v) + '</span>').join('') + '</div>' : '') + (evidence && safeUrl(evidence.source_url) !== '#' ? '<a class="di-source" target="_blank" rel="noopener noreferrer" href="' + esc(safeUrl(evidence.source_url)) + '">证据：' + esc(evidence.source_name || '原文') + ' ↗</a>' : '') + '</div></article>';
      }).join('') + '</div></section>';
  }

  function renderRadar(radar) {
    if (!radar) return '';
    const entities = Array.isArray(radar.entity_radar) ? radar.entity_radar.slice(0, 6) : [];
    const trends = Array.isArray(radar.topic_trends) ? radar.topic_trends.slice(0, 6) : [];
    if (!entities.length && !trends.length) return '';
    return '<section id="insureai-radar" aria-label="保险行业雷达">' +
      '<div class="radar-head"><div><div class="di-kicker">INSUREAI RADAR</div><h2>行业雷达</h2><p>监测谁正在发生变化，以及哪些主题正在形成趋势。信号不足时不会强行下结论。</p></div><div class="di-stats">' + esc(radar.stats?.trending_topics || 0) + ' 个上升主题</div></div>' +
      '<div class="radar-grid">' +
      '<div class="radar-panel"><h3>公司 / 实体</h3><div class="radar-entity-list">' + entities.map((x, i) => '<div class="radar-entity"><div class="radar-rank">' + (i + 1) + '</div><div class="radar-main"><strong>' + esc(x.display_name) + '</strong><span>' + esc(x.event_count_7d) + ' 事件 / 7天 · 活跃度 ' + esc(x.weighted_activity) + '</span><small>' + esc((x.top_topics || []).join(' · ')) + '</small></div><div class="radar-confidence">' + esc(x.confidence || 'low') + '</div></div>').join('') + '</div></div>' +
      '<div class="radar-panel"><h3>主题趋势</h3><div class="radar-trend-list">' + trends.map(x => '<div class="radar-trend"><div><strong>' + esc(x.topic_label) + '</strong><span>' + esc(x.current_7d_events) + ' vs ' + esc(x.previous_7d_events) + ' 事件</span></div><div class="trend-' + esc(directionClass[x.direction] || 'stable') + '">' + esc(directionLabel[x.direction] || '→ 稳定') + '</div></div>').join('') + '</div></div>' +
      '</div></section>';
  }

  async function boot() {
    try {
      const res = await fetch('intelligence.json?t=' + Date.now());
      if (!res.ok) return;
      const data = await res.json();
      const items = Array.isArray(data.daily_brief) ? data.daily_brief.slice(0, 5) : [];
      if (!items.length || document.getElementById('daily-intelligence')) return;
      const wrapper = document.createElement('div');
      wrapper.innerHTML = renderDaily(items, data.stats) + renderRadar(data.radar);
      const style = document.createElement('style');
      style.textContent = '#daily-intelligence,#insureai-radar{margin:18px auto 24px;max-width:1180px;padding:22px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:linear-gradient(135deg,rgba(245,249,252,.98),rgba(255,255,255,.98));box-shadow:0 8px 30px rgba(20,40,60,.06)}#daily-intelligence .di-head,#insureai-radar .radar-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:16px}#daily-intelligence h2,#insureai-radar h2{margin:2px 0 4px;font-size:24px}#daily-intelligence .di-head p,#insureai-radar .radar-head p{margin:0;color:#64748b;font-size:13px}.di-kicker{font-size:10px;letter-spacing:.14em;font-weight:700;color:#64748b}.di-stats{font-size:12px;color:#475569;padding:7px 10px;border:1px solid #dbe3ea;border-radius:999px;background:#fff}.di-list{display:grid;gap:10px}.di-item{display:flex;gap:14px;padding:14px 0;border-top:1px solid #e6edf2}.di-rank{font-size:13px;font-weight:800;color:#94a3b8;min-width:24px}.di-body{min-width:0;flex:1}.di-meta{font-size:11px;color:#64748b;margin-bottom:3px}.di-body h3{font-size:16px;margin:0 0 10px;line-height:1.45}.di-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}.di-grid b{font-size:11px;color:#475569}.di-grid p{font-size:12px;line-height:1.55;color:#334155;margin:3px 0}.di-source{display:inline-block;margin-top:8px;font-size:11px;color:#2563eb;text-decoration:none}.di-entities{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.di-entities span{font-size:10px;padding:4px 7px;border-radius:999px;background:#f1f5f9;color:#475569}.radar-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.radar-panel{border-top:1px solid #e6edf2;padding-top:10px}.radar-panel h3{font-size:13px;margin:0 0 10px}.radar-entity-list,.radar-trend-list{display:grid;gap:8px}.radar-entity,.radar-trend{display:flex;align-items:center;gap:10px;padding:8px 0}.radar-rank{width:20px;font-size:11px;color:#94a3b8;font-weight:700}.radar-main{flex:1;min-width:0;display:grid;gap:2px}.radar-main strong,.radar-trend strong{font-size:13px}.radar-main span,.radar-main small,.radar-trend span{font-size:10px;color:#64748b}.radar-confidence{font-size:9px;color:#64748b;text-transform:uppercase}.radar-trend{justify-content:space-between;border-bottom:1px solid #f0f3f5}.trend-rising{font-size:11px;font-weight:700}.trend-stable{font-size:11px;color:#64748b}.trend-falling{font-size:11px;color:#94a3b8}@media(max-width:700px){#daily-intelligence,#insureai-radar{margin:12px 10px;padding:16px}.di-grid,.radar-grid{grid-template-columns:1fr}#daily-intelligence h2,#insureai-radar h2{font-size:20px}}';
      document.head.appendChild(style);
      const host = document.querySelector('.app-layout') || document.querySelector('main') || document.body.firstElementChild;
      if (host && host.parentNode) {
        host.parentNode.insertBefore(wrapper, host);
      }
    } catch (e) { console.warn('Daily Intelligence unavailable:', e); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
