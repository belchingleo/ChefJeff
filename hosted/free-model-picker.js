/* Free trials use server-owned credentials. Selecting a model never calls an API. */
(() => {
  'use strict';
  const el=id=>document.getElementById(id);
  let state=null,busy=false,message='';
  function render(){
    const box=el('free-model-picker');if(!box)return;
    const c=state?.connection,catalog=c?.free_models;
    box.hidden=!catalog?.enabled;
    if(box.hidden)return;
    const current=catalog.models.find(m=>m.provider===c.provider);
    const selected=catalog.models.find(m=>m.provider===catalog.default);
    const editable=!!c.editable&&!busy;
    el('free-model-current').textContent=c.free_model&&current?
      '当前：'+current.name+'（'+current.platform+'）':'当前使用自有模型配置';
    el('free-model-default').textContent=selected?'默认：'+selected.name+'（'+selected.platform+'）':'';
    el('free-model-reason').textContent=catalog.reason;
    el('free-model-note').textContent=catalog.note;
    for(const provider of ['zhipu','startlux']){
      const button=el('free-model-'+provider);
      const capacity=catalog.global_capacity?.[provider];
      const label=provider==='zhipu'?'智谱 · GLM-4.7-Flash':'StartLux · Bamboo';
      button.textContent=label+(capacity?(capacity.available?' · 可用':capacity.reason==='seat_busy'?' · 名额已满':' · 暂不可用'):'');
      button.disabled=!editable||catalog.gateway_available===false;
      button.setAttribute('aria-pressed',String(c.free_model&&c.provider===provider));
    }
    el('free-model-message').textContent=message||(!c.editable?'本局模型已固定；结算后可选择另一模型。':'开局前一键选择，本局使用同一个模型。');
    // Keep the kitchen unobstructed during play; identity remains visible in Settings.
    box.hidden=!['ready','ended'].includes(state.phase);
  }
  window.addEventListener('kitchen-state',event=>{state=event.detail;render();});
  document.addEventListener('DOMContentLoaded',()=>{
    for(const provider of ['zhipu','startlux'])el('free-model-'+provider).onclick=async()=>{
      if(!state?.connection?.editable||busy)return;
      busy=true;message='正在选择…';render();
      try{
        const d=await window.chefjeffHostedRequest('/api/connection',{
          game_id:state.game_id,request_id:crypto.randomUUID(),free_provider:provider});
        state={...state,connection:d.connection};message='已选择。返回厨房即可开局。';
        window.dispatchEvent(new CustomEvent('kitchen-state',{detail:state}));
      }catch(_){message='模型选择未完成，请刷新厨房状态后重试。';}
      finally{busy=false;render();}
    };
    el('free-model-settings').onclick=()=>window.dispatchEvent(new CustomEvent('kitchen-open-connection'));
    render();
  });
})();
