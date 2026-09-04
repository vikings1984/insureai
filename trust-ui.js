/* Evidence trust UI: show why an intelligence event is trustworthy or needs caution. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={high:'高可信',medium:'中可信',low:'低可信'};
  const tierLabels={1:'T1 一手',2:'T2 通讯社',3:'T3 行业',4:'T4 社交'};
  async function boot(){
    try{
      const data=await window.InsureAIData.load(), events=Array.isArray(data.events)?data.events:[];
      const cards=[...document.querySelectorAll('#daily-intelligence .di-item')];
      const byTitle=new Map(events.map(e=>[String(e.title||''),e]));
      cards.forEach(card=>{
        const title=card.querySelector('h3')?.textContent||'';const event=byTitle.get(title);if(!event||card.querySelector('.trust-badge'))return;
        const t=event.trust||{};const badge=document.createElement('div');badge.className='trust-badge trust-'+(t.level||'low');
        const ev=(Array.isArray(t.evidence)?t.evidence:[]).slice(0,4);
        const tierHtml=bt=>'<i class="tv-tier tv-tier-'+(bt||3)+'">'+esc(tierLabels[bt]||('T'+(bt||3)))+'</i>';
        const evList=ev.length?'<div class="tv-ev">'+ev.map(x=>{const bt=x.source_tier||3;return '<span class="tv-ev-row"><i class="tv-tier tv-tier-'+bt+'">'+esc(tierLabels[bt]||('T'+bt))+'</i>'+esc(x.source_name||x.domain||'来源')+'</span>';}).join('')+'</div>':'';
        badge.innerHTML='<span>'+esc(labels[t.level]||'可信度')+'</span><small>'+esc(t.independent_domains||0)+' 独立来源 · '+esc(t.agreement||0)+'% 一致性 · 证据覆盖 '+esc(t.evidence_coverage||0)+'%'+(t.best_source_tier?' · 最高来源 '+tierHtml(t.best_source_tier):'')+'</small>'+(t.conflict?'<strong>⚠ 存在证据冲突：'+esc((t.conflict_fields||[]).join('、'))+'</strong>':'')+evList;
        card.querySelector('.di-body')?.appendChild(badge);
      });
      const style=document.createElement('style');style.textContent='.trust-badge{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:10px;font-size:10px}.trust-badge span{font-weight:800;padding:4px 7px;border-radius:999px}.trust-badge small{color:#64748b;display:inline-flex;align-items:center;gap:4px}.trust-badge strong{width:100%;font-size:10px;font-weight:600;color:#b45309}.trust-high span{background:#ecfdf5;color:#047857}.trust-medium span{background:#fffbeb;color:#a16207}.trust-low span{background:#f1f5f9;color:#64748b}.tv-tier{font-style:normal;font-weight:700;font-size:9px;padding:2px 5px;border-radius:3px;white-space:nowrap}.tv-tier-1{background:#dcfce7;color:#15803d}.tv-tier-2{background:#dbeafe;color:#1d4ed8}.tv-tier-3{background:#f1f5f9;color:#64748b}.tv-tier-4{background:#ffedd5;color:#c2410c}.tv-ev{display:flex;flex-wrap:wrap;gap:5px;width:100%}.tv-ev-row{display:inline-flex;align-items:center;gap:4px;color:#64748b;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}';document.head.appendChild(style);
    }catch(e){console.warn('Trust UI unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,300));else setTimeout(boot,300);
})();
