'use strict';
if(el('filter-form')) (()=>{
  const chosen=new Set();
  let page=1,total=0,shown=[],applied=new URLSearchParams(),recordRequest=0,chartRequest=0,previewRequest=0;
  let chartData=null,chartSvg=null,previewState=null;
  const messages=message=>{el('error').textContent=message;};
  const guard=operation=>Promise.resolve().then(operation).catch(error=>messages(error.message));
  const params=()=>new URLSearchParams(applied);
  const inputParams=()=>new URLSearchParams([...new FormData(el('filter-form'))].filter(([,v])=>v));
  const model=r=>[r['conditions.model_identity.provider'],r['conditions.model_identity.model_id']].filter(Boolean).join(' / ')||'未记录';
  const fmt=window.ChefJeffCharts.fmt;
  const formValue=(name,value)=>{el('filter-form').elements.namedItem(name).value=value;};

  function staleChart(message='范围或选择已改变，请重新生成图表。'){
    chartRequest++;chartData=null;chartSvg=null;
    el('chart-output').replaceChildren();el('chart-data').replaceChildren();
    document.querySelector('.chart-data-wrap').hidden=true;
    el('chart-status').textContent=message;el('download-svg').disabled=true;el('download-csv').disabled=true;
  }
  function selection(){
    el('selected-count').textContent=`已选 ${chosen.size} / 50 条`;
    el('download-selected').disabled=!chosen.size;
    el('select-page').checked=!!shown.length&&shown.every(r=>chosen.has(r.ref));
    el('select-page').indeterminate=shown.some(r=>chosen.has(r.ref))&&!el('select-page').checked;
    for(const box of document.querySelectorAll('[data-record-ref]'))box.checked=chosen.has(box.dataset.recordRef);
  }
  function select(ref,checked){
    if(checked&&chosen.size>=50&&!chosen.has(ref)){messages('一次最多选择50条记录；可以先下载这一批，再继续选择。');return;}
    checked?chosen.add(ref):chosen.delete(ref);
    if(el('chart-population').value==='selected')staleChart();
  }
  function selectedDownload(refs){
    if(!refs.length)return messages('请先勾选记录。');
    const form=document.createElement('form');form.method='POST';form.action=base+'download/selected.cjresearch.zip';form.target='_blank';
    const field=document.createElement('input');field.type='hidden';field.name='refs';field.value=JSON.stringify(refs);form.append(field);
    document.body.append(form);form.submit();form.remove();
  }
  function nativeDownload(url){
    const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';document.body.append(a);a.click();a.remove();
  }
  function saveBlob(raw,type,name){
    const url=URL.createObjectURL(new Blob([raw],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function options(){
    const data=await request('api/options'),select=el('filter-form').elements.namedItem('level');
    const existing=select.value;select.replaceChildren(new Option('全部关卡',''));
    for(const level of data.levels)select.add(new Option(`第 ${level} 关`,String(level)));
    if(existing&&!data.levels.map(String).includes(existing))select.add(new Option(`第 ${existing} 关（当前无有效记录）`,existing));
    select.value=existing;
    for(const [id,catalog] of [['chart-group',data.groups],['chart-metric',data.metrics]]){
      const control=el(id),value=control.value;control.replaceChildren(...Object.entries(catalog).map(([key,label])=>new Option(typeof label==='string'?label:label.label,key)));control.value=value||control.options[0].value;
    }
  }
  async function usage(){
    el('refresh').disabled=true;
    try{
      const data=await request('api/usage'),u=data.usage,shared=u.shared&&u.scope==='global';
      el('usage-status').textContent=`${shared?'两站汇总':'暂为本站统计'} · ${u.synchronized?'已同步':'共享同步未确认'} · 获取于 ${date(data.fetched_at)} UTC · 统计起于 ${date(u.tracking_since)} UTC`;
      const labels=[['页面访问','page_views'],['开局局数','started_rounds'],['自然完成','completed_rounds'],['试玩浏览器（估算）','estimated_player_browsers'],['访问浏览器（估算）','estimated_visitor_browsers'],['运行中会话（估算）','running_sessions']];
      el('cards').replaceChildren(...labels.map(([label,key])=>{const card=text('div','','card');card.append(text('p',label),text('strong',Number.isFinite(u[key])?fmt(u[key]):'—'));return card;}));
      el('usage-detail').textContent=JSON.stringify({levels:u.levels,round_outcomes:u.round_outcomes,durations:u.durations},null,2);
    }finally{el('refresh').disabled=false;}
  }
  async function regionalUsage(){
    try{
      const data=await request('api/regional-usage');
      el('regional-status').textContent=data.note;
      el('regional-rows').replaceChildren(...data.sites.map(r=>{const row=document.createElement('tr');for(const value of [r.label,r.page_views,r.started_rounds,r.completed_rounds,r.estimated_player_browsers])row.append(text('td',typeof value==='number'?fmt(value):value));return row;}));
    }catch(error){el('regional-status').textContent='分站统计暂时不可用：'+error.message;}
  }
  async function records(){
    const serial=++recordRequest,query=params();query.set('page',page);
    el('record-status').textContent='正在获取记录…';
    const data=await request('api/records?'+query);if(serial!==recordRequest)return;
    total=data.total;shown=data.records;
    el('record-status').textContent=total?`筛选结果共 ${total} 条有效记录`:'当前筛选条件下没有有效记录。';
    el('record-rows').replaceChildren(...shown.map(r=>{
      const row=document.createElement('tr'),check=document.createElement('input'),cell=document.createElement('td');
      check.type='checkbox';check.className='select-box';check.dataset.recordRef=r.ref;check.setAttribute('aria-label',`选择 ${date(r.started_at)} 第${r.level}关 ${r.ref.slice(0,6)}`);
      check.addEventListener('change',()=>{select(r.ref,check.checked);selection();});cell.append(check);row.append(cell,text('td',date(r.started_at)),text('td',r.level??'未知'),text('td',r.site_label||'来源未知'));
      row.append(text('td',model(r),'model-cell'));
      const quality=document.createElement('td'),old=r.schema==='chefjeff-pilot-session-v1';
      quality.append(text('span',old?'旧版 · 未知':r['quality.complete']?'完整':'不完整快照',old||!r['quality.complete']?'badge warn':'badge'));
      row.append(quality,text('td',Number.isFinite(r.duration)?fmt(r.duration)+' 秒':'未记录'),text('td',date(r.expires,true)));
      const actions=text('td','','record-actions'),view=text('button','预览','secondary'),download=text('button','下载本条','quiet');
      view.type=download.type='button';view.addEventListener('click',()=>guard(()=>openPreview(r.ref)));download.addEventListener('click',()=>selectedDownload([r.ref]));
      actions.append(view,download);row.append(actions);return row;
    }));
    el('page-status').textContent=`第 ${page} / ${Math.max(1,Math.ceil(total/50))} 页`;
    el('previous').disabled=page<=1;el('next').disabled=page*50>=total;el('download').disabled=!total;selection();
  }
  function applyFilters(){applied=inputParams();page=1;chosen.clear();selection();staleChart();return Promise.all([records(),options()]);}
  el('filter-form').addEventListener('submit',event=>{event.preventDefault();messages('');guard(applyFilters);});
  el('previous').addEventListener('click',()=>{if(page>1){page--;guard(records);}});
  el('next').addEventListener('click',()=>{if(page*50<total){page++;guard(records);}});
  el('select-page').addEventListener('change',()=>{const checked=el('select-page').checked;for(const row of shown)select(row.ref,checked);selection();});
  el('clear-selection').addEventListener('click',()=>{chosen.clear();selection();if(el('chart-population').value==='selected')staleChart();});
  el('download-selected').addEventListener('click',()=>selectedDownload([...chosen]));
  el('download').addEventListener('click',()=>nativeDownload(base+'download/research.cjresearch.zip?'+params()));
  el('refresh').addEventListener('click',()=>{messages('');guard(usage);guard(regionalUsage);guard(options);});

  function tab(name){
    for(const button of document.querySelectorAll('[data-tab]')){const active=button.dataset.tab===name;button.setAttribute('aria-selected',String(active));el('panel-'+button.dataset.tab).hidden=!active;}
  }
  for(const button of document.querySelectorAll('[data-tab]'))button.addEventListener('click',()=>tab(button.dataset.tab));
  function previewSummary(data){
    const r=data.metadata,identity=r.conditions?.model_identity;
    const values=[['开始时间 · UTC',date(r.started_at)],['结束时间 · UTC',date(r.ended_at)],['关卡',r.level??'未知'],['游戏入口',data.site_label],['模型',identity?[identity.provider,identity.model_id].filter(Boolean).join(' / '):'未采集'],['记录时长',Number.isFinite(r.duration)?fmt(r.duration)+' 秒':'未知'],['出餐数',r.result?.served??'未知'],['金额',r.result?.money??'未知'],['胜负',r.ended_at&&typeof r.result?.won==='boolean'?(r.result.won?'获胜':'未获胜'):'尚未记录结束胜负'],['完整性',data.legacy?'旧版，完整性未知':r.quality?.complete?'完整':'不完整快照'],['结束原因',r.termination?.session_close?.reason??'未知'],['到期时间 · UTC',date(data.expires,true)]];
    el('preview-summary').replaceChildren(...values.map(([label,value])=>{const group=document.createElement('div');group.append(text('dt',label),text('dd',String(value)));return group;}));
    el('preview-metadata').textContent=JSON.stringify(r,null,2);
    el('preview-config').textContent=data.config?JSON.stringify(data.config,null,2):'这条旧记录未采集完整配置；不会使用当前关卡配置补填。';
  }
  async function loadPreview(){
    if(!previewState)return;
    const current={...previewState},serial=++previewRequest;
    el('preview-status').textContent='正在读取记录…';
    const query=new URLSearchParams({ref:current.ref,offset:current.offset,type:current.type});
    const data=await request('api/preview?'+query);if(serial!==previewRequest||!previewState||current.ref!==previewState.ref)return;
    el('preview-title').textContent=`第 ${data.metadata.level??'?'} 关 · ${date(data.metadata.started_at)}`;
    el('preview-status').textContent=`${data.site_label} · 引用 ${data.ref} · 到期 ${date(data.expires,true)} UTC${data.legacy?' · 旧记录的缺失字段保持未知':''}`;
    previewSummary(data);
    const typeSelect=el('event-type');typeSelect.replaceChildren(new Option('全部类型',''),...data.event_types.map(t=>new Option(t,t)));typeSelect.value=current.type;
    el('event-count').textContent=`当前类型共 ${data.event_total} 个事件`;
    el('event-list').replaceChildren(...data.events.map(event=>{const details=text('details','','event-item');details.append(text('summary',`#${event.seq??'?'} · ${event.type??'未知类型'} · 游戏时间 ${event.game_time_ms??'未知'} ms`),text('pre',JSON.stringify(event,null,2)));return details;}));
    if(!data.events.length)el('event-list').append(text('p',data.legacy?'此版本没有采集可在此分页预览的事件流；其他已有字段可在完整元数据中查看。':'当前筛选没有事件。','muted'));
    el('event-page').textContent=`第 ${Math.floor(current.offset/50)+1} / ${Math.max(1,Math.ceil(data.event_total/50))} 页`;
    el('event-previous').disabled=current.offset===0;el('event-next').disabled=current.offset+50>=data.event_total;
  }
  async function openPreview(ref){
    previewState={ref,offset:0,type:''};tab('summary');el('preview-dialog').showModal();
    try{await loadPreview();}catch(error){el('preview-status').textContent=error.message;throw error;}
  }
  el('preview-close').addEventListener('click',()=>el('preview-dialog').close());
  el('preview-dialog').addEventListener('close',()=>{previewRequest++;previewState=null;for(const id of ['preview-summary','preview-metadata','preview-config','event-list'])el(id).replaceChildren();});
  el('preview-download').addEventListener('click',()=>{if(previewState)selectedDownload([previewState.ref]);});
  el('event-type').addEventListener('change',()=>{if(previewState){previewState.type=el('event-type').value;previewState.offset=0;guard(loadPreview);}});
  el('event-previous').addEventListener('click',()=>{if(previewState&&previewState.offset>0){previewState.offset-=50;guard(loadPreview);}});
  el('event-next').addEventListener('click',()=>{if(previewState){previewState.offset+=50;guard(loadPreview);}});

  function chartControls(){
    const line=el('chart-kind').querySelector('option[value=line]');line.disabled=el('chart-group').value!=='day';
    if(line.disabled&&el('chart-kind').value==='line')el('chart-kind').value='bar';
  }
  el('chart-group').addEventListener('change',()=>{chartControls();staleChart('图表设置已变，请重新生成。');});
  for(const id of ['chart-population','chart-metric','chart-kind'])el(id).addEventListener('change',()=>staleChart('图表设置已变，请重新生成。'));
  function settings(){return {format:'chefjeff-admin-chart-v1',filters:Object.fromEntries(applied),group:el('chart-group').value,metric:el('chart-metric').value,kind:el('chart-kind').value,population:el('chart-population').value};}
  function validateSettings(value){
    if(!value||value.format!=='chefjeff-admin-chart-v1'||Object.keys(value).some(k=>!['format','filters','group','metric','kind','population'].includes(k)))throw new Error('不支持的图表配置。');
    if(!value.filters||Array.isArray(value.filters)||typeof value.filters!=='object')throw new Error('配置的筛选格式无效。');
    for(const [key,v] of Object.entries(value.filters)){
      if(typeof v!=='string'||v.length>80||!['since','until','level','schema','site'].includes(key))throw new Error('配置含不支持的筛选。');
      if((key==='since'||key==='until')&&!/^\d{4}-\d{2}-\d{2}$/.test(v))throw new Error('配置日期无效。');
      if(key==='since'||key==='until'){
        const date=new Date(v+'T00:00:00Z');
        if(Number.isNaN(date.valueOf())||date.toISOString().slice(0,10)!==v)throw new Error('配置包含不存在的日期。');
      }
      if(key==='level'&&!/^[1-9]\d{0,5}$/.test(v))throw new Error('配置关卡无效。');
      if(key==='schema'&&!['chefjeff-pilot-session-v1','chefjeff-pilot-session-v2'].includes(v))throw new Error('配置版本无效。');
      if(key==='site'&&!['cn','global','unknown'].includes(v))throw new Error('配置站点无效。');
    }
    if(value.filters.since&&value.filters.until&&value.filters.since>value.filters.until)throw new Error('配置的开始日期晚于结束日期。');
    for(const [key,id] of [['group','chart-group'],['metric','chart-metric'],['kind','chart-kind'],['population','chart-population']])if(![...el(id).options].some(o=>o.value===value[key]))throw new Error('配置含不支持的图表字段。');
    return value;
  }
  async function applySettings(value){
    validateSettings(value);
    for(const key of ['since','until','level','schema','site']){
      const control=el('filter-form').elements.namedItem(key),v=value.filters[key]||'';
      if(key==='level'&&v&&![...control.options].some(o=>o.value===v))control.add(new Option(`第 ${v} 关`,v));control.value=v;
    }
    for(const [key,id] of [['group','chart-group'],['metric','chart-metric'],['kind','chart-kind'],['population','chart-population']])el(id).value=value[key];
    chartControls();await applyFilters();
  }
  async function makeChart(){
    const query=params();query.set('group',el('chart-group').value);query.set('metric',el('chart-metric').value);
    if(el('chart-population').value==='selected'){
      if(!chosen.size)throw new Error('请先勾选要分析的记录，或将范围改为全部筛选结果。');
      query.set('refs',JSON.stringify([...chosen]));
    }
    staleChart('正在计算整个范围的贡献数据…');
    const serial=++chartRequest,kind=el('chart-kind').value;
    el('chart-status').textContent='正在计算整个范围的贡献数据…';
    const data=await request('api/analysis?'+query);if(serial!==chartRequest)return;
    chartData=data;chartSvg=null;el('chart-output').replaceChildren();
    const notes=[];
    if(kind!=='table'){
      const plot=window.ChefJeffCharts.render(data,kind);chartSvg=plot.svg;notes.push(...plot.notes);
      if(plot.svg)el('chart-output').append(plot.svg);else el('chart-output').append(text('p',plot.notes.join(' '),'muted'));
    }else el('chart-output').append(text('p','数据表见下方；可下载全部分组的CSV。','muted'));
    el('chart-status').textContent=`${data.filter_label} · ${data.population} · ${data.records} 条记录 · ${data.eligible} 个有效样本 · ${data.groups.length} 个分组。${notes.join(' ')}`;
    el('chart-value-heading').textContent=data.metric_label+' / '+data.unit;
    el('chart-data').replaceChildren(...data.groups.slice(0,300).map(g=>{const row=document.createElement('tr');for(const value of [g.label,g.records,g.eligible,g.excluded,fmt(g.value)])row.append(text('td',String(value)));return row;}));
    if(data.groups.length>300)el('chart-status').textContent+=' 数据表显示前300组，CSV保留全部。';
    document.querySelector('.chart-data-wrap').hidden=false;el('download-csv').disabled=!data.groups.length;el('download-svg').disabled=!chartSvg;
    try{localStorage.setItem('chefjeff-admin-chart-v1',JSON.stringify(settings()));}catch{}
  }
  el('chart-form').addEventListener('submit',event=>{event.preventDefault();messages('');guard(makeChart);});
  el('download-csv').addEventListener('click',()=>{if(chartData)saveBlob(window.ChefJeffCharts.csv(chartData),'text/csv;charset=utf-8','chefjeff-chart-data.csv');});
  el('download-svg').addEventListener('click',()=>guard(async()=>{
    if(!chartSvg)return;
    const svg=chartSvg.cloneNode(true),[font,license]=await Promise.all([fetch(base+'chefjeff-pixel.woff2').then(r=>{if(!r.ok)throw new Error('字体加载失败。');return r.arrayBuffer();}),fetch(base+'OFL.txt').then(r=>r.text())]);
    let encoded='';for(const byte of new Uint8Array(font))encoded+=String.fromCharCode(byte);
    const NS='http://www.w3.org/2000/svg',style=document.createElementNS(NS,'style'),metadata=document.createElementNS(NS,'metadata');
    style.textContent="@font-face{font-family:ChefJeffPixel;src:url(data:font/woff2;base64,"+btoa(encoded)+") format('woff2')}";
    metadata.textContent=license;svg.insertBefore(style,svg.firstChild);svg.append(metadata);
    saveBlob('<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(svg),'image/svg+xml;charset=utf-8','chefjeff-chart.svg');
  }));
  el('save-config').addEventListener('click',()=>saveBlob(JSON.stringify(settings(),null,2),'application/json','chefjeff-chart-config.json'));
  el('load-config').addEventListener('click',()=>el('config-file').click());
  el('config-file').addEventListener('change',()=>guard(async()=>{const file=el('config-file').files[0];if(!file)return;if(file.size>4096)throw new Error('配置文件过大；这里只接受图表配置JSON，不是研究记录。');await applySettings(JSON.parse(await file.text()));el('config-file').value='';}));
  async function initialize(){
    await options();
    let remembered=null;try{const raw=localStorage.getItem('chefjeff-admin-chart-v1');if(raw&&raw.length<4096)remembered=JSON.parse(raw);}catch{}
    if(remembered){try{await applySettings(remembered);}catch{await applyFilters();}}
    else await applyFilters();
    chartControls();
  }
  guard(usage);guard(regionalUsage);guard(initialize);
})();
