/* InsureAI shared data store (P0-1 fix).
 *
 * 背景：intelligence-ui / trust / claim-evidence / decision / temporal 五个 UI
 * 模块此前各自执行 `fetch('intelligence.json?t='+Date.now(),{cache:'no-store'})`，
 * 导致单次访问重复下载 intelligence.json 5 次（≈26.5 MB），且 ?t=Date.now() + no-store
 * 完全禁用了 HTTP 缓存。
 *
 * 修复：
 *  1. 全局只加载一次，返回一个共享的 Promise，多模块复用（5.29 MB → 1 次）。
 *  2. 去掉 ?t=Date.now() —— 不再每次构造唯一 URL 破坏缓存。
 *  3. 去掉 cache:'no-store' —— 交给 ETag / Last-Modified 走默认缓存。
 *  4. 部署期用一个稳定的 build id 作为唯一缓存破缀（meta[name=insureai-build-id]），
 *     仅在发版时变化，而不是每次页面加载都变。
 */
(function () {
  var _promise = null;

  function load() {
    if (!_promise) {
      var url = 'intelligence.json';
      var meta = document.querySelector('meta[name="insureai-build-id"]');
      if (meta && meta.content) {
        url = 'intelligence.json?v=' + encodeURIComponent(meta.content);
      }
      _promise = fetch(url).then(function (r) {
        if (!r.ok) throw new Error('intelligence.json HTTP ' + r.status);
        return r.json();
      });
    }
    return _promise;
  }

  window.InsureAIData = { load: load };
})();
