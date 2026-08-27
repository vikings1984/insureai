/* Decision Intelligence UI: bounded, evidence-linked action guidance. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={now:'现在关注',soon:'近期关注',watch:'继续观察'};
  const roleLabels={executive:'高管',product:'产品',underwriting:'核保',actuarial:'精算',investment:'投资',technology:'技术',claims:'理赔',distribution:'渠道'};
  let activeRole='executive';
  function cardsFor(data,role){
    const byRole=data.decisions_by_role||{};
    const rows=Array.isArray(byRole[role])?byRole[role]:(role==='executive'&&Array.isArray(data.decisions)?data.decisions:[]);
    return rows.slice(0,6);
  }
  function contextHtml(x){
    const c=x.context||{};
    const fns=(c.affected_functions||[]).map(f=>'<i class="dec-fn">'+esc(f.label)+' '+esc(f.impact||0)+'</i>').join('');
    const opp=(c.potential_opportunity||[]).map(s=>'<div class="dec-ctx opp">机会 · '+esc(s)+'</div>').join('');
    const risk=(c.potential_risk||[]).map(s=>'<div class="dec-ctx risk">风险 · '+esc(s)+'</div>').join('');
    const mon=c.what_to_monitor?'<div class="dec-ctx">监控 · '+esc(c.what_to_monitor)+'</div>':'';
    const step=c.recommended_next_step?'<div class="dec-step">下一步 · '+esc(c.recommended_next_step)+'</div>':'';
    return (fns?'<div class="dec-fns">'+fns+'</div>':'')+opp+risk+mon+step;
  }
  function render(box,data){
    const decisions=cardsFor(data,activeRole);
    const tabs='<div class="dec-roles">'+Object.keys(roleLabels).map(r=>'<button type="button" class="dec-role'+(r===activeRole?' on':'')+'" data-role="'+esc(r)+'">'+esc(roleLabels[r])+'</button>').join('')+'</div>';
    box.innerHTML='<div class="dec-head"><div><div class="di-kicker">DECISION INTELLIGENCE</div><h2>下一步关注</h2><p>同一事件按角色分发视角：'+esc(roleLabels[activeRole])+'视图。数据同源、建议仅供参考，不替代业务决策。</p></div></div>'+tabs+
      (decisions.length?'<div class="dec-list">'+decisions.map(x=>'<div class="dec-row"><div><strong>'+esc(x.action)+'</strong><small>'+esc(labels[x.urgency]||x.urgency)+' · '+esc(x.basis?.temporal_phase||'')+' · 可信度 '+esc(x.basis?.trust_level||'')+'</small></div><span>'+esc(x.urgency_label||'')+'</span></div><div class="dec-basis">依据：情报 '+esc(x.basis?.intelligence_score||0)+' · 趋势信号 '+esc(x.basis?.signal_strength||0)+'</div>'+contextHtml(x)).join('')+'</div>':'<p class="dec-empty">该角色暂无达到行动阈值的事件。</p>');
    box.querySelectorAll('.dec-role').forEach(btn=>btn.addEventListener('click',()=>{activeRole=btn.dataset.role;render(box,data);}));
  }
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now()); if(!res.ok)return;
      const data=await res.json();
      const host=document.querySelector('.app-layout')||document.querySelector('main'); if(!host||document.querySelector('#decision-intelligence'))return;
      const box=document.createElement('section'); box.id='decision-intelligence';
      render(box,data);
      host.parentNode.insertBefore(box,host);
      const style=document.createElement('style');style.textContent='#decision-intelligence{margin:18px auto 24px;max-width:1180px;padding:20px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:#fff;box-shadow:0 8px 30px rgba(20,40,60,.05)}#decision-intelligence h2{margin:2px 0 4px;font-size:21px}#decision-intelligence p{margin:0;color:#64748b;font-size:12px}.dec-roles{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.dec-role{border:1px solid #dbe4ec;background:#f8fafc;color:#475569;font-size:10px;padding:4px 10px;border-radius:999px;cursor:pointer}.dec-role.on{background:#0f2c44;color:#fff;border-color:#0f2c44}.dec-list{display:grid;gap:8px;margin-top:12px}.dec-row{display:flex;justify-content:space-between;gap:14px;padding-top:9px;border-top:1px solid #eef2f5}.dec-row>div{display:grid;gap:3px}.dec-row strong{font-size:12px}.dec-row small{font-size:9px;color:#64748b}.dec-row>span{font-weight:800;font-size:10px;color:#475569}.dec-basis{font-size:9px;color:#94a3b8;margin-left:0}.dec-fns{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.dec-fn{font-style:normal;font-size:9px;color:#0f2c44;background:#eef4fa;border:1px solid #d7e5f2;border-radius:4px;padding:1px 6px}.dec-ctx{font-size:9px;color:#64748b;margin-top:3px}.dec-ctx.opp{color:#1a7f4b}.dec-ctx.risk{color:#b3452e}.dec-step{font-size:9px;color:#0f2c44;margin-top:4px;font-weight:600}.dec-empty{font-size:11px;margin-top:8px}';document.head.appendChild(style);
    }catch(e){console.warn('Decision Intelligence unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
