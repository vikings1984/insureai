/* Temporal Intelligence UI: show trend phases without pretending to forecast. */
(function(){
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  const phases={accelerating:'加速形成',forming:'形成中',cooling:'降温',isolated:'孤立信号'};
  async function boot(){
    try{
      const res=await fetch('intelligence.json?t='+Date.now()); if(!res.ok)return;
      const data=await res.json(), t=data.temporal||{}, topics=Array.isArray(t.topic_signals)?t.topic_signals.slice(0,6):[], entities=Array.isArray(t.entity_momentum)?t.entity_momentum.slice(0,6):[];
      const host=document.querySelector('.app-layout')||document.querySelector('main'); if(!host||document.querySelector('#temporal-intelligence'))return;
      const box=document.createElement('section'); box.id='temporal-intelligence';
      box.innerHTML='<div class="ti-head"><div><div class="di-kicker">TEMPORAL INTELLIGENCE</div><h2>趋势与动量</h2><p>基于时间上的重复、确认和加速度，不等同于预测。</p></div></div><div class="ti-grid"><div><b>主题趋势</b><div class="ti-list">'+(topics.length?topics.map(x=>'<div class="ti-row"><div><strong>'+esc(x.topic)+'</strong><small>'+esc(phases[x.phase]||x.phase)+' · '+esc(x.current_period_count)+' vs '+esc(x.previous_period_count)+' · '+esc(x.change_pct)+'%</small></div><span>'+esc(x.signal_strength)+'</span></div>').join(''):'<p class="ti-empty">暂无足够时间序列数据。</p>')+'</div></div><div><b>实体动量</b><div class="ti-list">'+(entities.length?entities.map(x=>'<div class="ti-row"><div><strong>'+esc(x.entity)+'</strong><small>'+esc(x.event_count)+' 事件 · '+esc(x.event_type_count)+' 类事件</small></div><span>'+esc(x.momentum)+'</span></div>').join(''):'<p class="ti-empty">暂无足够实体历史数据。</p>')+'</div></div></div>';
      host.parentNode.insertBefore(box,host);
      const style=document.createElement('style'); style.textContent='#temporal-intelligence{margin:18px auto 24px;max-width:1180px;padding:20px 24px;border:1px solid rgba(80,110,140,.18);border-radius:16px;background:#fff;box-shadow:0 8px 30px rgba(20,40,60,.05)}#temporal-intelligence h2{margin:2px 0 4px;font-size:21px}#temporal-intelligence p{margin:0;color:#64748b;font-size:12px}.ti-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:14px}.ti-list{display:grid;gap:6px;margin-top:8px}.ti-row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid #eef2f5}.ti-row>div{display:grid;gap:2px}.ti-row strong{font-size:12px}.ti-row small{font-size:9px;color:#64748b}.ti-row>span{font-weight:800;font-size:12px;color:#475569}.ti-empty{font-size:11px;margin-top:8px}@media(max-width:700px){#temporal-intelligence{margin:12px 10px;padding:16px}.ti-grid{grid-template-columns:1fr}}';document.head.appendChild(style);
    }catch(e){console.warn('Temporal Intelligence unavailable:',e);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,550)); else setTimeout(boot,550);
})();
