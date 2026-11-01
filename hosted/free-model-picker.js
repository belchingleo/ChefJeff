/* Free trials use server-owned credentials. Selecting a model never calls an API.
   The list is whatever the server's catalog holds, so a newly connected model needs no page change. */
(() => {
  'use strict';
  const el=id=>document.getElementById(id);
  let state=null,busy=false,message='';
  const catalog=()=>state?.connection?.free_models;
  // The shop card's three words; only what the server reports, never "free to use" by default.
  function status(c,provider){
    const cap=c?.enabled&&c.gateway_available!==false?c.global_capacity?.[provider]:null;
    if(cap?.available)return ['● 有空位','open',true];
    if(cap?.reason==='seat_busy')return ['● 名额已满，稍后再试','full',true];
    return ['○ 暂不可用','off',false];
  }
  async function select(provider){
    const c=state?.connection;
    if(!c?.editable||busy||!catalog()?.models?.some(m=>m.provider===provider))return false;
    busy=true;message='正在选择…';render();
    try{
      const d=await window.chefjeffHostedRequest('/api/connection',{
        game_id:state.game_id,request_id:crypto.randomUUID(),free_provider:provider});
      state={...state,connection:d.connection};message='';
      window.dispatchEvent(new CustomEvent('kitchen-state',{detail:state}));
      return true;
    }catch(_){message='模型选择未完成，请刷新厨房状态后重试。';return false;}
    finally{busy=false;render();}
  }
  function render(){
    const list=el('free-model-list');if(!list)return;
    const c=state?.connection,f=catalog();
    const limit=el('free-limits-round');
    if(limit&&f?.per_round_limit)limit.textContent=`每局最多向模型请求 ${f.per_round_limit} 次，没成功的请求也算在内。`;
    if(!f?.enabled){list.replaceChildren();return;}
    el('free-model-reason').textContent=f.reason||'';
    el('free-model-message').textContent=message||(!c.editable?'本局模型已固定；结算后可选择另一模型。':'');
    const current=c.free_model?c.provider:'';
    list.replaceChildren(...f.models.map(m=>{
      const [text,tone,usable]=status(f,m.provider),b=document.createElement('button');
      b.type='button';b.setAttribute('aria-pressed',String(m.provider===current));
      b.disabled=!usable||!c.editable||busy;
      const row=document.createElement('span');row.className='row';
      const name=document.createElement('span');name.className='name';name.textContent=m.name;
      const st=document.createElement('span');st.className='status '+tone;st.textContent=text;
      row.append(name,st);
      const detail=document.createElement('span');detail.className='detail';detail.textContent=[m.platform,m.model].filter(Boolean).join(' · ');
      b.append(row,detail);
      b.onclick=async()=>{if(await select(m.provider))el('free-model-picker').close();};
      return b;
    }));
  }
  const open=id=>{const d=el(id);if(d&&!d.open)d.showModal();render();};
  window.addEventListener('kitchen-state',event=>{state=event.detail;render();});
  window.addEventListener('kitchen-open-free-models',()=>{if(catalog()?.enabled)open('free-model-picker');});
  window.addEventListener('kitchen-open-free-limits',()=>open('free-model-limits'));
  window.addEventListener('kitchen-select-free',event=>{select(event.detail?.provider);});
  document.addEventListener('DOMContentLoaded',()=>{
    el('free-model-close').onclick=()=>el('free-model-picker').close();
    el('free-limits-close').onclick=()=>el('free-model-limits').close();
    el('free-model-settings').onclick=()=>{el('free-model-picker').close();window.dispatchEvent(new CustomEvent('kitchen-open-connection'));};
    render();
  });
})();
