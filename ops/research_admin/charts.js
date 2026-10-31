'use strict';
(() => {
  const NS='http://www.w3.org/2000/svg';
  const node=(tag,attrs={},content)=>{
    const n=document.createElementNS(NS,tag);
    for(const [key,value] of Object.entries(attrs))n.setAttribute(key,String(value));
    if(content!==undefined)n.textContent=content;
    return n;
  };
  const fmt=value=>value===null?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
  function render(data,kind){
    const notes=[];
    let groups=data.groups;
    if(kind==='line'){
      groups=groups.filter(g=>/^\d{4}-\d{2}-\d{2}$/.test(g.label)&&g.value!==null);
      notes.push('折线仅连接有有效数值的UTC日期；未知日期及缺失值保留在数据表中。');
    }
    if(groups.length>30){
      groups=data.group==='day'?groups.slice(-30):groups.slice(0,30);
      notes.push('图中显示'+(data.group==='day'?'最近':'前')+'30组；CSV仍包含全部分组。');
    }
    const values=groups.map(g=>g.value).filter(v=>Number.isFinite(v));
    if(!groups.length||!values.length)return {svg:null,notes:[...notes,'没有适用于该指标的有效数值；未知值不会画成0。']};
    const W=1100,H=450,L=88,R=30,T=58,B=112,pw=W-L-R,ph=H-T-B;
    let low=Math.min(0,...values),high=Math.max(0,...values);
    if(data.metric.endsWith('_rate')){low=0;high=100;}
    else if(data.metric==='records')high=Math.max(4,Math.ceil(high/4)*4);
    else if(high===low)high=low+1;
    const y=v=>T+(high-v)/(high-low)*ph;
    const zero=y(0);
    const svg=node('svg',{xmlns:NS,viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':data.metric_label+' · 按'+data.group_label,'font-family':'ChefJeffPixel,monospace'});
    svg.append(node('title',{},data.metric_label+'，按'+data.group_label+'分组'),node('rect',{width:W,height:H,fill:'#101d33'}));
    svg.append(node('text',{x:L,y:27,fill:'#fdf3e1','font-size':18},data.metric_label+' / '+data.unit));
    svg.append(node('text',{x:W-R,y:27,fill:'#b4c4df','font-size':12,'text-anchor':'end'},`图示 ${groups.length} / 全部 ${data.groups.length} 组`));
    for(let i=0;i<=4;i++){
      const value=low+(high-low)*i/4,yy=y(value);
      svg.append(node('line',{x1:L,y1:yy,x2:W-R,y2:yy,stroke:'#354f72','stroke-width':1}),node('text',{x:L-12,y:yy+4,fill:'#b4c4df','font-size':12,'text-anchor':'end'},fmt(value)));
    }
    svg.append(node('line',{x1:L,y1:zero,x2:W-R,y2:zero,stroke:'#829dc1','stroke-width':2}));
    const times=groups.map(g=>Date.parse(g.label+'T00:00:00Z'));
    const timeLow=Math.min(...times),timeHigh=Math.max(...times);
    const x=(g,i)=>kind==='line'?(timeHigh===timeLow?L+pw/2:L+(times[i]-timeLow)/(timeHigh-timeLow)*pw):L+(i+.5)*pw/groups.length;
    if(kind==='line')svg.append(node('polyline',{points:groups.map((g,i)=>`${x(g,i)},${y(g.value)}`).join(' '),fill:'none',stroke:'#e8983a','stroke-width':3}));
    const every=Math.max(1,Math.ceil(groups.length/12));
    groups.forEach((g,i)=>{
      const xx=x(g,i);
      const tooltip=`${g.label}：${fmt(g.value)} ${data.unit}；有效样本 ${g.eligible} / 贡献记录 ${g.records}`;
      if(g.value!==null){
        const yy=y(g.value);
        const shape=kind==='line'?node('rect',{x:xx-4,y:yy-4,width:8,height:8,fill:'#fdf3e1',stroke:'#e8983a','stroke-width':2}):node('rect',{x:xx-Math.min(52,pw/groups.length*.65)/2,y:Math.min(yy,zero),width:Math.min(52,pw/groups.length*.65),height:Math.abs(zero-yy),fill:'#2a5a9e',stroke:'#80a6d9','stroke-width':1});
        shape.append(node('title',{},tooltip));svg.append(shape);
      }
      if(groups.length<=14)svg.append(node('text',{x:xx,y:g.value===null?zero-9:y(g.value)+(g.value>=0?-10:18),fill:'#fdf3e1','font-size':12,'text-anchor':'middle'},fmt(g.value)));
      if(i%every===0||i===groups.length-1){
        const caption=g.label.length>17?g.label.slice(0,15)+'…':g.label;
        const label=node('text',{x:xx,y:H-B+22,fill:'#b4c4df','font-size':12,'text-anchor':'end',transform:`rotate(-30 ${xx} ${H-B+22})`},caption);
        label.append(node('title',{},g.label));svg.append(label);
      }
    });
    svg.append(node('text',{x:L,y:H-15,fill:'#b4c4df','font-size':12},`${data.population==='已选贡献记录'?'已选记录':'全部筛选结果'} · ${data.filter_label||''} · ${data.records} 条贡献 · 有效 ${data.eligible} · 非全站对局统计`));
    return {svg,notes};
  }
  function csv(data){
    const quote=value=>{
      let s=value===null?'':String(value);
      if(typeof value!=='number'&&(/^\s*[=+@\-]/.test(s)||/^[\t\r]/.test(s)))s="'"+s;
      return '"'+s.replaceAll('"','""')+'"';
    };
    const rows=[['数据范围','筛选范围','分组字段','分组','贡献记录数','有效样本','缺失/不适用',data.metric_label+' ('+data.unit+')']];
    for(const g of data.groups)rows.push([data.population,data.filter_label||'',data.group_label,g.label,g.records,g.eligible,g.excluded,g.value]);
    return '\uFEFF'+rows.map(row=>row.map(quote).join(',')).join('\r\n');
  }
  window.ChefJeffCharts={render,csv,fmt};
})();
