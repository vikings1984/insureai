/* Claim -> Evidence UI: make each important fact traceable. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={cross_checked:'已交叉验证',supported:'有来源支持',uncorroborated:'待验证'};
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now()); if(!res.ok)return;
      const data=await res.json(); const events=Array.isArray(data.events)?data.events:[];
      const cards=[...document.querySelectorAll('#daily-intelligence .di-item')];
      const byTitle=new Map(events.map(e=>[String(e.title||''),e]));
      cards.forEach(card=>{
        const title=card.querySelector('h3')?.textContent||''; const event=byTitle.get(title); if(!event||card.querySelector('.claim-evidence'))return;
        const c=event.claims||{}; const claims=Array.isArray(c.claims)?c.claims:[];
        const box=document.createElement('div'); box.className='claim-evidence';
        box.innerHTML='<div class="ce-head"><b>事实证据</b><span>覆盖 '+esc(c.coverage||0)+'% · 交叉验证 '+esc(c.cross_checked||0)+'</span></div>' +
          (claims.length?'<div class="ce-list">'+claims.map(x=>'<div class="ce-row"><div><strong>'+esc(x.text)+'</strong><small>'+esc(labels[x.status]||x.status||'')+' · '+esc(x.evidence_count||0)+' 来源</small></div><span>'+esc(x.independent_domains||0)+' 域</span></div>').join('')+'</div>':'<div class="ce-empty">暂无可拆分的事实证据。</div>');
        card.querySelector('.di-body')?.appendChild(box);
      });
      const style=document.createElement('style'); style.textContent='.claim-evidence{margin-top:10px;padding-top:9px;border-top:1px dashed #e2e8f0}.ce-head{display:flex;justify-content:space-between;gap:10px;font-size:10px}.ce-head b{color:#475569}.ce-head span{color:#94a3b8}.ce-list{display:grid;gap:5px;margin-top:6px}.ce-row{display:flex;justify-content:space-between;gap:10px;padding:6px 0}.ce-row>div{display:grid;gap:2px}.ce-row strong{font-size:11px;font-weight:600;color:#334155}.ce-row small,.ce-row>span{font-size:9px;color:#64748b}.ce-empty{font-size:10px;color:#94a3b8;margin-top:6px}'; document.head.appendChild(style);
    }catch(e){console.warn('Claim evidence UI unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,450));else setTimeout(boot,450);
})();
