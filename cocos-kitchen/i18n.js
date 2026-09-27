/* Display-only localization. No game state, API inputs or logs are rewritten. */
(function (root) {
  'use strict';
  const catalog = __KITCHEN_CATALOG__;
  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const templates = catalog.templates.map(([source, target]) => {
    const ids = [];
    const pattern = source.split(/(\{\d+\})/).map(part => {
      if (/^\{\d+\}$/.test(part)) { ids.push(Number(part.slice(1,-1))); return '(.*?)'; }
      return escape(part);
    }).join('');
    return { source, target, ids, regex: new RegExp('^' + pattern + '$', 's') };
  }).sort((a,b) => b.source.replace(/\{\d+\}/g,'').length-a.source.replace(/\{\d+\}/g,'').length);
  const keys = Object.keys(catalog.messages).sort((a,b) => b.length-a.length);
  const fragments = new RegExp(keys.map(escape).join('|'),'g');
  let locale = 'zh';
  try { if (root.localStorage?.getItem('chefjeff-language') === 'en') locale='en'; } catch (_) {}
  function english(text, depth=0) {
    if (typeof text !== 'string' || !text || depth>8) return text;
    if (Object.prototype.hasOwnProperty.call(catalog.messages,text)) return catalog.messages[text];
    for (const rule of templates) {
      const match=text.match(rule.regex);
      if (!match) continue;
      const args={}; rule.ids.forEach((id,i) => { args[id]=match[i+1]; });
      return rule.target.replace(/\{(\d+)\}/g,(_,id) =>
        rule.source.startsWith('已连接：') && id==='0' ? args[id] : english(args[id],depth+1));
    }
    if (text.includes('\n')) return text.split('\n').map(line=>english(line,depth+1)).join('\n');
    if (text.startsWith('空格 · ')) return 'Space · '+english(text.slice(5),depth+1);
    return text.replace(fragments,key=>catalog.messages[key]);
  }
  const cache=new Map();
  function translate(text){
    if(locale!=='en')return text;
    if(cache.has(text))return cache.get(text);
    const value=english(text);if(cache.size>=512)cache.clear();cache.set(text,value);return value;
  }
  root.kitchenI18n = { t:translate, english, get language(){return locale;}, setLanguage };
  if (typeof module !== 'undefined') module.exports=root.kitchenI18n;
  const doc=root.document;
  const sources=new WeakMap(), attributes=new WeakMap();
  function textNode(node) {
    if (!node.parentElement || node.parentElement.closest('script,style,textarea,[data-no-i18n]')) return;
    let row=sources.get(node);
    if (!row || node.nodeValue!==row.rendered) row={source:node.nodeValue,rendered:node.nodeValue};
    row.rendered=translate(row.source);sources.set(node,row);
    if (node.nodeValue!==row.rendered) node.nodeValue=row.rendered;
  }
  function element(el) {
    if (el.nodeType!==1 || el.closest('script,style,textarea,[data-no-i18n]')) return;
    let rows=attributes.get(el)||{};
    for (const name of ['placeholder','aria-label','title']) {
      if (!el.hasAttribute(name)) continue;
      let row=rows[name],current=el.getAttribute(name);
      if (!row || current!==row.rendered) row={source:current};
      row.rendered=translate(row.source);rows[name]=row;
      if (current!==row.rendered) el.setAttribute(name,row.rendered);
    }
    attributes.set(el,rows);
  }
  function walk(node) {
    if (node.nodeType===3) {textNode(node);return;}
    if (node.nodeType!==1 || node.matches('script,style,textarea,[data-no-i18n]')) return;
    element(node); for (const child of node.childNodes) walk(child);
  }
  function chrome() {
    doc.documentElement.lang=locale==='en'?'en':'zh-CN';
    doc.title=locale==='en'?'ChefJeff · Cook together':'ChefJeff · 一起出餐';
    const toggle=doc.getElementById('kitchen-language');
    if(toggle){toggle.textContent=locale==='en'?'中文':'English';toggle.setAttribute('aria-label',locale==='en'?'切换到中文':'Switch to English');}
  }
  function setLanguage(next) {
    if (!['zh','en'].includes(next)) return;
    locale=next;try{root.localStorage?.setItem('chefjeff-language',locale);}catch(_){}
    if(doc){walk(doc.body);chrome();root.dispatchEvent(new CustomEvent('kitchen-language-changed',{detail:locale}));}
  }
  if (doc) {
    function mount() {
      walk(doc.body);chrome();
      const toggle=doc.getElementById('kitchen-language');
      if(toggle)toggle.addEventListener('click',()=>setLanguage(locale==='en'?'zh':'en'));
      // Only changed DOM nodes are translated; no frame loop or game-state mutation.
      new MutationObserver(records=>{
        for(const record of records){
          if(record.type==='characterData')textNode(record.target);
          else if(record.type==='attributes')element(record.target);
          else for(const node of record.addedNodes)walk(node);
        }
      }).observe(doc.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title']});
    }
    if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
  }
})(typeof window !== 'undefined' ? window : globalThis);
