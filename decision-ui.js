/* Decision Intelligence UI: bounded, evidence-linked action guidance. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={now:'现在关注',soon:'近期关注',watch:'继续观察'};
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now()); if(!res.ok)return;
      const data=await res.json(); const decisions=Array.isArray(data.decisions)?data.decisions.slice(0,6):[];
      const host=document.querySelector('.app-layout')||document.querySelector('main'); if(!host||document.querySelector('#decision-intelligence'))return;
      const box=document.createElement('section'); box.id='decision-intelligence';
      box.innerHTML='<div class="dec-head"><div><div class="di-kicker">DECISION INTELLIGENCE</div><h2>下一步关注</h2><p>根据事件重要性、可信度和趋势阶段生成辅助建议，不替代业务决策。</p></div></div>' +
        (decisions.length?'<div class="dec-list">'+decisions.map(x=>'<div class="dec-row"><div><strong>'+esc(x.action)+'</strong><small>'+esc(labels[x.urgency]||x.urgency)+' · '+esc(x.basis?.temporal_phase||'')+' · 可信度 '+esc(x.basis?.trust_level||'')+'</small></div><span>'+esc(x.urgency_label||'')+'</span></div><div class="dec-basis">依据：情报 '+esc(x.basis?.intelligence_score||0)+' · 趋势信号 '+esc(x.basis?.signal_strength||0)+'</div>').join('')+'</div>':'<p class="dec-empty">暂无达到行动阈值的事件。</p>');
      host.parentNode.insertBefore(box,host);
      const style=document.createElement('style');style.textContent='#decision-intelligence{margin:18px auto 24px;max-width:1180px;padding:20px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:#fff;box-shadow:0 8px 30px rgba(20,40,60,.05)}#decision-intelligence h2{margin:2px 0 4px;font-size:21px}#decision-intelligence p{margin:0;color:#64748b;font-size:12px}.dec-list{display:grid;gap:8px;margin-top:12px}.dec-row{display:flex;justify-content:space-between;gap:14px;padding-top:9px;border-top:1px solid #eef2f5}.dec-row>div{display:grid;gap:3px}.dec-row strong{font-size:12px}.dec-row small{font-size:9px;color:#64748b}.dec-row>span{font-weight:800;font-size:10px;color:#475569}.dec-basis{font-size:9px;color:#94a3b8;margin-left:0}.dec-empty{font-size:11px;margin-top:8px}';document.head.appendChild(style);
    }catch(e){console.warn('Decision Intelligence unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
