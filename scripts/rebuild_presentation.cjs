// Cloud fallback for two plain TypeScript classes; scene/engine code is left intact.
// Requires TypeScript 5.9.3. A full Creator build remains scripts/build_cocos.py.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),ts=require('typescript');
if(ts.version!=='5.9.3')throw new Error('Use TypeScript 5.9.3 for this reproducible fallback.');
const root=path.resolve(__dirname,'..'),bundle=path.join(root,'cocos-kitchen/build/web/assets/main/index.js');
let content=fs.readFileSync(bundle,'utf8');
for(const name of ['KitchenAudio','LevelOneArt']){
 const source=fs.readFileSync(path.join(root,'cocos-kitchen/assets/scripts',name+'.ts'),'utf8');
 const id='chunks:///_virtual/'+name+'.ts';
 const result=ts.transpileModule(source,{moduleName:id,fileName:name+'.ts',reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.System,target:ts.ScriptTarget.ES2017}});
 if(result.diagnostics.some(d=>d.category===ts.DiagnosticCategory.Error))throw new Error('Transpile failed: '+name);
 const hash=crypto.createHash('sha256').update(source).digest('hex');
 const output=result.outputText.replace('\n','\n    // source-sha256: '+hash+'\n');
 const starts=[...content.matchAll(/^System\.register\("([^\"]+)"/gm)];
 const index=starts.findIndex(m=>m[1]===id);
 if(index<0)throw new Error('Expected existing Cocos module: '+id);
 const start=starts[index].index,end=index+1<starts.length?starts[index+1].index:content.length;
 content=content.slice(0,start)+output+'\n'+content.slice(end);
}
fs.writeFileSync(bundle,content);
console.log('Recompiled KitchenAudio and LevelOneArt from source; other Cocos modules retained.');
