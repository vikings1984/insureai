/* Local-first behavior learning. All feedback stays in this browser. */
(function () {
  const KEY = 'insureai_behavior_v1';
  const MAX_EVENTS = 200;
  const LIMIT = 6;
  function empty(){ return {version:1, events:[], topic:{}, entity:{}, type:{}}; }
  function load(){
    try {
      const value = JSON.parse(localStorage.getItem(KEY));
      return value && value.version === 1 ? value : empty();
    } catch(e){ return empty(); }
  }
  function save(state){ localStorage.setItem(KEY, JSON.stringify(state)); }
  function keys(event){
    return {
      topic: String(event.topic || '').toLowerCase(),
      entities: (event.entities || []).map(x => String(x).trim().toLowerCase()).filter(Boolean).slice(0, LIMIT),
      type: String(event.event_type || '').toLowerCase()
    };
  }
  function adjust(bucket, key, amount){
    if(!key) return;
    bucket[key] = Math.max(-12, Math.min(12, Number(bucket[key] || 0) + amount));
  }
  function record(action, event){
    if(!event || !['view','save','dismiss'].includes(action)) return;
    const state = load(), k = keys(event);
    const factor = action === 'dismiss' ? -1 : (action === 'save' ? 2 : 1);
    adjust(state.topic, k.topic, factor * 2);
    k.entities.forEach(x => adjust(state.entity, x, factor * 2));
    adjust(state.type, k.type, factor);
    state.events.push({action, event_id:event.event_id || '', at:Date.now()});
    state.events = state.events.slice(-MAX_EVENTS);
    save(state);
  }
  function boost(event){
    const state = load(), k = keys(event);
    let value = Number(state.topic[k.topic] || 0) + Number(state.type[k.type] || 0);
    k.entities.forEach(x => { value += Number(state.entity[x] || 0); });
    return Math.max(-20, Math.min(20, value));
  }
  function reset(){ localStorage.removeItem(KEY); }
  window.InsureAIBehavior = { load, record, boost, reset };
})();
