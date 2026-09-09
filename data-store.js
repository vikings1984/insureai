/* InsureAI shared data store (P0-1).
 *
 * 背景一（首屏重复下载）：intelligence-ui / trust / claim-evidence / decision /
 * temporal 五个 UI 模块此前各自执行
 *   fetch('intelligence.json?t='+Date.now(), {cache:'no-store'})
 * 导致单次访问重复下载 intelligence.json 5 次（≈65 MB），且 ?t=Date.now() + no-store
 * 完全禁用了 HTTP 缓存。
 *
 * 背景二（单文件过大）：contract.py 把 claims / decisions_by_role / temporal 内联进
 * intelligence.json 后，单文件涨到 13 MB 量级，而 index.html 首屏只用到约 118 KB。
 *
 * 修复：
 *  1. 全局只加载一次，返回共享 Promise，多模块复用。
 *  2. 去掉 ?t=Date.now() 与 cache:'no-store'，交给 ETag / Last-Modified 走默认缓存；
 *     部署期用稳定的 build id 作为缓存破缀（meta[name=insureai-build-id]），
 *     仅在发版时变化，而不是每次页面加载都变。
 *  3. 按消费场景分片：
 *       loadSummary()  → intelligence.summary.json    ~118 KB  首屏五个模块
 *       loadIndex()    → intelligence.events.json     ~1.3 MB  事件列表工作台
 *       loadDetail(id) → intelligence.detail.<k>.json ~180 KB  单事件详情（按需）
 *
 * 回退纪律：分片由部署流水线生成、**不进仓库**（见 .gitignore）。
 * 因此在没有分片的环境（例如直接由仓库托管的 GitHub Pages 镜像）里，
 * 每个分片加载器都会在取不到分片时自动退回全量 intelligence.json，
 * 页面表现与分片之前完全一致 —— 分片是加速，不是依赖。
 */
(function () {
  var _full = null;
  var _summary = null;
  var _index = null;
  var _chunks = {};
  var _buildId = null;

  function buildId() {
    if (_buildId === null) {
      var meta = document.querySelector('meta[name="insureai-build-id"]');
      _buildId = (meta && meta.content) ? meta.content : '';
    }
    return _buildId;
  }

  function url(name) {
    var id = buildId();
    return id ? name + '?v=' + encodeURIComponent(id) : name;
  }

  function getJson(name) {
    return fetch(url(name)).then(function (r) {
      if (!r.ok) throw new Error(name + ' HTTP ' + r.status);
      return r.json();
    });
  }

  /* 全量文件：权威产物，也是分片缺失时的兜底。 */
  function load() {
    if (!_full) _full = getJson('intelligence.json');
    return _full;
  }

  /* 首屏分片：取不到就退回全量。 */
  function loadSummary() {
    if (!_summary) {
      _summary = getJson('intelligence.summary.json')['catch'](function () { return load(); });
    }
    return _summary;
  }

  /* 事件索引分片：取不到就退回全量。 */
  function loadIndex() {
    if (!_index) {
      _index = getJson('intelligence.events.json')['catch'](function () { return load(); });
    }
    return _index;
  }

  /* 单事件详情：先定位索引条目得到分块号，再按需拉取该分块并按事件缓存。
   * 索引条目本身已是全量事件（回退模式）时直接返回，不再额外请求。 */
  function loadDetail(eventId) {
    return loadIndex().then(function (doc) {
      var events = (doc && doc.events) || [];
      for (var i = 0; i < events.length; i++) {
        if (String(events[i].event_id) === String(eventId)) {
          var lean = events[i];
          var key = lean.detail_chunk;
          if (key === undefined || key === null) return lean;
          if (!_chunks[key]) {
            _chunks[key] = getJson('intelligence.detail.' + key + '.json')['catch'](function () { return null; });
          }
          return _chunks[key].then(function (bucket) {
            var extra = bucket && bucket.events && bucket.events[String(eventId)];
            if (!extra) return lean;
            var merged = {};
            var k;
            for (k in lean) { if (Object.prototype.hasOwnProperty.call(lean, k)) merged[k] = lean[k]; }
            for (k in extra) { if (Object.prototype.hasOwnProperty.call(extra, k)) merged[k] = extra[k]; }
            return merged;
          });
        }
      }
      throw new Error('event not found: ' + eventId);
    });
  }

  window.InsureAIData = {
    load: load,
    loadSummary: loadSummary,
    loadIndex: loadIndex,
    loadDetail: loadDetail
  };
})();
