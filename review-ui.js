/* Human Review 队列 + E3 反馈采集 / 跟踪书签。
   静态站点无后端：采集结果先落 localStorage，再经「导出 JSON / 提交 GitHub Issue」两个出口
   交由 p2_import_feedback.py 校验后写入 p2_state.json（人工桥梁，不伪造用户偏好）。 */
(function () {
  'use strict';
  var KEY = 'insureai_review_feedback_v1';
  var LABELS = [
    ['useful', '有用'], ['important', '重要'], ['noise', '噪声'],
    ['irrelevant', '不相关'], ['incorrect', '有误'], ['acted_on', '已处理']
  ];
  var STATUSES = [['active', '跟踪中'], ['resolved', '已闭环'], ['snoozed', '已搁置']];

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]);
    });
  }
  function meta(name, fallback) {
    var el = document.querySelector('meta[name="' + name + '"]');
    return (el && el.content) ? el.content : fallback;
  }
  function pageLimit() {
    var n = parseInt(meta('review-limit', '8'), 10);
    return (isNaN(n) || n <= 0) ? 8 : n;
  }
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || { version: 1, feedback: [], monitoring: [] }; }
    catch (e) { return { version: 1, feedback: [], monitoring: [] }; }
  }
  function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  function isoNow() { return new Date().toISOString(); }

  function fbKey(r) { return r.event_id + '|' + r.label; }
  function monKey(r) { return r.watchlist_id + '|' + r.event_id; }

  function toggleFeedback(s, eventId, label) {
    var k = eventId + '|' + label;
    var hit = s.feedback.filter(function (r) { return fbKey(r) === k; })[0];
    if (hit) {
      s.feedback = s.feedback.filter(function (r) { return fbKey(r) !== k; });
    } else {
      s.feedback.push({
        event_id: eventId, label: label, note: '', importance: null,
        confidence: null, outcome: null, user_id: null, created_at: isoNow()
      });
    }
    save(s);
    return !hit;
  }

  function setMonitor(s, eventId, watchlistId, status) {
    if (!watchlistId) return null;
    var k = watchlistId + '|' + eventId;
    var hit = s.monitoring.filter(function (r) { return monKey(r) === k; })[0];
    if (hit && hit.status === status) {
      s.monitoring = s.monitoring.filter(function (r) { return monKey(r) !== k; });
      save(s);
      return false;
    }
    s.monitoring = s.monitoring.filter(function (r) { return monKey(r) !== k; });
    s.monitoring.push({
      watchlist_id: watchlistId, event_id: eventId, status: status, updated_at: isoNow()
    });
    save(s);
    return true;
  }

  function hasFeedback(s, eventId, label) {
    var k = eventId + '|' + label;
    return s.feedback.some(function (r) { return fbKey(r) === k; });
  }
  function monitorOf(s, eventId, watchlistId) {
    var k = watchlistId + '|' + eventId;
    return s.monitoring.filter(function (r) { return monKey(r) === k; })[0] || null;
  }

  function exportJson(s) {
    return JSON.stringify({
      version: 'p2-export-v1',
      generated_at: isoNow(),
      feedback: s.feedback,
      monitoring: s.monitoring
    }, null, 2);
  }

  function download(name, text) {
    var blob = new Blob([text], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function submitIssue(s) {
    var payload = { feedback: s.feedback, monitoring: s.monitoring };
    var title = encodeURIComponent('复核反馈: ' + s.feedback.length + ' 条标签 / ' + s.monitoring.length + ' 条跟踪');
    var body = encodeURIComponent(
      '## Human Review 反馈导出\n\n' +
      '- **标签数**: ' + s.feedback.length + '\n' +
      '- **跟踪数**: ' + s.monitoring.length + '\n' +
      '- **导出时间**: ' + isoNow() + '\n\n' +
      '## 机器可解析负载（供 `python3 p2_import_feedback.py` 导入）\n\n' +
      '```json\n' + JSON.stringify(payload, null, 2) + '\n```\n\n' +
      '---\n*此 Issue 由 InsureAI Human Review 自动生成*'
    );
    var ghRepo = meta('github-repo', 'vikings1984/insureai');
    window.open('https://github.com/' + String(ghRepo).trim() + '/issues/new?title=' + title + '&body=' + body + '&labels=复核反馈', '_blank');
  }

  function render(queue, state, s) {
    var mount = document.getElementById('rv-mount');
    if (!queue || !Array.isArray(queue.items) || !queue.items.length) {
      if (mount) mount.innerHTML = '<div class="rv-empty">暂无复核队列数据：<code>review_queue.json</code> 缺失或为空。请先运行智能化流水线。</div>';
      return;
    }
    var watchlists = (state && Array.isArray(state.watchlists)) ? state.watchlists : [];
    var defaultWl = watchlists.length ? watchlists[0].id : '';
    var cap = pageLimit();
    var shown = queue.items.slice(0, cap);
    var root = document.createElement('section');
    root.className = 'intel-review-queue';

    root.innerHTML =
      '<div class="intel-review-head"><strong>人工复核队列</strong>' +
      '<span>高风险样本优先，不自动修改结论 · 共 ' + queue.items.length + ' 条，本页展示 ' + shown.length + ' 条</span></div>' +
      '<div class="rv-tools">' +
      '<span class="rv-pending">本机待入库：<b id="rv-fb-count">0</b> 标签 · <b id="rv-mon-count">0</b> 跟踪</span>' +
      '<button type="button" id="rv-export">导出 JSON</button>' +
      '<button type="button" id="rv-issue">提交 GitHub Issue</button>' +
      '<button type="button" id="rv-clear">清空本机</button>' +
      '</div>' +
      '<p class="rv-hint">标签与跟踪先存本机；点「导出 JSON」后用 <code>python3 p2_import_feedback.py 文件名</code> 校验入库到 <code>p2_state.json</code>。已入库记录显示为「已同步」。</p>' +
      '<div class="intel-review-list">' + shown.map(function (item) {
        var reasons = (item.reasons || []).map(function (r) {
          return '<span class="intel-review-reason">' + esc(r.type) + '</span>';
        }).join('');
        var eid = item.event_id || '';
        var labelBtns = LABELS.map(function (l) {
          var local = hasFeedback(s, eid, l[0]);
          var synced = (state.feedback || []).some(function (r) {
            return r.event_id === eid && r.label === l[0];
          });
          var cls = 'rv-label' + (local ? ' on' : '') + (synced && !local ? ' synced' : '');
          var tip = synced && !local ? '（已同步入库）' : '';
          return '<button type="button" class="' + cls + '" data-label="' + l[0] +
            '" data-event="' + esc(eid) + '" title="' + esc(l[1] + tip) + '">' + esc(l[1]) + '</button>';
        }).join('');
        var wlOptions = watchlists.map(function (w) {
          return '<option value="' + esc(w.id) + '">' + esc(w.name || w.id) + '</option>';
        }).join('');
        var stOptions = STATUSES.map(function (st) {
          return '<option value="' + st[0] + '">' + esc(st[1]) + '</option>';
        }).join('');
        var tracked = monitorOf(s, eid, defaultWl);
        return '<article class="intel-review-item" data-event="' + esc(eid) + '">' +
          '<div><b>' + esc(item.title) + '</b>' +
          '<div class="intel-review-meta">优先级 ' + esc(item.priority) + ' · ' +
          esc(item.trust_level) + ' trust · 情报分 ' + esc(item.intelligence_score) + '</div></div>' +
          '<div>' + reasons + '</div>' +
          '<div class="rv-actions">' + labelBtns + '</div>' +
          (watchlists.length
            ? '<div class="rv-track"><span>跟踪</span><select class="rv-wl">' + wlOptions + '</select>' +
              '<select class="rv-st">' + stOptions + '</select>' +
              '<button type="button" class="rv-track-btn' + (tracked ? ' on' : '') +
              '" data-event="' + esc(eid) + '">' + (tracked ? '取消跟踪' : '加入跟踪') + '</button></div>'
            : '') +
          '</article>';
      }).join('') + '</div>';

    var style = document.createElement('style');
    style.textContent =
      '.intel-review-queue{margin:18px auto;max-width:1180px;padding:20px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:#fff;box-shadow:0 8px 30px rgba(20,40,60,.05)}' +
      '.intel-review-head{display:flex;justify-content:space-between;align-items:baseline}.intel-review-head span{font-size:11px;color:#94a3b8}' +
      '.rv-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0 6px}.rv-pending{font-size:11px;color:#64748b;margin-right:auto}' +
      '.rv-tools button{font-size:11px;border:1px solid #dbe3ea;background:#f8fafc;border-radius:8px;padding:6px 10px;cursor:pointer}' +
      '.rv-tools button:hover{background:#eef2f7}' +
      '.rv-hint{font-size:11px;color:#64748b;background:#f8fafc;border-left:3px solid #cbd5e1;padding:8px 10px;border-radius:0 8px 8px 0}code{font-size:11px;background:#eef2f7;padding:1px 4px;border-radius:4px}' +
      '.intel-review-item{display:grid;gap:8px;padding:12px 0;border-top:1px solid #eef2f5}' +
      '.rv-actions{display:flex;gap:6px;flex-wrap:wrap}' +
      '.rv-label{font-size:11px;border:1px solid #e2e8f0;background:#f8fafc;border-radius:999px;padding:4px 9px;cursor:pointer}' +
      '.rv-label:hover{border-color:#94a3b8}' +
      '.rv-label.on{background:#0f766e;border-color:#0f766e;color:#fff}' +
      '.rv-label.synced{background:#e0f2fe;border-color:#7dd3fc;color:#075985}' +
      '.rv-track{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px;color:#475569}' +
      '.rv-track select{border:1px solid #dbe3ea;border-radius:8px;padding:4px 6px;background:#fff;font-size:11px}' +
      '.rv-track-btn{font-size:11px;border:1px solid #dbe3ea;background:#f8fafc;border-radius:8px;padding:4px 9px;cursor:pointer}' +
      '.rv-track-btn.on{background:#1d4ed8;border-color:#1d4ed8;color:#fff}' +
      '.rv-empty{font-size:13px;color:#64748b;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:12px;padding:18px 20px}' +
      '@media(max-width:700px){.intel-review-queue{margin:12px 10px;padding:16px}}';
    document.head.appendChild(style);

    function refreshCounts() {
      var c1 = root.querySelector('#rv-fb-count'), c2 = root.querySelector('#rv-mon-count');
      if (c1) c1.textContent = s.feedback.length;
      if (c2) c2.textContent = s.monitoring.length;
    }

    root.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-label]') : null;
      if (btn) {
        toggleFeedback(s, btn.getAttribute('data-event'), btn.getAttribute('data-label'));
        btn.classList.toggle('on');
        btn.classList.remove('synced');
        refreshCounts();
        return;
      }
      var tbtn = ev.target.closest ? ev.target.closest('.rv-track-btn') : null;
      if (tbtn) {
        var eid = tbtn.getAttribute('data-event');
        var wrap = tbtn.closest('.rv-track');
        var wl = wrap.querySelector('.rv-wl').value;
        var st = wrap.querySelector('.rv-st').value;
        var on = setMonitor(s, eid, wl, st);
        tbtn.classList.toggle('on', !!on);
        tbtn.textContent = on ? '取消跟踪' : '加入跟踪';
        refreshCounts();
      }
    });

    var exportBtn = root.querySelector('#rv-export');
    if (exportBtn) exportBtn.addEventListener('click', function () {
      download('p2_feedback_export.json', exportJson(s));
    });
    var issueBtn = root.querySelector('#rv-issue');
    if (issueBtn) issueBtn.addEventListener('click', function () { submitIssue(s); });
    var clearBtn = root.querySelector('#rv-clear');
    if (clearBtn) clearBtn.addEventListener('click', function () {
      if (!window.confirm('清空本机待入库的 ' + s.feedback.length + ' 条标签与 ' + s.monitoring.length + ' 条跟踪？已入库记录不受影响。')) return;
      save({ version: 1, feedback: [], monitoring: [] });
      location.reload();
    });

    // 有专用挂载点（review-ui.html）时渲染进挂载点；否则沿用主站行为：注入 <main> 顶部
    if (mount) { mount.innerHTML = ''; mount.appendChild(root); }
    else { (document.querySelector('main') || document.body).prepend(root); }
    refreshCounts();
  }

  function boot() {
    var s = load();
    var pState = fetch('p2_state.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { feedback: [], monitoring: [], watchlists: [] }; })
      .catch(function () { return { feedback: [], monitoring: [], watchlists: [] }; });
    var pQueue = fetch('review_queue.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    Promise.all([pQueue, pState]).then(function (res) {
      render(res[0], res[1], s);
    }).catch(function () {});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
