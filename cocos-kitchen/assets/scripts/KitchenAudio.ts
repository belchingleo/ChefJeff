import { AudioClip, AudioSource, JsonAsset, Node, resources, sys } from 'cc';

type Entry = { loop:boolean; kind?:string; gain:number; seconds:number };
type Index = { sounds:Record<string,Entry>; chop:string[]; wash:Record<string,Entry> };
type Channel = { src:AudioSource; clip:string; level:number; target:number; fadeIn:number; fadeOut:number; randomStart:boolean };
const STORAGE='chefjeff-audio';
const LOOPS:[string,string,number,number,boolean][]=[
    // name, clip, fade in (s), fade out (s), start at a random offset
    ['ambience','amb_kitchen',1.5,.6,false],
    ['sizzle','sizzle_loop',.15,.4,true],
    ['fire','fire_loop',.2,.5,true],
    ['wash_solo','wash_solo',.08,.1,true],
    ['wash_duo','wash_duo',.2,.2,true],
];
const MUSIC=['bgm_menu','bgm_service','bgm_rush'];
const EVENT_SOUNDS:Record<string,string>={order:'order_new',ready:'food_ready',burn:'burnt_warn',fire:'fire_ignite',
    fire_spread:'fire_spread',served:'serve_ok',bad_service:'serve_bad',expired:'order_expired',thrown:'throw',
    caught:'catch',dropped:'land',plate_returned:'plate_return'};
const board=(id?:string|null)=>!!id&&id.startsWith('b')&&!id.startsWith('bin');
const cooking=(stage?:string)=>!!stage&&/^(pot_)?(cooking|chopped|ready|burnt)$/.test(stage);

/** Presentation only: reads kitchen snapshots and plays sounds; never alters observations or rules. */
export class KitchenAudio {
    private index:Index|null=null;
    private clips:Record<string,AudioClip>={};
    private sfx:AudioSource|null=null;
    private channels:Record<string,Channel>={};
    private music:Channel[]=[];
    private musicClip='';
    private last:any=null;
    private seen=new Set<string>();
    private urgent=new Set<string>();
    private recent:Record<string,number>={};
    private lastChop='';
    private endedGame='';
    private menuAfter=0;
    private clock=0;
    private warned=false;
    volume={music:.8,sfx:.8};
    ready=false;

    async load(parent:Node){
        try{
            const [index,clips]=await Promise.all([
                new Promise<JsonAsset>((ok,no)=>resources.load('audio/index',JsonAsset,(e,a)=>e?no(e):ok(a))),
                new Promise<AudioClip[]>((ok,no)=>resources.loadDir('audio',AudioClip,(e,a)=>e?no(e):ok(a))),
            ]);
            this.index=index.json as Index;
            for(const c of clips)this.clips[c.name]=c;
            const source=(name:string)=>{const n=new Node('audio-'+name);parent.addChild(n);const s=n.addComponent(AudioSource);s.playOnAwake=false;return s;};
            this.sfx=source('sfx');
            for(const [name,clip,fadeIn,fadeOut,randomStart] of LOOPS)
                this.channels[name]={src:source(name),clip,level:0,target:0,fadeIn,fadeOut,randomStart};
            // Two music players so the service/rush switch can crossfade.
            this.music=[0,1].map(i=>({src:source('music-'+i),clip:'',level:0,target:0,fadeIn:1.2,fadeOut:.8,randomStart:false}));
            if(!sys.isNative){
                try{Object.assign(this.volume,JSON.parse(localStorage.getItem(STORAGE)||'{}'));}catch(_){}
                window.addEventListener('kitchen-audio-settings',this.onSettings);
                window.addEventListener('keydown',this.unlock,true);
                window.addEventListener('pointerdown',this.unlock,true);
            }
            this.ready=true;
        }catch(error){console.warn('ChefJeff audio unavailable; the kitchen stays silent.',error);}
    }
    /** Sound must never break play: an audio error is reported once and that sound is skipped. */
    private safely(run:()=>void){
        try{run();}
        catch(error){if(!this.warned){this.warned=true;console.warn('ChefJeff audio error; the kitchen carries on without this sound.',error);}}
    }
    destroy(){
        if(sys.isNative)return;
        window.removeEventListener('kitchen-audio-settings',this.onSettings);
        window.removeEventListener('keydown',this.unlock,true);
        window.removeEventListener('pointerdown',this.unlock,true);
    }
    /** Cocos resumes its suspended Web Audio context only on a canvas click, but the kitchen is played
     *  from the keyboard. Resume the same context on any key or pointer gesture; Cocos then starts the
     *  queued sounds itself. If engine internals change, this quietly falls back to the canvas click. */
    private unlock=()=>this.safely(()=>{
        // Any source that already holds a clip has a player wired to the engine's shared context.
        for(const src of [...this.music.map(ch=>ch.src),...Object.values(this.channels).map(ch=>ch.src)]){
            const context:AudioContext|undefined=(src as any)?._player?._player?._gainNode?.context;
            if(!context)continue;
            if(context.state!=='running')context.resume().catch(()=>{});
            return;
        }
    });
    private onSettings=(e:Event)=>this.safely(()=>{Object.assign(this.volume,(e as CustomEvent).detail||{});});
    private gain(name:string){return this.index?.sounds[name]?.gain??this.index?.wash[name]?.gain??.8;}

    play(name:string,scale=1,minGap=.06){this.safely(()=>this.playNow(name,scale,minGap));}
    private playNow(name:string,scale:number,minGap:number){
        const clip=this.clips[name];if(!this.ready||!clip||!this.sfx||this.volume.sfx<=0)return;
        if(this.clock-(this.recent[name]??-1)<minGap)return;
        this.recent[name]=this.clock;
        this.sfx.playOneShot(clip,Math.min(1,this.gain(name)*this.volume.sfx*scale));
    }
    /** One knife strike, fired by the chop animation at the moment the blade meets the board. */
    chop(){this.safely(()=>this.chopNow());}
    private chopNow(){
        const pool=this.index?.chop||[];if(!pool.length)return;
        let name=pool[Math.floor(Math.random()*pool.length)];
        if(name===this.lastChop&&pool.length>1)name=pool[(pool.indexOf(name)+1)%pool.length];
        this.lastChop=name;this.playNow(name,.8+Math.random()*.2,0);
    }

    onState(s:any){this.safely(()=>this.applyState(s));}
    private applyState(s:any){
        if(!this.ready)return;
        const prev=this.last;this.last=s;
        const k=s.kitchen,fresh=!prev||prev.game_id!==s.game_id;
        if(fresh){this.seen=new Set((s.events||[]).map((e:any)=>e.t+'|'+e.message));this.urgent.clear();}
        this.phaseMusic(prev,s,fresh);
        const running=s.phase==='running';
        if(!fresh&&running){
            const events=(s.events||[]).filter((e:any)=>!this.seen.has(e.t+'|'+e.message));
            for(const e of events){
                this.seen.add(e.t+'|'+e.message);
                if(e.kind==='landed')this.play(/落到/.test(e.message)?'place_board':'land');
                else if(EVENT_SOUNDS[e.kind])this.play(EVENT_SOUNDS[e.kind]);
            }
            if(this.seen.size>80)this.seen=new Set([...this.seen].slice(-40));
            const skip=new Set(events.filter((e:any)=>['thrown','dropped','interrupted','served','bad_service'].includes(e.kind)).map((e:any)=>e.actor));
            for(const who of Object.keys(k.chefs))if(!skip.has(who))this.chefChange(prev.kitchen.chefs[who],k.chefs[who]);
            this.stationChanges(prev.kitchen,k);
            for(const o of k.orders||[])
                if(o.status==='pending'&&o.remaining<=10&&o.remaining>0&&!this.urgent.has(o.id)){this.urgent.add(o.id);this.play('order_urgent');}
        }
        const stations:any[]=Object.values(k.stations||{});
        const washers=Object.values(k.chefs).filter((c:any)=>c.action_kind==='wash'&&c.working).length;
        this.channels.ambience.target=running||s.phase==='ready'?1:0;
        this.channels.sizzle.target=running&&stations.some(st=>st.stove&&st.heating&&!st.fire&&cooking(st.food?.stage))?1:0;
        this.channels.fire.target=running&&stations.some(st=>st.fire)?1:0;
        this.channels.wash_solo.target=running&&washers===1?1:0;
        this.channels.wash_duo.target=running&&washers>=2?1:0;
    }
    private chefChange(a:any,b:any){
        const before=a.holding,after=b.holding,kind=a.action_kind||b.action_kind,target=a.target||b.target;
        const sameItem=before&&after&&before.id===after.id;
        if(sameItem&&before.stage!==after.stage){
            if(kind==='assemble')this.play('assemble');
            else if(kind==='empty_pot'||kind==='discard')this.play('discard');
            else if(/^plate|merge/.test(kind||''))this.play('plate_place');
            return;
        }
        if(after&&!sameItem){this.play(kind==='fetch'&&target==='fridge'?'fridge_grab':'pickup');return;}
        if(before&&!after){
            if(['discard','empty_pot','clear'].includes(kind))this.play('discard');
            else if(target==='serve'||this.last?.kitchen?.stations?.[target]?.stove)return; // serving/pan sounds come from events/stations
            else if(board(target))this.play('place_board');
            else this.play(/plate/.test(before.stage)?'plate_place':'place_board');
            return;
        }
        // Finished an assembly or plating job without a hand change (e.g. building on the counter).
        if(a.job_id&&a.job_id!==b.job_id&&a.working&&(a.action_kind==='assemble'||/^plate|merge/.test(a.action_kind||'')))
            this.play(a.action_kind==='assemble'?'assemble':'plate_place');
    }
    private stationChanges(a:any,b:any){
        const held=new Set(Object.values(b.chefs).map((c:any)=>c.holding?.id).filter(Boolean));
        for(const [key,n] of Object.entries<any>(b.stations||{})){
            const p=a.stations?.[key];if(!p)continue;
            if(p.fire&&!n.fire)this.play('extinguisher');
            if(n.stove&&cooking(n.food?.stage)&&/cooking|chopped/.test(n.food.stage)&&!cooking(p.food?.stage))this.play('pan_sizzle_start');
            // Burnt food cleared out of a pot without anyone carrying it away: it was dumped.
            if(p.food&&/burnt/.test(p.food.stage)&&!n.food&&!held.has(p.food.id))this.play('discard');
        }
    }
    private phaseMusic(prev:any,s:any,fresh:boolean){
        const was=prev?.phase,now=s.phase;
        if(!fresh&&was==='running'&&now==='paused')this.play('ui_pause');
        if(!fresh&&was==='paused'&&now==='running')this.play('ui_resume');
        if(now==='ended'&&!fresh&&was!=='ended'&&this.endedGame!==s.game_id){
            this.endedGame=s.game_id;this.setMusic('');
            this.play(s.won?'jingle_win':'jingle_lose',1,0);
            this.menuAfter=this.clock+(s.won?3.5:2.3);
            return;
        }
        if(now==='ended'){if(this.menuAfter&&this.clock<this.menuAfter)return;this.setMusic('bgm_menu');return;}
        if(now==='running')this.setMusic(s.kitchen.round_remaining<=30?'bgm_rush':'bgm_service');
        else if(now==='paused')this.setMusic('');
        else this.setMusic('bgm_menu');
    }
    private setMusic(name:string){
        if(name===this.musicClip)return;
        this.musicClip=name;
        for(const ch of this.music)if(ch.clip!==name)ch.target=0;
        if(!name)return;
        // Pausing keeps the position, so resuming the same piece continues where it stopped.
        const same=this.music.find(ch=>ch.clip===name);
        if(same){same.target=1;return;}
        const free=this.music[0].level<=this.music[1].level?this.music[0]:this.music[1];
        free.src.stop();free.clip=name;free.src.clip=this.clips[name]||null;free.level=0;free.target=1;
    }

    update(dt:number){this.safely(()=>this.tick(dt));}
    private tick(dt:number){
        this.clock+=dt;if(!this.ready)return;
        if(this.menuAfter&&this.clock>=this.menuAfter){this.menuAfter=0;if(this.last?.phase==='ended')this.setMusic('bgm_menu');}
        for(const ch of Object.values(this.channels))this.step(ch,dt,this.volume.sfx,true);
        for(const ch of this.music)this.step(ch,dt,this.volume.music,false);
    }
    private step(ch:Channel,dt:number,master:number,sfx:boolean){
        const rate=ch.target>ch.level?1/ch.fadeIn:1/ch.fadeOut;
        ch.level=ch.target>ch.level?Math.min(ch.target,ch.level+dt*rate):Math.max(ch.target,ch.level-dt*rate);
        const clip=this.clips[ch.clip];if(!clip)return;
        const src=ch.src;
        if(ch.level>0&&master>0){
            if(src.clip!==clip)src.clip=clip;
            src.loop=true;
            if(!src.playing){
                src.play();
                if(ch.randomStart&&sfx)src.currentTime=Math.random()*Math.max(0,clip.getDuration()-.2);
            }
            src.volume=ch.level*this.gain(ch.clip)*master;
        }else if(src.playing){
            // Loops pause at silence; texture loops restart elsewhere next time, music resumes in place.
            if(sfx&&ch.randomStart)src.stop();else src.pause();
        }
    }
}
