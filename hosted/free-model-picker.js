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
  // Settings has two choices per row, so it uses the short words.
  const SHORT={open:'有空位',full:'名额已满',off:'暂不可用'};
  function choice(m,f,c,current,picked,short=false){
    const [long,tone,usable]=status(f,m.provider),text=short?SHORT[tone]:long,b=document.createElement('button');
    b.type='button';b.setAttribute('aria-pressed',String(m.provider===current));
    b.disabled=!usable||!c.editable||busy;
    const name=document.createElement('span');name.className='name';name.textContent=m.name;
    const st=document.createElement('span');st.className='status '+tone;st.textContent=text;
    b.onclick=async()=>{if(await select(m.provider))picked?.();};
    return [b,name,st];
  }
  function render(){
    const list=el('free-model-list'),settings=el('settings-free');
    const c=state?.connection,f=catalog();
    for(const li of document.querySelectorAll('.free-limits-round'))
      if(f?.per_round_limit)li.textContent=`每局最多向模型请求 ${f.per_round_limit} 次，没成功的请求也算在内。`;
    if(settings)settings.hidden=!f?.enabled;
    if(!f?.enabled){list?.replaceChildren();el('settings-free-list')?.replaceChildren();return;}
    const note=message||(!c.editable?'本局模型已固定；结算后可选择另一模型。':'');
    const current=c.free_model?c.provider:'';
    if(list){
      el('free-model-reason').textContent=f.reason||'';
      el('free-model-message').textContent=note;
      list.replaceChildren(...f.models.map(m=>{
        const [b,name,st]=choice(m,f,c,current,()=>el('free-model-picker').close());
        const row=document.createElement('span');row.className='row';row.append(name,st);
        const detail=document.createElement('span');detail.className='detail';detail.textContent=[m.platform,m.model].filter(Boolean).join(' · ');
        b.append(row,detail);return b;
      }));
    }
    if(settings){
      el('settings-free-message').textContent=note;
      el('settings-free-list').replaceChildren(...f.models.map(m=>{
        const [b,name,st]=choice(m,f,c,current,null,true);b.title=[m.platform,m.model].filter(Boolean).join(' · ');
        b.append(name,st);return b;
      }));
    }
  }
  const open=id=>{const d=el(id);if(d&&!d.open)d.showModal();render();};
  window.addEventListener('kitchen-state',event=>{state=event.detail;render();});
  window.addEventListener('kitchen-open-free-models',()=>{if(catalog()?.enabled)open('free-model-picker');});
  window.addEventListener('kitchen-open-free-limits',()=>open('free-model-limits'));
  window.addEventListener('kitchen-select-free',event=>{select(event.detail?.provider);});
  document.addEventListener('DOMContentLoaded',()=>{
    el('free-model-close').onclick=()=>el('free-model-picker').close();
    el('free-limits-close').onclick=()=>el('free-model-limits').close();
    el('free-model-settings').onclick=()=>{el('free-model-picker').close();window.dispatchEvent(new CustomEvent('kitchen-open-connection',{detail:{view:'custom'}}));};
    render();
  });
})();
