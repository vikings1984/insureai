/* Local-first Personal Intelligence: preferences never leave the browser. */
(function () {
  const KEY = 'insureai_profile_v1';
  const TOPICS = [
    ['ai_intelligent','AI智能化'],['pension_finance','养老金融'],['product_innovation','产品创新'],
    ['channel_transformation','渠道变革'],['capital_reinsurance','资本与再保险'],['climate_catastrophe','气候与巨灾'],
    ['digital_transformation','数字化转型'],['regulatory_change','监管变革']
  ];
  const ROLES = [
    ['executive','管理层 / 高管'],['product','产品'],['underwriting','核保'],['actuarial','精算'],
    ['investment','投资 / 资管'],['technology','科技 / 数字化'],['claims','理赔'],['distribution','渠道']
  ];
  const ROLE_TYPES = {
    executive:new Set(['acquisition','capital','regulatory','market_entry']), product:new Set(['product','market_entry','regulatory']),
    underwriting:new Set(['rating','claims_loss','product','regulatory']), actuarial:new Set(['claims_loss','rating','capital','catastrophe']),
    investment:new Set(['capital','acquisition','rating','regulatory']), technology:new Set(['product','market_entry','regulatory']),
    claims:new Set(['claims_loss','product','regulatory']), distribution:new Set(['market_entry','product'])
  };
  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  function load(){ try { return JSON.parse(localStorage.getItem(KEY)) || {version:1,role:'executive',topics:[],entities:[]}; } catch(e){ return {version:1,role:'executive',topics:[],entities:[]}; } }
  function save(p){ localStorage.setItem(KEY, JSON.stringify(p)); }
  function score(event,p){
    let boost = ROLE_TYPES[p.role]?.has(event.event_type) ? 8 : 0;
    boost += p.topics.includes(String(event.topic||'')) ? 10 : 0;
    const selected = new Set((event.entities||[]).map(x=>String(x).toLowerCase()));
    boost += Math.min(18, p.entities.filter(x=>selected.has(String(x).toLowerCase())).length * 9);
    return Math.min(100, Number(event.scores?.intelligence_score||0) + boost);
  }
  function renderPanel(profile, onChange){
    const roleOptions = ROLES.map(([v,l])=>`<option value="${v}" ${profile.role===v?'selected':''}>${esc(l)}</option>`).join('');
    const topicOptions = TOPICS.map(([v,l])=>`<label><input type="checkbox" data-topic="${v}" ${profile.topics.includes(v)?'checked':''}> ${esc(l)}</label>`).join('');
    const panel = document.createElement('section'); panel.id='personal-intelligence'; panel.innerHTML =
      `<div class="pi-head"><div><div class="di-kicker">MY INTELLIGENCE</div><h2>我的关注</h2><p>偏好仅保存在本机，不上传账号服务器。</p></div><button id="pi-reset" type="button">重置</button></div>`+
      `<div class="pi-grid"><label class="pi-role">我的角色<select id="pi-role">${roleOptions}</select></label><div><b>关注主题</b><div class="pi-topics">${topicOptions}</div></div></div>`+
      `<label class="pi-entities">关注公司 / 实体<input id="pi-entities" placeholder="例如 Munich Re, Ping An, At-Bay" value="${esc(profile.entities.join(', '))}"></label>`;
    panel.querySelector('#pi-role').addEventListener('change',(e)=>{ profile.role=e.target.value; save(profile); onChange(profile); });
    panel.querySelectorAll('[data-topic]').forEach(el=>el.addEventListener('change',()=>{ profile.topics=[...panel.querySelectorAll('[data-topic]:checked')].map(x=>x.dataset.topic); save(profile); onChange(profile); }));
    panel.querySelector('#pi-entities').addEventListener('change',(e)=>{ profile.entities=e.target.value.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean).slice(0,12); save(profile); onChange(profile); });
    panel.querySelector('#pi-reset').addEventListener('click',()=>{ const fresh={version:1,role:'executive',topics:[],entities:[]}; save(fresh); onChange(fresh); location.reload(); });
    return panel;
  }
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now()); if(!res.ok)return;
      const data=await res.json(); const profile=load();
      const daily=Array.isArray(data.daily_brief)?data.daily_brief:[];
      const wrapper=document.createElement('div');
      function renderPersonal(p){
        const ranked=daily.map(e=>({e,s:score(e,p)})).sort((a,b)=>b.s-a.s).slice(0,5);
        let box=document.getElementById('pi-results');
        if(!box){ box=document.createElement('section'); box.id='pi-results'; wrapper.appendChild(box); }
        box.innerHTML=`<div class="pi-results-head"><h3>为你优先排序</h3><span>基于本机偏好</span></div>`+
          (ranked.length?`<div class="pi-result-list">${ranked.map((x,i)=>`<div class="pi-result"><span class="pi-result-rank">${i+1}</span><div><strong>${esc(x.e.title)}</strong><small>${esc(x.e.topic_label||'保险行业')} · 个性化 ${x.s}</small></div></div>`).join('')}</div>`:'<p class="pi-empty">选择角色、主题或公司后，这里会形成你的专属情报排序。</p>');
      }
      const host=document.querySelector('.app-layout')||document.querySelector('main')||document.body.firstElementChild;
      wrapper.appendChild(renderPanel(profile,renderPersonal)); renderPersonal(profile);
      const style=document.createElement('style'); style.textContent='#personal-intelligence,#pi-results{margin:18px auto 24px;max-width:1180px;padding:20px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:#fff;box-shadow:0 8px 30px rgba(20,40,60,.05)}#personal-intelligence .pi-head{display:flex;justify-content:space-between;align-items:flex-start}#personal-intelligence h2,#pi-results h3{margin:2px 0 4px;font-size:21px}#personal-intelligence p{margin:0;color:#64748b;font-size:12px}.pi-head button{border:1px solid #dbe3ea;background:#f8fafc;border-radius:8px;padding:6px 10px;cursor:pointer}.pi-grid{display:grid;grid-template-columns:220px 1fr;gap:22px;margin-top:15px}.pi-role,.pi-entities{display:grid;gap:6px;font-size:12px;color:#475569}.pi-role select,.pi-entities input{border:1px solid #dbe3ea;border-radius:8px;padding:9px 10px;background:#fff}.pi-topics{display:flex;flex-wrap:wrap;gap:7px;margin-top:7px}.pi-topics label{font-size:11px;padding:6px 8px;border:1px solid #e2e8f0;border-radius:999px;background:#f8fafc}.pi-entities{margin-top:14px}.pi-results-head{display:flex;justify-content:space-between;align-items:center}.pi-results-head span{font-size:10px;color:#94a3b8}.pi-result-list{display:grid;gap:7px;margin-top:10px}.pi-result{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid #eef2f5}.pi-result-rank{font-weight:800;color:#94a3b8}.pi-result div{display:grid;gap:2px}.pi-result strong{font-size:13px}.pi-result small{font-size:10px;color:#64748b}.pi-empty{font-size:12px;color:#64748b}@media(max-width:700px){#personal-intelligence,#pi-results{margin:12px 10px;padding:16px}.pi-grid{grid-template-columns:1fr}}'; document.head.appendChild(style);
      if(host&&host.parentNode) host.parentNode.insertBefore(wrapper,host);
    }catch(e){console.warn('Personal Intelligence unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
