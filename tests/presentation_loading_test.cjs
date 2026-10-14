// Test the actual shipped modules: atlas order, missing assets and lazy audio.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
// Release builds name files by content (md5Cache): index.<hash>.js, bundle.<hash>.js.
const built=(dir,re)=>{const found=fs.readdirSync(dir).filter(n=>re.test(n));assert.equal(found.length,1,dir+' '+re);return dir+'/'+found[0];};
const bundle=fs.readFileSync(built('cocos-kitchen/build/web/assets/main',/^index(\.[0-9a-f]{5})?\.js$/),'utf8');
const clientHash=crypto.createHash('sha256').update(fs.readFileSync('cocos-kitchen/assets/scripts/KitchenClient.ts')).digest('hex');
assert(bundle.includes('source-sha256: '+clientHash),'KitchenClient source/build mismatch');
const helpers={};
vm.runInNewContext(fs.readFileSync(built('cocos-kitchen/build/web/src/chunks',/^bundle(\.[0-9a-f]{5})?\.js$/),'utf8'),{
 System:{register(id,deps,factory){
  if(Array.isArray(id)){deps(()=>{},{}).execute();return;}
  if(id!=='chunks:///_virtual/rollupPluginModLoBabelHelpers.js')return;
  factory((key,value)=>{if(typeof key==='object')Object.assign(helpers,key);else helpers[key]=value;}).execute();
 }}});
function loadModule(name,cc,globals={}){
 const starts=[...bundle.matchAll(/^System\.register\("([^\"]+)"/gm)];
 const i=starts.findIndex(m=>m[1]==='chunks:///_virtual/'+name+'.ts');assert(i>=0);
 const code=bundle.slice(starts[i].index,i+1<starts.length?starts[i+1].index:bundle.length);
 const source=fs.readFileSync('cocos-kitchen/assets/scripts/'+name+'.ts');
 assert(code.includes('source-sha256: '+crypto.createHash('sha256').update(source).digest('hex')),name+' source/build mismatch');
 let exported={};
 vm.runInNewContext(code,{...globals,console:{warn:()=>{}},URLSearchParams,
  System:{register(id,deps,factory){
   const module=factory((key,value)=>{exported[key]=value;},{id});
   deps.forEach((dep,index)=>{
    assert(['cc','./rollupPluginModLoBabelHelpers.js'].includes(dep));
    module.setters[index](dep==='cc'?{cclegacy:{_RF:{push(){},pop(){}}},...cc}:helpers);
   });module.execute();
  }}});
 return exported[name];
}
class JsonAsset{}
class Texture2D{static Filter={NEAREST:0};constructor(name){this.name=name;this.width=this.height=16;}setFilters(){}}
class SpriteFrame{}
class Rect{}
class Size{}
async function artTest(failed){
 const pending=[];
 const Art=loadModule('LevelOneArt',{JsonAsset,Texture2D,SpriteFrame,Rect,Size,
  resources:{load(path,type,callback){pending.push({path,type,callback});}}});
 const art=new Art(),loading=art.load();
 assert.equal(pending.length,26,'All atlas downloads should start before any completes.');
 for(const {path,type,callback} of [...pending].reverse()){
  if(failed&&path.startsWith(failed))callback(new Error('Fixture missing asset'));
  else callback(null,type===JsonAsset?{json:{frames:{shared:{rect:[0,0,8,8]}}}}:new Texture2D(path));
 }
 await loading;
 assert.equal(art.ready,failed!=='art/level1/');
 assert.equal(art.frames.shared.texture.name,'art/ingredient-pack-v1/atlas/texture');
 assert.equal(art.frames['modular/shared'].texture.name,'art/serving-side-v1/atlas/texture');
}
class AudioClip{constructor(name){this.name=name;}getDuration(){return 1;}}
class AudioSource{constructor(){this.playing=false;this.clip=null;this.oneShots=0;}stop(){}play(){this.playing=true;}pause(){}playOneShot(){this.oneShots++;}}
class Node{constructor(){this.isValid=true;}addChild(){}addComponent(){return new AudioSource();}}
async function audioTest(){
 const calls=[],pending=new Map(),listeners=new Map();
 const Audio=loadModule('KitchenAudio',{JsonAsset,AudioClip,AudioSource,Node,sys:{isNative:false},
  resources:{load(path,type,callback){calls.push(path);if(type===JsonAsset)callback(null,{json:{sounds:{},wash:{},chop:[]}});else pending.set(path,callback);},
   loadDir(){throw new Error('Web startup must not preload the audio directory.');}}},
  {localStorage:{getItem:()=>null},window:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:()=>{}}});
 const audio=new Audio();await audio.load(new Node());assert(audio.ready);
 audio.onState({game_id:'test',phase:'ready',kitchen:{chefs:{},stations:{}},events:[]});
 audio.update(.1);assert.deepEqual(calls,['audio/index'],'No MP3 before a gesture.');
 listeners.get('pointerdown')();audio.update(.1);audio.update(.1);
 assert.equal(calls.filter(p=>p==='audio/bgm_menu').length,1);
 assert.equal(calls.filter(p=>p==='audio/amb_kitchen').length,1);
 assert(!calls.includes('audio/bgm_rush'));
 audio.play('serve_ok');audio.play('serve_ok');assert.equal(calls.filter(p=>p==='audio/serve_ok').length,1);
 pending.get('audio/serve_ok')(null,new AudioClip('serve_ok'));await Promise.resolve();
 assert.equal(audio.sfx.oneShots,1,'A pending effect must not be replayed twice.');
 audio.play('order_new');audio.update(1);
 pending.get('audio/order_new')(null,new AudioClip('order_new'));await Promise.resolve();
 assert.equal(audio.sfx.oneShots,1,'A stale effect should not be replayed after a slow download.');
 audio.destroy();audio.play('food_ready');assert(!calls.includes('audio/food_ready'));
}
(async()=>{await artTest();await artTest('art/kitchen-modules-v2/');await artTest('art/level1/');await audioTest();
 console.log('Presentation loading: parallel atlases retain override order; web audio loads on demand without stale or duplicate effects.');
})().catch(error=>{console.error(error);process.exitCode=1;});
