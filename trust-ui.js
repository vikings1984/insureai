/* Evidence trust UI: show why an intelligence event is trustworthy or needs caution. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={high:'高可信',medium:'中可信',low:'低可信'};
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now());if(!res.ok)return;
      const data=await res.json(), events=Array.isArray(data.events)?data.events:[];
      const cards=[...document.querySelectorAll('#daily-intelligence .di-item')];
      const byTitle=new Map(events.map(e=>[String(e.title||''),e]));
      cards.forEach(card=>{
        const title=card.querySelector('h3')?.textContent||'';const event=byTitle.get(title);if(!event||card.querySelector('.trust-badge'))return;
        const t=event.trust||{};const badge=document.createElement('div');badge.className='trust-badge trust-'+(t.level||'low');
        badge.innerHTML='<span>'+esc(labels[t.level]||'可信度')+'</span><small>'+esc(t.independent_domains||0)+' 独立来源 · '+esc(t.agreement||0)+'% 一致性 · 证据覆盖 '+esc(t.evidence_coverage||0)+'%</small>'+(t.conflict?'<strong>⚠ 存在证据冲突：'+esc((t.conflict_fields||[]).join('、'))+'</strong>':'');
        card.querySelector('.di-body')?.appendChild(badge);
      });
      const style=document.createElement('style');style.textContent='.trust-badge{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:10px;font-size:10px}.trust-badge span{font-weight:800;padding:4px 7px;border-radius:999px}.trust-badge small{color:#64748b}.trust-badge strong{width:100%;font-size:10px;font-weight:600;color:#b45309}.trust-high span{background:#ecfdf5;color:#047857}.trust-medium span{background:#fffbeb;color:#a16207}.trust-low span{background:#f1f5f9;color:#64748b}';document.head.appendChild(style);
    }catch(e){console.warn('Trust UI unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,300));else setTimeout(boot,300);
})();
