// Recompile script modules while retaining the reviewed scene, engine and component UUID.
// Requires TypeScript 5.9.3. A full Creator build remains scripts/build_cocos.py.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),ts=require('typescript');
if(ts.version!=='5.9.3')throw new Error('Use TypeScript 5.9.3 for this reproducible fallback.');
const root=path.resolve(__dirname,'..'),web=path.join(root,'cocos-kitchen/build/web');
// md5Cache builds name files by content (index.<v>.js); one match each, found by pattern.
const built=(dir,re)=>{const found=fs.readdirSync(path.join(web,dir)).filter(n=>re.test(n));
 if(found.length!==1)throw new Error('Expected one '+re+' in '+dir+', found '+found.length);return path.join(web,dir,found[0]);};
const bundle=built('assets/main',/^index(\.[0-9a-f]{5})?\.js$/);
let content=fs.readFileSync(bundle,'utf8');
for(const name of ['KitchenAudio','LevelOneArt','KitchenClient']){
 const source=fs.readFileSync(path.join(root,'cocos-kitchen/assets/scripts',name+'.ts'),'utf8');
 const id='chunks:///_virtual/'+name+'.ts';
 let input=source;
 if(name==='KitchenClient'){
  // This component has only @ccclass, no serialized @property declarations.
  if([...source.matchAll(/^\s*@\w+/gm)].length!==1)throw new Error('Serialized/decorated properties require a Creator build.');
  const uuid=JSON.parse(fs.readFileSync(path.join(root,'cocos-kitchen/assets/scripts',name+'.ts.meta'),'utf8')).uuid.replaceAll('-','');
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let compressed=uuid.slice(0,5);
  for(let i=5;i<32;i+=3){const value=parseInt(uuid.slice(i,i+3),16);compressed+=alphabet[value>>6]+alphabet[value&63];}
  const current=content.match(/_RF\.push\(\{\},\s*["']([^"']+)["'],\s*["']KitchenClient["']/);
  if(!current||current[1]!==compressed)throw new Error('Component UUID differs from the reviewed scene build.');
  input="import {cclegacy as __metadata} from 'cc';\n"+`__metadata._RF.push({}, ${JSON.stringify(compressed)}, 'KitchenClient', undefined);\n`+source+'\n__metadata._RF.pop();\n';
 }
 const result=ts.transpileModule(input,{moduleName:id,fileName:name+'.ts',reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.System,target:ts.ScriptTarget.ES2017,experimentalDecorators:true}});
 if(result.diagnostics.some(d=>d.category===ts.DiagnosticCategory.Error))throw new Error('Transpile failed: '+name);
 const hash=crypto.createHash('sha256').update(source).digest('hex');
 let output=result.outputText.replace('\n','\n    // source-sha256: '+hash+'\n');
 for(const dependency of ['KitchenAudio','LevelOneArt','KitchenGeometry'])output=output.replaceAll('"./'+dependency+'"','"./'+dependency+'.ts"');
 const starts=[...content.matchAll(/^System\.register\("([^\"]+)"/gm)];
 const index=starts.findIndex(m=>m[1]===id);
 if(index<0)throw new Error('Expected existing Cocos module: '+id);
 const start=starts[index].index,end=index+1<starts.length?starts[index+1].index:content.length;
 content=content.slice(0,start)+output+'\n'+content.slice(end);
}
fs.writeFileSync(bundle,content);
// Hashed names are cached for a year, so changed content needs a new name all the way up to index.html:
// index.<v>.js and config.<v>.json (bundleVers.main) -> settings.<s>.json -> application.<a>.js -> index.html.
const tag=text=>crypto.createHash('md5').update(text).digest('hex').slice(0,5);
const rename=(file,next)=>{const to=file.replace(/\.[0-9a-f]{5}(\.[a-z]+)$/,'.'+next+'$1');if(to!==file)fs.renameSync(file,to);return to;};
const old=path.basename(bundle).match(/^index\.([0-9a-f]{5})\.js$/)?.[1];
if(old){
 const main=tag(content);
 rename(bundle,main);rename(built('assets/main',/^config\.[0-9a-f]{5}\.json$/),main);
 const settingsFile=built('src',/^settings\.[0-9a-f]{5}\.json$/),settings=JSON.parse(fs.readFileSync(settingsFile,'utf8'));
 if(settings.assets?.bundleVers?.main!==old)throw new Error('settings bundleVers.main does not match '+old);
 settings.assets.bundleVers.main=main;
 const settingsText=JSON.stringify(settings,null,2)+'\n';fs.writeFileSync(settingsFile,settingsText);
 const settingsTo=rename(settingsFile,tag(settingsText));
 const app=built('.',/^application\.[0-9a-f]{5}\.js$/);
 const appText=fs.readFileSync(app,'utf8').replace(path.basename(settingsFile),path.basename(settingsTo));
 fs.writeFileSync(app,appText);const appTo=rename(app,tag(appText));
 const page=path.join(web,'index.html');
 fs.writeFileSync(page,fs.readFileSync(page,'utf8').replace(path.basename(app),path.basename(appTo)));
}
console.log('Recompiled presentation/client scripts; reviewed scene, engine and component UUID retained.');
