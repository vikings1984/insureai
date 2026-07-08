
    // ===== Embedded Backup Data (fallback if fetch fails) =====
    // 真实数据由同仓库 data.json 运行时加载；此处仅 fetch 失败时的空回退，
    // 不再内嵌任何静态样例数据（避免把陈旧/假数据当作真实资讯展示）。
    const BACKUP_DATA = {"news": [], "sources": []};

    // ===== Data (loaded from data.json) =====
    let NEWS_DATA = [];
    let SOURCES_DATA = [];
    let RESEARCH_DATA = [];

    // ===== XSS Protection: HTML escape for all dynamic content =====
    function esc(str) {
      if (str == null) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function safeUrl(url) {
      if (!url || typeof url !== 'string') return '';
      const u = url.trim();
      if (/^https?:\/\//i.test(u)) return u;
      return '';
    }

    // ===== LocalStorage Utils =====
    const storage = {
      get: (k) => { try { return JSON.parse(localStorage.getItem(k)) || {}; } catch(e) { return {}; } },
      set: (k, v) => localStorage.setItem(k, JSON.stringify(v))
    };

    // ===== 项目名统一：旧 localStorage 键迁移到 insureai_*（保留用户已读/收藏/提报数据） =====
    const STORAGE_KEY_MIGRATION = {
      'insurescope_read': 'insureai_read',
      'insurescope_fav': 'insureai_fav',
      'insurescope_sources': 'insureai_sources',
      'insurescope_feedback': 'insureai_feedback',
    };
    (function migrateStorageKeys() {
      for (const [oldK, newK] of Object.entries(STORAGE_KEY_MIGRATION)) {
        const v = localStorage.getItem(oldK);
        if (v == null) continue;
        if (localStorage.getItem(newK) == null) localStorage.setItem(newK, v);
        localStorage.removeItem(oldK);
      }
    })();

    // ===== State =====
    const RESEARCH_TOPIC_LABELS = {
      ai_intelligent: 'AI智能化',
      pension_finance: '养老金融',
      product_innovation: '产品创新',
      channel_transformation: '渠道变革',
      capital_reinsurance: '资本与再保险',
      climate_catastrophe: '气候与巨灾',
      digital_transformation: '数字化转型',
      regulatory_change: '监管变革',
    };
    const state = {
      page: 'featured',
      featured: { category: 'all', keyword: '' },
      all: { category: 'all', keyword: '', page: 1, pageSize: 20 },
      research: { topic: 'all' },
      read: storage.get('insureai_read'),
      fav: storage.get('insureai_fav'),
      feedbackType: 'bug'
    };

    // ===== Load Data =====
    // 同源加载：data-url 默认指向同仓库 data.json。GitHub Pages 每次 push 自动重部署，
    // 数据即最新，无需 jsDelivr CDN / SHA pin / purge。fetch 加缓存戳避免浏览器陈旧缓存。
    // 研究数据从同源 research.json 加载（源自 InsureAI 知识库的中文研究报告）。
    async function loadData() {
      const primary = document.querySelector('meta[name="data-url"]')?.content || 'data.json';
      const finalUrl = primary.startsWith('http') ? primary : (primary + '?t=' + Date.now());
      try {
        const res = await fetch(finalUrl);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (!data || !Array.isArray(data.news)) throw new Error('bad payload');
        NEWS_DATA = deduplicateData(data.news || []);
        SOURCES_DATA = data.sources || [];
      } catch (e) {
        console.warn('loadData 主源失败，回退内嵌备用数据:', e);
        NEWS_DATA = deduplicateData(BACKUP_DATA.news || []);
        SOURCES_DATA = BACKUP_DATA.sources || [];
      }
      await loadResearch();
      initApp();
    }

    async function loadResearch() {
      try {
        const res = await fetch('research.json?t=' + Date.now());
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        RESEARCH_DATA = Array.isArray(data.reports) ? data.reports
                       : (Array.isArray(data) ? data : []);
      } catch (e) {
        console.warn('loadResearch 失败（研究版块将留空）:', e);
        RESEARCH_DATA = [];
      }
    }

    // ===== Deduplication =====
    function deduplicateData(data) {
      const seen = new Set();
      return data.filter(item => {
        const normalizedTitle = item.title.toLowerCase()
          .replace(/[\s\p{P}]/gu, '')
          .replace(/\d+/g, '');
        for (const seenTitle of seen) {
          if (calculateSimilarity(normalizedTitle, seenTitle) > 0.7) {
            return false;
          }
        }
        seen.add(normalizedTitle);
        return true;
      });
    }

    function calculateSimilarity(a, b) {
      if (a === b) return 1;
      const longer = a.length > b.length ? a : b;
      const shorter = a.length > b.length ? b : a;
      if (longer.length === 0) return 1;
      const distance = levenshteinDistance(longer, shorter);
      return (longer.length - distance) / longer.length;
    }

    function levenshteinDistance(a, b) {
      const matrix = [];
      for (let i = 0; i <= b.length; i++) matrix[i] = [i];
      for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
      for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
          matrix[i][j] = b[i-1] === a[j-1]
            ? matrix[i-1][j-1]
            : Math.min(matrix[i-1][j-1] + 1, matrix[i][j-1] + 1, matrix[i-1][j] + 1);
        }
      }
      return matrix[b.length][a.length];
    }

    // ===== Filter =====
    function filterData(keyword, category) {
      let data = [...NEWS_DATA];
      if (category && category !== 'all') data = data.filter(item => item.category === category);
      if (keyword) {
        const kw = keyword.toLowerCase();
        data = data.filter(item =>
          item.title.toLowerCase().includes(kw) ||
          item.summary.toLowerCase().includes(kw) ||
          (item.tags && item.tags.toLowerCase().includes(kw)) ||
          (item.source_name && item.source_name.toLowerCase().includes(kw))
        );
      }
      return data;
    }

    // ===== Render Hot Topics =====
    function renderHotTopics(data) {
      const container = document.getElementById('hot-topics');
      if (!container) return;
      // Take top 3-5 items with highest ai_score as hot topics
      const hot = data.slice(0, 5);
      if (!hot.length) { container.innerHTML = ''; return; }
      container.innerHTML = hot.map((item, i) => {
        const catNames = { regulation: '监管', product: '产品', industry: '行业', research: '研究', claims: '理赔' };
        return `
          <div class="hot-topic-card" onclick="showDetail(${item.id})">
            <div class="hot-topic-rank">#${i + 1} 热点</div>
            <div class="hot-topic-title">${esc(item.title)}</div>
            <div class="hot-topic-meta">
              <span>${esc(item.source_name) || ''}</span>
              <span>· ${esc(catNames[item.category] || item.category)}</span>
              <span class="hot-topic-count">&#9733; ${esc(item.ai_score)}</span>
            </div>
          </div>
        `;
      }).join('');
    }

    // ===== Render Featured =====
    function renderFeatured() {
      let data = filterData(state.featured.keyword, state.featured.category);
      data = data.filter(item => item.ai_score >= 60);
      // 精选按"时间倒序"为主、ai_score 为次，确保最新采集的资讯优先展示
      // （修复：原按 ai_score 排序 + date_verified 优先，导致旧的"人工精选"高分项霸屏，当天数据被埋到榜尾）
      data.sort((a, b) => {
        return new Date(b.published_at) - new Date(a.published_at) || b.ai_score - a.ai_score;
      });
      renderHotTopics(data);
      renderTimeline('timeline-featured', data, true, true);
      renderRecommendations();
    }

    // ===== Render All =====
    function renderAll() {
      let data = filterData(state.all.keyword, state.all.category);
      data.sort((a, b) => new Date(b.published_at) - new Date(a.published_at));
      const totalPages = Math.ceil(data.length / state.all.pageSize);
      if (state.all.page > totalPages) state.all.page = totalPages || 1;
      const start = (state.all.page - 1) * state.all.pageSize;
      const pageData = data.slice(start, start + state.all.pageSize);
      renderTimeline('timeline-all', pageData, false, false);
      renderPagination(state.all.page, totalPages, data.length);
    }

    // ===== Render Pagination =====
    function renderPagination(page, totalPages, totalItems) {
      const container = document.getElementById('pagination-all');
      if (!container || totalPages <= 1) { if (container) container.style.display = 'none'; return; }
      container.style.display = 'flex';
      container.innerHTML = `
        <button class="pagination-btn ${page <= 1 ? 'disabled' : ''}" onclick="goPage(${page - 1})" ${page <= 1 ? 'disabled' : ''}>上一页</button>
        <span class="pagination-info">第 ${page} / ${totalPages} 页 · 共 ${totalItems} 条</span>
        <button class="pagination-btn ${page >= totalPages ? 'disabled' : ''}" onclick="goPage(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>下一页</button>
      `;
    }

    // ===== Render Timeline =====
    function renderTimeline(containerId, data, showScore, showReason) {
      const container = document.getElementById(containerId);
      if (!data.length) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#128269;</div><p>暂无内容</p></div>';
        return;
      }

      const grouped = groupByDate(data);
      let html = '';

      Object.keys(grouped).forEach(date => {
        const items = grouped[date];
        const isCollapsed = state[`collapsed_${date}`] || false;
        html += `
          <div class="date-header" onclick="toggleDate('${date}')">
            <span class="date-dropdown">${isCollapsed ? '&#9654;' : '&#9660;'}</span>
            <span class="date-label">${date}</span>
          </div>
          <div id="date-group-${date}" style="${isCollapsed ? 'display:none' : ''}">
        `;
        items.forEach(news => {
          const isRead = state.read[news.id];
          const isFav = state.fav[news.id];
          const hasSource = news.source_url && news.source_url !== '#';
          const sourceSub = news.source_type ? `<span class="source-sub">${esc(news.source_type)}</span>` : '';
          const dateVerified = news.date_verified ? '<span class="date-verified-badge" title="发布日期已验证">&#10003;</span>' : '';
          const authReport = news.is_research_report ? '<span class="auth-report-badge" title="权威研究报告">&#128218;</span>' : '';
          const topicLabel = news.research_topic ? RESEARCH_TOPIC_LABELS[news.research_topic] || '' : '';
          const topicBadge = topicLabel ? `<span class="topic-badge" title="研究主题">${esc(topicLabel)}</span>` : '';
          const scoreBadge = showScore ? `<span class="score-badge">&#9733; <span class="score-num">${esc(news.ai_score)}</span></span>` : '';
          const reasonBlock = showReason && news.reason ? `
            <div class="card-reason">
              <div class="reason-text"><span class="reason-label">推荐理由：</span>${esc(news.reason)}</div>
            </div>
          ` : '';
          const tags = news.tags ? news.tags.split(',').map(t => `<span class="card-tag" data-tag="${esc(t.trim())}" onclick="event.stopPropagation();searchTag(this.dataset.tag)">${esc(t.trim())}</span>`).join('') : '';
          const summaryClass = news.summary && news.summary.length > 80 ? 'collapsed' : '';
          const toggleBtn = news.summary && news.summary.length > 80 ? `<span class="summary-toggle" onclick="event.stopPropagation();toggleSummary(this)">展开</span>` : '';

          html += `
            <div class="timeline-item ${isRead ? 'is-read' : ''} ${isFav ? 'is-fav' : ''}" data-id="${news.id}" onclick="showDetail(${news.id})" style="cursor:pointer">
              <div class="time-col">
                <div class="time-text">${esc(formatTime(news.published_at))}</div>
              </div>
              <div class="timeline-axis">
                <div class="timeline-dot"></div>
              </div>
              <div class="card-content">
                <div class="card-source">${esc(news.source_name) || '未知来源'}${sourceSub} · <span class="relative-time">${esc(formatRelativeTime(news.published_at))}</span>${dateVerified}${authReport}${topicBadge}</div>
                <div class="title-row">
                  <div class="card-title" data-id="${news.id}">${esc(news.title)}</div>
                  ${scoreBadge}
                </div>
                <div class="card-summary ${summaryClass}">${esc(news.summary) || ''}${toggleBtn}</div>
                <div class="card-tags">${tags}</div>
                ${reasonBlock}
              </div>
            </div>
          `;
        });
        html += '</div>';
      });

      container.innerHTML = html;

    }

    // ===== Render Daily =====
    function renderDaily() {
      const container = document.getElementById('daily-content');
      const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
      const vol = Math.floor((new Date() - new Date('2024-05-15')) / 86400000);

      const cats = {
        regulation: { name: '监管政策', items: [] },
        product: { name: '产品发布', items: [] },
        industry: { name: '行业动态', items: [] },
        research: { name: '研究洞察', items: [] },
        claims: { name: '理赔案例', items: [] }
      };

      NEWS_DATA.forEach(item => {
        if (cats[item.category]) cats[item.category].items.push(item);
      });

      let html = `
        <div class="daily-masthead">
          <h2>保险日报</h2>
          <div class="daily-date">${today}</div>
          <div class="daily-tagline">DAILY · 每早八时</div>
          <div class="daily-vol">第 ${vol} 期 · ${NEWS_DATA.length} 条动态</div>
        </div>
      `;

      let globalNum = 1;
      Object.keys(cats).forEach((key, idx) => {
        const cat = cats[key];
        if (!cat.items.length) return;
        html += `
          <div class="daily-section">
            <div class="daily-section-header">
              <span class="daily-section-num">0${idx + 1}</span>
              <span class="daily-section-name">${cat.name}</span>
              <span class="daily-section-count">${cat.items.length} 条</span>
            </div>
        `;
        cat.items.forEach(item => {
          const hasSource = item.source_url && item.source_url !== '#';
          const safeHref = safeUrl(item.source_url);
          html += `
            <div class="daily-entry">
              <div class="daily-entry-source">
                <span class="source-name">${esc(item.source_name)}</span>
                ${item.source_type ? `<span class="source-tag">${esc(item.source_type)}</span>` : ''}
              </div>
              <div class="daily-entry-title">${hasSource ? `<a href="${esc(safeHref)}" target="_blank" rel="noopener noreferrer">${globalNum}. ${esc(item.title)}</a>` : `${globalNum}. ${esc(item.title)}`}</div>
              <div class="daily-entry-summary">${esc(item.summary) || ''}</div>
            </div>
          `;
          globalNum++;
        });
        html += '</div>';
      });

      html += `
        <div class="daily-stats">
          <div class="daily-stat">
            <div class="daily-stat-num">${NEWS_DATA.length}</div>
            <div class="daily-stat-label">今日事件</div>
          </div>
          <div class="daily-stat">
            <div class="daily-stat-num">${NEWS_DATA.filter(n => n.ai_score >= 60).length}</div>
            <div class="daily-stat-label">精选</div>
          </div>
          <div class="daily-stat">
            <div class="daily-stat-num">5</div>
            <div class="daily-stat-label">分类</div>
          </div>
          <div class="daily-stat">
            <div class="daily-stat-num">${SOURCES_DATA.length || 16}</div>
            <div class="daily-stat-label">信源</div>
          </div>
        </div>
        <div class="daily-nav">
          <div class="daily-nav-btn disabled">&larr; 上一期</div>
          <div class="daily-nav-btn disabled">下一期 &rarr;</div>
        </div>
      `;

      container.innerHTML = html;
    }

    // ===== Render Recommendations =====
    function renderRecommendations() {
      const container = document.getElementById('source-list-container');
      if (!container) return;
      const sources = SOURCES_DATA.slice(0, 10);
      container.innerHTML = sources.map((s, i) => {
        const rank = i + 1;
        const rankClass = s.score >= 90 ? 'high' : s.score >= 80 ? 'medium' : 'low';
        const scoreClass = rankClass;
        return `
          <div class="source-item">
            <div class="source-rank ${rankClass}">${rank}</div>
            <div class="source-info">
              <div class="source-name">${esc(s.name)}</div>
              <div class="source-type">${esc(s.type)} · ${esc(s.reason.substring(0, 30))}...</div>
            </div>
            <div class="source-score ${scoreClass}">${s.score}</div>
          </div>
        `;
      }).join('');
    }

    function renderSourceWall() {
      const wall = document.getElementById('source-wall');
      const container = document.getElementById('source-wall-container');
      if (!wall || !container) return;
      const sources = JSON.parse(localStorage.getItem('insureai_sources') || '[]');
      if (!sources.length) { wall.style.display = 'none'; return; }
      wall.style.display = 'block';
      const typeLabels = { media: '保险垂直媒体', company: '保险公司官方', regulator: '监管机构', research: '研究机构', academic: '学术机构' };
      container.innerHTML = sources.map((s, i) => {
        const num = String(i + 1).padStart(3, '0');
        const t = s.timestamp ? new Date(s.timestamp).toLocaleDateString('zh-CN') : '';
        return `
          <div class="source-item">
            <div class="source-rank" style="background:var(--accent);color:#fff;font-size:0.7rem;font-weight:700;font-family:monospace">N° ${num}</div>
            <div class="source-info">
              <div class="source-name">${esc(s.name)}</div>
              <div class="source-type">${esc(typeLabels[s.type] || s.type)} · ${esc(s.reason.substring(0, 30))}...</div>
            </div>
            <div style="font-size:0.7rem;color:var(--text-muted)">${t}</div>
          </div>
        `;
      }).join('');
    }

    // ===== RSS (Deprecated - 即将上线) =====
    function getRSSLinks() {
      return [];
    }

    function renderRSSLinks() {
      const container = document.getElementById('rss-links');
      if (!container) return;
      container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:0.85rem">📡 RSS 订阅功能开发中（参考 InsureAI 架构）</div>';
    }

    // ===== Filter =====
    function groupByDate(data) {
      const groups = {};
      data.forEach(item => {
        const date = formatDate(item.published_at);
        if (!groups[date]) groups[date] = [];
        groups[date].push(item);
      });
      return groups;
    }

    function formatDate(dateStr) {
      const date = new Date(dateStr);
      const now = new Date();
      if (date.toDateString() === now.toDateString()) return '今天';
      return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) + '日';
    }
    function formatTime(dateStr) {
      return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    function formatRelativeTime(dateStr) {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);
      if (diffMins < 1) return '刚刚';
      if (diffMins < 60) return `${diffMins}分钟前`;
      if (diffHours < 24) return `${diffHours}小时前`;
      if (diffDays < 7) return `${diffDays}天前`;
      return formatDate(dateStr);
    }

    // ===== Toggle =====
    window.toggleDate = function(date) {
      const key = `collapsed_${date}`;
      state[key] = !state[key];
      const group = document.getElementById(`date-group-${date}`);
      const header = group.previousElementSibling;
      if (state[key]) {
        group.style.display = 'none';
        header.querySelector('.date-dropdown').innerHTML = '&#9654;';
      } else {
        group.style.display = 'block';
        header.querySelector('.date-dropdown').innerHTML = '&#9660;';
      }
    };

    window.toggleSummary = function(el) {
      const summary = el.parentElement;
      summary.classList.toggle('collapsed');
      el.textContent = summary.classList.contains('collapsed') ? '展开' : '收起';
    };

    window.goPage = function(p) {
      state.all.page = p;
      renderAll();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    window.searchTag = function(tag) {
      state.featured.keyword = tag;
      document.getElementById('search-featured').value = tag;
      switchPage('featured');
      renderFeatured();
    };

    // ===== Research Rendering (深度研究) =====
    function renderResearch() {
      const grid = document.getElementById('research-grid');
      if (!grid) return;
      const topic = state.research ? state.research.topic : 'all';
      let list = RESEARCH_DATA || [];
      if (topic && topic !== 'all') list = list.filter(r => r && r.topic === topic);
      if (!list.length) {
        grid.innerHTML = '<div class="empty-state">暂无研究报告数据。</div>';
        return;
      }
      const layerLabels = { reinsurance: '国际再保险', consulting: '全球咨询', domestic: '国内研究' };
      grid.innerHTML = list.map(r => {
        const topicLabel = RESEARCH_TOPIC_LABELS[r.topic] || r.topic || '';
        const layer = layerLabels[r.layer] || r.source_type || '';
        const keyData = Array.isArray(r.key_data) ? r.key_data.map(k => `<li>${esc(k)}</li>`).join('') : '';
        const url = safeUrl(r.url);
        return `<div class="research-card">
          <div class="research-card-head">
            <span class="research-layer">${esc(layer)}</span>
            <span class="topic-badge">${esc(topicLabel)}</span>
          </div>
          <div class="research-inst">${esc(r.institution_cn || r.institution || '')}</div>
          <h3 class="research-title">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>` : esc(r.title)}</h3>
          <div class="research-date">${esc(r.publish_date || '')}</div>
          ${keyData ? `<ul class="research-keydata">${keyData}</ul>` : ''}
          ${r.key_insight ? `<div class="research-insight"><span class="reason-label">核心洞察：</span>${esc(r.key_insight)}</div>` : ''}
        </div>`;
      }).join('');
    }

    // ===== Page Switching =====
    function switchPage(page) {
      state.page = page;
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      const targetPage = document.getElementById('page-' + page);
      if (targetPage) targetPage.classList.add('active');
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      const sidebarNav = document.querySelector(`.nav-item[data-nav="${page}"]`);
      if (sidebarNav) sidebarNav.classList.add('active');
      document.querySelectorAll('.mobile-nav-item').forEach(i => i.classList.remove('active'));
      const mobileNav = document.querySelector(`.mobile-nav-item[data-nav="${page}"]`);
      if (mobileNav) mobileNav.classList.add('active');
      window.scrollTo({ top: 0, behavior: 'smooth' });

      if (page === 'featured') renderFeatured();
      if (page === 'all') renderAll();
      if (page === 'daily') renderDaily();
      if (page === 'research') renderResearch();
    }

    // ===== Events =====
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => switchPage(item.dataset.nav));
    });
    document.querySelectorAll('.mobile-nav-item').forEach(item => {
      item.addEventListener('click', () => switchPage(item.dataset.nav));
    });

    document.querySelectorAll('#featured-tabs .category-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#featured-tabs .category-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        state.featured.category = tab.dataset.category;
        renderFeatured();
      });
    });

    document.querySelectorAll('#all-tabs .category-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#all-tabs .category-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        state.all.category = tab.dataset.category;
        state.all.page = 1;
        renderAll();
      });
    });

    document.querySelectorAll('#research-tabs .category-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#research-tabs .category-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        state.research.topic = tab.dataset.topic;
        renderResearch();
      });
    });

    let searchTimerF;
    document.getElementById('search-featured').addEventListener('input', (e) => {
      clearTimeout(searchTimerF);
      searchTimerF = setTimeout(() => { state.featured.keyword = e.target.value; renderFeatured(); }, 250);
    });
    document.getElementById('search-btn-featured').addEventListener('click', renderFeatured);

    let searchTimerA;
    document.getElementById('search-all').addEventListener('input', (e) => {
      clearTimeout(searchTimerA);
      searchTimerA = setTimeout(() => { state.all.keyword = e.target.value; state.all.page = 1; renderAll(); }, 250);
    });
    document.getElementById('search-btn-all').addEventListener('click', renderAll);

    document.querySelectorAll('.feedback-type').forEach(type => {
      type.addEventListener('click', () => {
        document.querySelectorAll('.feedback-type').forEach(t => t.classList.remove('active'));
        type.classList.add('active');
        state.feedbackType = type.dataset.type;
      });
    });

    document.getElementById('submit-source').addEventListener('click', () => {
      const url = document.getElementById('source-url').value.trim();
      const name = document.getElementById('source-name').value.trim();
      const type = document.getElementById('source-type').value;
      const reason = document.getElementById('source-reason').value.trim();
      if (!url || !name || !type || reason.length < 15) {
        alert('请填写所有必填项（推荐理由至少15字）');
        return;
      }
      const typeLabels = { media: '保险垂直媒体', company: '保险公司官方', regulator: '监管机构', research: '研究机构', academic: '学术机构' };
      const title = encodeURIComponent('信源提报: ' + name);
      const body = encodeURIComponent(
        '## 信源信息\n' +
        '- **信源名称**: ' + name + '\n' +
        '- **信源 URL**: ' + url + '\n' +
        '- **信源类型**: ' + (typeLabels[type] || type) + '\n' +
        '- **推荐理由**: ' + reason + '\n' +
        '- **提报时间**: ' + new Date().toISOString() + '\n\n' +
        '---\n*此 Issue 由 InsureAI 信源提报页面自动生成*'
      );
      const ghRepo = (document.querySelector('meta[name="github-repo"]')?.content || 'vikings1984/insureai').trim();
      const issueUrl = 'https://github.com/' + ghRepo + '/issues/new?title=' + title + '&body=' + body + '&labels=信源提报';
      window.open(issueUrl, '_blank');
      // 同时保存到 localStorage 作为备份
      const data = { url, name, type, reason, timestamp: new Date().toISOString() };
      const existing = JSON.parse(localStorage.getItem('insureai_sources') || '[]');
      existing.push(data);
      localStorage.setItem('insureai_sources', JSON.stringify(existing));
      document.getElementById('source-url').value = '';
      document.getElementById('source-name').value = '';
      document.getElementById('source-type').value = '';
      document.getElementById('source-reason').value = '';
    });
    document.getElementById('submit-feedback').addEventListener('click', () => {
      const content = document.getElementById('feedback-content').value.trim();
      const contact = document.getElementById('feedback-contact').value.trim();
      if (!content) {
        alert('请填写反馈内容');
        return;
      }
      const title = encodeURIComponent('反馈: ' + content.substring(0, 40));
      const body = encodeURIComponent(
        '## 反馈信息\n' +
        '- **反馈类型**: ' + state.feedbackType + '\n' +
        '- **联系方式**: ' + (contact || '未填写') + '\n' +
        '- **提交时间**: ' + new Date().toISOString() + '\n\n' +
        '## 反馈内容\n' + content + '\n\n' +
        '---\n*此 Issue 由 InsureAI 反馈页面自动生成*'
      );
      const ghRepo = (document.querySelector('meta[name="github-repo"]')?.content || 'vikings1984/insureai').trim();
      const issueUrl = 'https://github.com/' + ghRepo + '/issues/new?title=' + title + '&body=' + body + '&labels=反馈';
      window.open(issueUrl, '_blank');
      // 同时保存到 localStorage 作为备份
      const data = { type: state.feedbackType, content, contact, timestamp: new Date().toISOString() };
      const existing = JSON.parse(localStorage.getItem('insureai_feedback') || '[]');
      existing.push(data);
      localStorage.setItem('insureai_feedback', JSON.stringify(existing));
      document.getElementById('feedback-content').value = '';
      document.getElementById('feedback-contact').value = '';
    });

    // 反馈闭环：邮件备选出口（无 GitHub 也可反馈）
    (function setupFeedbackMail() {
      const mailMeta = document.querySelector('meta[name="feedback-email"]');
      const mailBtn = document.getElementById('feedback-mail');
      if (!mailMeta || !mailBtn) return;
      const email = (mailMeta.content || '').trim();
      if (!email) return; // 未配置邮箱则隐藏邮件出口
      mailBtn.style.display = 'block';
      mailBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const content = document.getElementById('feedback-content').value.trim();
        const contact = document.getElementById('feedback-contact').value.trim();
        if (!content) { alert('请先填写反馈内容'); return; }
        const subject = 'InsureAI 反馈: ' + content.substring(0, 40);
        const body = '反馈类型: ' + state.feedbackType + '\n联系方式: ' + (contact || '未填写') +
          '\n\n' + content + '\n\n---\n此邮件由 InsureAI 反馈页面生成';
        window.location.href = 'mailto:' + email + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
      });
    })();

    document.getElementById('modal-close').addEventListener('click', () => {
      document.getElementById('modal-overlay').classList.remove('active');
    });
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('modal-overlay')) {
        document.getElementById('modal-overlay').classList.remove('active');
      }
    });

    // ===== Detail Modal =====
    function showDetail(id) {
      const news = NEWS_DATA.find(n => n.id === id);
      if (!news) return;
      // Mark as read
      state.read[id] = true;
      storage.set('insureai_read', state.read);
      const el = document.querySelector(`.timeline-item[data-id="${id}"]`);
      if (el) el.classList.add('is-read');

      const catNames = { regulation: '监管政策', product: '产品发布', industry: '行业动态', research: '研究洞察', claims: '理赔案例' };
      const tags = news.tags ? news.tags.split(',').map(t => `<span class="card-tag" style="cursor:default">${esc(t.trim())}</span>`).join('') : '';
      const hasUrl = news.source_url && news.source_url !== '#';
      // Build share URL (current page URL with anchor)
      const shareUrl = window.location.origin + window.location.pathname + '?id=' + id;

      document.getElementById('modal-title').textContent = news.title;
      const safeHref = safeUrl(news.source_url);
      document.getElementById('modal-body').innerHTML = `
        <div class="modal-meta">
          <span>${esc(news.source_name) || '未知来源'}</span>
          ${news.source_type ? `<span class="source-sub">${esc(news.source_type)}</span>` : ''}
          <span> · ${esc(formatRelativeTime(news.published_at))}</span>${news.date_verified ? '<span class="date-verified-badge" title="发布日期已验证">&#10003;</span>' : ''}${news.is_research_report ? '<span class="auth-report-badge" title="权威研究报告">&#128218;</span>' : ''}
          <span> · ${esc(catNames[news.category] || news.category)}</span>
          ${news.research_topic ? `<span class="topic-badge" title="研究主题">${esc(RESEARCH_TOPIC_LABELS[news.research_topic] || news.research_topic)}</span>` : ''}
          ${news.ai_score ? `<span class="score-badge" style="display:inline-flex;vertical-align:middle;margin-left:4px">&#9733; <span class="score-num">${esc(news.ai_score)}</span></span>` : ''}
        </div>
        ${news.reason ? `<div class="card-reason" style="margin-bottom:16px"><div class="reason-text"><span class="reason-label">推荐理由：</span>${esc(news.reason)}</div></div>` : ''}
        <p style="white-space:pre-wrap;line-height:1.8">${esc(news.summary) || '暂无摘要'}</p>
        <div style="margin-top:12px">${tags}</div>
        <div class="modal-actions">
          ${safeHref ? `<a href="${esc(safeHref)}" target="_blank" rel="noopener noreferrer" class="modal-btn primary">阅读原文 &#8599;</a>` : ''}
          <button class="modal-btn secondary" onclick="copyShareLink('${esc(shareUrl.replace(/'/g, "\\'"))}')">&#128279; 复制链接</button>
          <button class="modal-btn secondary" onclick="document.getElementById('modal-overlay').classList.remove('active')">关闭</button>
        </div>
      `;
      document.getElementById('modal-overlay').classList.add('active');
    }

    window.copyShareLink = function(url) {
      navigator.clipboard.writeText(url).then(() => {
        const btn = document.querySelector('.modal-btn.secondary');
        if (btn && btn.textContent.includes('复制链接')) {
          btn.textContent = '已复制!';
          setTimeout(() => { btn.textContent = '🔗 复制链接'; }, 1500);
        }
      }).catch(() => {
        alert('复制失败，链接：' + url);
      });
    };

    // Calendar date
    document.getElementById('cal-date').textContent = new Date().getDate();

    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');
    document.body.setAttribute('data-theme', initialTheme);
    themeToggle.innerHTML = initialTheme === 'dark' ? '&#9788;' : '&#9790;'; // Sun for dark mode, Moon for light mode

    themeToggle.addEventListener('click', () => {
      const currentTheme = document.body.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      document.body.setAttribute('data-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      themeToggle.innerHTML = newTheme === 'dark' ? '&#9788;' : '&#9790;';
    });

    // ===== Init =====
    function initApp() {
      renderFeatured();
      renderAll();
      renderDaily();
      renderRecommendations();
      renderSourceWall();
      renderRSSLinks();
      // Update about page stats
      const statSources = document.getElementById('stat-sources');
      const statNews = document.getElementById('stat-news');
      if (statSources) statSources.textContent = (SOURCES_DATA.length || 15) + '+';
      if (statNews) statNews.textContent = NEWS_DATA.length;
    }

    loadData();
  