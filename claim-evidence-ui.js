/* Claim -> Evidence UI: render proposition-level claims (Claim Schema v3). */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const labels={cross_checked:'已交叉验证',single_source:'单一来源',conflicted:'证据冲突',unverified:'待验证'};
  const typeLabels={acquisition_intent:'收购意图',transaction_amount:'交易金额',transaction_scope:'交易标的',strategic_context:'战略意图',regulatory_action:'监管行动',fine_amount:'处罚金额',effective_date:'生效时间',product_launch:'产品发布',capital_raise:'融资',capital_amount:'融资金额',rating_change:'评级变动',executive_change:'人事变动',market_entry:'市场进入',loss_event:'损失事件',loss_amount:'损失金额',event_summary:'事件概要',reported_amount:'涉及金额',product_amount:'产品金额',rating_amount:'评级金额',market_amount:'涉及金额'};
  async function boot(){
    try{
      const data=await window.InsureAIData.load(); const events=Array.isArray(data.events)?data.events:[];
      const cards=[...document.querySelectorAll('#daily-intelligence .di-item')];
      const byTitle=new Map(events.map(e=>[String(e.title||''),e]));
      cards.forEach(card=>{
        const title=card.querySelector('h3')?.textContent||''; const event=byTitle.get(title); if(!event||card.querySelector('.claim-evidence'))return;
        const c=event.claims||{}; const claims=Array.isArray(c.claims)?c.claims:[];
        const conflicted=claims.filter(x=>x.verification_status==='conflicted').length;
        const box=document.createElement('div'); box.className='claim-evidence';
        box.innerHTML='<div class="ce-head"><b>关键命题</b><span>覆盖 '+esc(c.coverage||0)+'% · 交叉验证 '+esc(c.cross_checked||0)+(conflicted?' · <em class="ce-conflict">冲突 '+esc(conflicted)+'</em>':'')+'</span></div>' +
          (claims.length?'<div class="ce-list">'+claims.map(x=>{
            const text=x.claim_text||x.text||''; const status=x.verification_status||x.status||'';
            const contra=(x.contradicting_evidence||[]).length;
            const ctx=(x.context_evidence||[]).length;
            const tag=typeLabels[x.claim_type]?'<i class="ce-type">'+esc(typeLabels[x.claim_type])+'</i>':'';
            return '<div class="ce-row'+(status==='conflicted'?' ce-row-conflict':'')+'"><div><strong>'+esc(text)+'</strong><small>'+tag+esc(labels[status]||status||'')+' · 置信 '+esc(x.confidence==null?'-':x.confidence)+' · 支持 '+esc(x.evidence_count||0)+(contra?' · 矛盾 '+esc(contra):'')+(ctx?' · 关联 '+esc(ctx):'')+'</small></div><span>'+esc(x.independent_domains||0)+' 域</span></div>';
          }).join('')+'</div>':'<div class="ce-empty">暂无可拆分的事实命题。</div>');
        card.querySelector('.di-body')?.appendChild(box);
      });
      const style=document.createElement('style'); style.textContent='.claim-evidence{margin-top:10px;padding-top:9px;border-top:1px dashed #e2e8f0}.ce-head{display:flex;justify-content:space-between;gap:10px;font-size:10px}.ce-head b{color:#475569}.ce-head span{color:#94a3b8}.ce-head em{color:#b91c1c;font-style:normal}.ce-list{display:grid;gap:5px;margin-top:6px}.ce-row{display:flex;justify-content:space-between;gap:10px;padding:6px 0}.ce-row>div{display:grid;gap:2px}.ce-row strong{font-size:11px;font-weight:600;color:#334155}.ce-row small,.ce-row>span{font-size:9px;color:#64748b}.ce-row-conflict strong{color:#b91c1c}.ce-type{font-style:normal;background:#f1f5f9;border-radius:3px;padding:0 4px;margin-right:4px;color:#64748b}.ce-empty{font-size:10px;color:#94a3b8;margin-top:6px}'; document.head.appendChild(style);
    }catch(e){console.warn('Claim evidence UI unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,450));else setTimeout(boot,450);
})();
