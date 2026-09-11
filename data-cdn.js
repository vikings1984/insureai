/* InsureAI data-cdn.js — F-03 生成物外置（瘦身 Workers 产物）
 *
 * 问题：Workers 部署把整个仓库（30 MB+）作为静态资源上传，但首屏只需要约 118 KB。
 * 体积最大的分析产物（knowledge_graph.json 7 MB、claims.json 5.5 MB、
 * intelligence.json 13 MB 等 19 个文件）其实只被个别页面按需 fetch。
 *
 * 方案：Workers 只上传前端 + 首屏分片（几 MB）；这 19 个文件不进 Workers，
 * 改由同源的 GitHub Pages 提供。Pages 已开启 `Access-Control-Allow-Origin: *`，
 * 可直接当作 CORS 安全的 CDN 使用。本文件 patch window.fetch：对这些路径
 * 先走 Pages CDN，失败再回退同源 —— 因此无需改动任何业务页面的 fetch 逻辑。
 *
 * 必须在所有其它脚本之前加载（deploy 时由 build_worker_dist.py 注入到 <head> 最前）。
 *
 * 外置清单与 scripts/build_worker_dist.py 的 EXCLUDE 清单必须保持一致。
 */
(function () {
  'use strict';
  var CDN = 'https://vikings1984.github.io/insureai/';

  // 外置到 Pages CDN 的文件（与 build_worker_dist.py EXTERNAL_JSON 一致）
  var EXTERNAL = {
    'intelligence.json': 1,
    'knowledge_graph.json': 1,
    'claims.json': 1,
    'data.json': 1,
    'research.json': 1,
    'kg_viz.json': 1,
    'canonical_events.json': 1,
    'second_brain.json': 1,
    'p2_personal_memory.json': 1,
    'p2_daily_brief.json': 1,
    'p2_state.json': 1,
    'p2_alerts.json': 1,
    'decisions_pending.json': 1,
    'review_queue.json': 1,
    'event_replays.json': 1,
    'action_triggers.json': 1,
    'owner_risk_view.json': 1,
    'execution_readiness.json': 1,
    'executive_terminal.json': 1
  };

  var _orig = (typeof window !== 'undefined' && window.fetch) ? window.fetch.bind(window) : null;
  if (!_orig) return; // 无 fetch（极旧环境）直接跳过，页面回退到原有同源行为

  function relPath(input) {
    var s = (typeof input === 'string') ? input : (input && input.url) || '';
    if (!s) return '';
    try {
      // 解析为相对于站点根的路径（去掉查询串）
      var path = new URL(s, (typeof location !== 'undefined' ? location.href : 'https://insureai.local/')).pathname;
      return path.replace(/^\/+/, '');
    } catch (e) {
      // 兜底：去掉查询串与前导 ./
      return String(s).split('?')[0].replace(/^\.?\//, '');
    }
  }

  window.fetch = function (input, init) {
    var rel = relPath(input);
    if (Object.prototype.hasOwnProperty.call(EXTERNAL, rel)) {
      var cdnUrl = CDN + rel;
      return _orig(cdnUrl, init).then(function (r) {
        if (r.ok) return r;
        return _orig(input, init); // CDN 未命中（极少）→ 回退同源
      }, function () {
        return _orig(input, init);
      });
    }
    return _orig(input, init);
  };
})();
