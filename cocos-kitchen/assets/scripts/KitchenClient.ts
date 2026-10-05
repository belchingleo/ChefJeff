import { _decorator, Component, Node, UITransform, Graphics, Color, Label, Layers,
    view, ResolutionPolicy, sys, game, Game, profiler, Mask, Vec2, Camera, director, Sprite } from 'cc';
import { LevelOneArt } from './LevelOneArt';
import { KitchenAudio } from './KitchenAudio';
import { levelButtonLayout, GRID_ART, stationView, trashView, wallNeighbours, surfaceOffset, wallOffset, depthOrder, workingChefDepth, flightDepth, predictWalk, footWalkable, plateLayers, heatCountdown, behindCounter, throwPose, throwItemPoint, panHandleSide } from './KitchenGeometry';
const { ccclass } = _decorator;
type Action = { key: string; label: string; kind: string; target: string; expected: unknown[] };
type KitchenState = { game_id: string; phase: string; speed: number; kitchen: any; actions: Action[]; levels?:any[]; limits?:any; release?:any; interaction?:Action; use_interaction?:Action; interaction_hint?:string; interaction_focus?:string; interaction_cell?:number[];
    events: {t:number; message:string; kind?:string}[]; ai: {thinking:boolean; error:string|null}; won:boolean; aborted?:boolean; round_summary?:any; rules?:Record<string,number>; connection?:any; memory?:any; communication?:any; hosted?:any };
type ChefMotion = {body:Node; leftLeg:Node; rightLeg:Node; leftArm:Node; rightArm:Node; knife:Node; facing:string; step:number};
type PotEffects = {steam:Node; smoke:Node; fire:Node; ready:Node};
// Tokens from the "ChefJeff 厨房 UI" design system: every colour is sampled from the art
// (denim overalls, copper-eared Jeff, honey floorboards, walnut walls, steel stoves).
const COLORS = { ink:'#2b1a12', muted:'#6e4e38', bg:'#f0d9b5', paper:'#fdf3e1', honeyTint:'#fbe3b8', walnut:'#6b3418', honey:'#e8983a', steel:'#3d5566',
    human:'#2a5a9e', humanHover:'#224a82', jeff:'#a8520e', herb:'#3c7a2a', hot:'#b8321e', hotHover:'#9c2a19',
    // alert: danger text on the surface ground (the hot red itself is 4.35:1 there).
    alert:'#9c2a19', frame:'#4a2616',
    // Fallback programmer art only.
    wood:'#6b3418', wall:'#ae8055', counter:'#8baab7', counterEdge:'#587582', counterLight:'#c6d9de' };
// Pixel face for titles, buttons, tags and HUD numbers (loaded by the web shell); body text stays system.
const PIXEL='ChefJeffPixel, sans-serif';
// Result events reach the player; AI decision notes have their own status line.
const RESULT_ANNOUNCE=new Set(['order','served','expired','ready','burn','fire','fire_spread','fire_loss']);
// Keyboard order; the level buttons (one per listed level, from the server) follow the language button.
const TAB_ORDER=['language','main','reset','cover-connection','help','record','resume','pause','end'];
type ButtonView = {node:Node;label:Label;callback:()=>void;enabled:boolean;width:number;height:number;tone:string;hover:boolean;selected?:boolean};
// Labels for things that are not recipe items; item and dish names come from the server's catalog.
const STAGES: Record<string,string> = {extinguisher:'灭火器',clean_plate:'干净餐盘',dirty_plate:'脏餐盘'};
// Art stem for a vessel kind that has no art of its own yet (the soup pot's frames).
const VESSEL_ART_FALLBACK='pot';
// Fallback tints by stage, for items without a colour; burnt is charred for every item.
const FOOD_COLORS: Record<string,string> = {raw:'#d68f8c',chopped:'#dcaa86',cooking:'#b58359',ready:'#846144',burnt:'#3e3733',extinguisher:'#c65138'};
const TILE=GRID_ART.tile, MAPX=GRID_ART.originX, MAPY=GRID_ART.originY;
// Knife frames per facing: front view toward the viewer, top view up-screen, side view (mirrored for left).
const KNIFE_VIEW:Record<string,[string,boolean]>={down:['knife/v1/front_',false],up:['knife/v1/top_',false],right:['knife/v1/side_',false],left:['knife/v1/side_',true]};
const color=(hex:string)=>new Color().fromHEX(hex);
const AIM_HOLD=.3;
const FACING_DIR:Record<string,[number,number]>={up:[0,-1],down:[0,1],left:[-1,0],right:[1,0]};

@ccclass('KitchenClient')
export class KitchenClient extends Component {
    private state: KitchenState|null=null;
    private art=new LevelOneArt();
    private artLoaded=false;
    private audio=new KitchenAudio();
    private knifePhase:Record<string,number>={};
    private get useArt(){return this.art.ready;}
    private get useModularArt(){return this.useArt&&this.art.modular;}
    private pending=false;
    private polling=false;
    private lastScheduledPoll=-Infinity;
    private hidden=false;
    private connected=false;
    private clock=0;
    private activeClock=0;
    private heldKeys=new Set<string>();
    private moveSeq=Date.now()*1000;
    private lastMoveAt=0;
    private manualDirection={x:0,y:0};
    private touchDirection={x:0,y:0};
    private touchMoveDirty=false;
    private touchMoveAt=-Infinity;
    private touchNeedsNeutral=false;
    private touchBlocked=false;
    private touchLayout:any=null;
    private touchNodeVisibility=new Map<Node,boolean>();
    private controls:any=null;
    private controlsSignature='';
    // Hold Space to aim a throw (Overcooked-style): after AIM_HOLD seconds the chef stops, a translucent
    // arc guides the direction and maximum range; direction keys turn it, and releasing Space throws along it.
    private spaceDownAt:number|null=null;
    private spaceItemId:string|null=null;
    private aiming:{x:number,y:number}|null=null;
    private aimArrow:Node|null=null;
    // Held-key walking is predicted locally so the chef answers on the same frame, then eased onto server state.
    private predicted:number[]|null=null;
    /** Held-key walk in whole server ticks: position at the last tick, the next one, and the progress between. */
    private walkPlan:{dx:number,dy:number,at:number[],next:number[],frac:number}|null=null;
    private releasedAt:number|null=null;
    private stateSentAt=0;
    private handsBusyUntil=-1;
    private qaNoMotion=!sys.isNative&&new URLSearchParams(location.search).get('qaMotion')==='off';
    // Isolated visual pilot; not enabled at the fixed gameplay entry.
    private prepSample=!sys.isNative&&new URLSearchParams(location.search).get('prepSample')==='1';
    private prepPoses:Record<string,Node>={};
    // Knife-only comparison: same normal scene and actor in both variants.
    private knifeSample=!sys.isNative&&new URLSearchParams(location.search).get('knifeSample')==='1';
    private knifeProbe:Node|null=null;
    private cutProbe:Node|null=null;
    private chopImpacts:Record<string,Node>={};
    // Throw poses: the human winds up while aiming; either chef shows the release briefly after a throw.
    private throwReleases:Record<string,{dx:number;dy:number;until:number}>={};
    private knives:Record<string,Node>={};
    private knifeHands:Record<string,Node>={};
    private knifeEdges:Record<string,number[]|null>={};
    private received=0;
    private labels: Record<string,Label>={};
    private buttons: Record<string,ButtonView>={};
    private controlAccess:HTMLDivElement|null=null;
    private reduceMotion=!sys.isNative&&!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    private eventsGame='';
    private seenEvents=new Set<string>();
    private lastAiError:string|null=null;
    private pops:{node:Node;label:Label;born:number;y:number;fill:Color}[]=[];
    private flashes:Record<string,{until:number;fill:string}>={};
    private tickets:Node[]=[];
    private orderArt:string[]=[];
    private focusId="";
    private meters:Record<string,Node>={};
    private overlayPhase="";
    private recordShown="";
    private devices: Record<string,{node:Node;graphics:Graphics;label:Label}>={};
    private people: Record<string,Node>={};
    private motions: Record<string,ChefMotion>={};
    private potEffects: Record<string,PotEffects>={};
    private cabinetFires:Record<string,Node>={};
    private foodStages: Record<string,string>={};
    private readyUntil: Record<string,number>={};
    private jeffThinking: Node|null=null;
    private jeffError: Node|null=null;
    private ground: Record<string,Node>={};
    private groundStages: Record<string,string>={};
    private flights: Record<string,Node>={};
    private flightOrder:Record<string,number>={};
    private menu: Node|null=null;
    private menuSignature='';
    private cover:Node=null!;
    private mounted=false;
    private world:Node|null=null;
    private depthEntries:{node:Node;getDepth:()=>number}[]=[];
    private registerDepth(node:Node,getDepth:()=>number){this.depthEntries.push({node,getDepth});}
    private sortWorld(){
        this.depthEntries=this.depthEntries.filter(e=>e.node.isValid);
        this.depthEntries.sort((a,b)=>a.getDepth()-b.getDepth());
        this.depthEntries.forEach((e,i)=>e.node.setSiblingIndex(i));
    }
    private mapNodes:Node[]=[];
    private mountedLayout="";
    // Native debug builds use USB forwarding: adb reverse tcp:8769 tcp:8769.
    // Production releases replace this with the operator's HTTPS game backend, never a Jev API key.
    private endpoint=sys.isNative?'http://127.0.0.1:8769':'';

    start(){
        if(!sys.isNative&&new URLSearchParams(location.search).has('qaPerf'))profiler.showStats();else profiler.hideStats();
        view.setDesignResolutionSize(1280,720,ResolutionPolicy.SHOW_ALL);
        // Letterbox bands match the page's wall-plank frame instead of the engine's default grey.
        for(const cam of director.getScene()?.getComponentsInChildren(Camera)||[])cam.clearColor=color(COLORS.frame);
        this.node.getComponent(UITransform)!.setContentSize(1280,720);
        this.box(this.node,'background',640,360,1280,720,COLORS.bg);
        this.box(this.node,'header',640,35,1280,70,COLORS.paper);
        this.icon(this.node,'brand-icon',45,35,'vessel',1.1);
        this.pixel(this.text('brand','ChefJeff',80,30,170,36,24),24);
        this.text('edition','和AI一起经营餐馆',81,53,290,20,11).color=color(COLORS.muted);
        for(const [i,id,title] of [[0,'served','完成订单'],[1,'money','营业收入']] as [number,string,string][]){
            const x=690+i*130;
            this.text(id+'-title',title,x,19,120,20,12).color=color(COLORS.muted);
            this.pixel(this.text(id,'—',x,46,120,32,24),24);
        }
        this.pixel(this.text('clock','准备开店',470,34,220,28,24),24).color=color(COLORS.muted);
        this.box(this.node,'order-rail',640,81,812,8,COLORS.walnut);
        for(let i=0;i<5;i++){
            const x=234+i*164,n=this.make('ticket-'+i,x+78,112,156,67);this.tickets.push(n);
            this.pixel(this.text('order-id-'+i,'',x+12,96,100,16,12),12);
            this.pixel(this.text('order-name-'+i,'',x+12,117,132,26,24),24);
            this.pixel(this.text('order-time-'+i,'',x+104,96,40,16,12),12).horizontalAlign=Label.HorizontalAlign.RIGHT;
        }
        // Map geometry has a shared projection; the exterior remains plain.
        this.text('sprint-status','',1070,63,190,16,11).horizontalAlign=Label.HorizontalAlign.RIGHT;
        this.text('fire-status','',1060,112,205,25,14).color=color(COLORS.alert);
        // End sits apart from pause/resume; both destructive actions ask first.
        this.button('pause','Ⅱ',1100,34,44,36,()=>this.post('/api/pause'));
        this.button('resume','▶',1152,34,44,36,()=>this.post('/api/resume'),this.node,'primary');
        this.button('end','■',1226,34,44,36,()=>this.confirm('end'),this.node,'danger');
        for(const id of ['pause','resume','end'])this.pixel(this.buttons[id].label,24);
        this.text('hand','',234,691,235,22,14).color=color(COLORS.ink);
        this.text('interaction','',470,691,575,22,14).color=color(COLORS.ink);
        this.text('event','',234,709,500,18,13).color=color(COLORS.ink);
        this.text('ai-status','',744,709,302,18,13).horizontalAlign=Label.HorizontalAlign.RIGHT;
        this.cover=this.make('cover',640,360,1280,720);
        this.cover.on(Node.EventType.TOUCH_END,(e:any)=>{e.propagationStopped=true;});
        const shade=this.cover.addComponent(Graphics);shade.fillColor=new Color(43,26,18,170);shade.rect(-640,-360,1280,720);shade.fill();
        // A cafe awning frames the start/pause board; the kitchen stays visible behind it.
        this.box(this.cover,'welcome-shadow',646,367,736,464,COLORS.ink);
        this.box(this.cover,'welcome-board',640,358,736,464,COLORS.paper);
        for(let i=0;i<16;i++)this.box(this.cover,'awning',295+i*46,145,46,38,i%2?COLORS.paper:COLORS.human);
        this.text('welcome-kicker','和AI一起经营餐馆',340,193,600,25,13,this.cover).horizontalAlign=Label.HorizontalAlign.CENTER;
        this.pixel(this.text('coverTitle','ChefJeff',316,244,648,56,48,this.cover),48);
        this.labels.coverTitle.horizontalAlign=Label.HorizontalAlign.CENTER;
        this.chef(this.cover,'welcome-human',550,332,'human',1.25);
        this.chef(this.cover,'welcome-jeff',730,332,'jeff',1.25);
        this.icon(this.cover,'welcome-food',640,332,'ready',1.05);
        this.text('coverText','正在连接厨房…',330,404,620,78,19,this.cover).horizontalAlign=Label.HorizontalAlign.CENTER;
        this.button('main','开始经营',379,520,158,48,()=>{
            if(!this.connected){this.poll();return;}
            const phase=this.state?.phase;
            if(phase==='ready'&&this.state?.connection&&!this.state.connection.configured){this.set('coverText','请先从下方「设置」连接自己的 API，再开始经营。');return;}
            this.post(phase==='ready'?'/api/start':phase==='paused'?'/api/resume':'/api/reset',phase==='ready'?{speed:.75}:{});
        },this.cover,'primary');
        this.button('reset','重新开局',553,520,158,48,()=>this.confirm('restart'),this.cover);
        this.buttons.reset.node.active=false;
        this.button('cover-connection','设置',727,520,158,48,()=>this.openConnection(),this.cover);
        this.button('help','操作说明',901,520,158,48,()=>this.openHelp(),this.cover);
        // Language sits on the board where people look first, not only inside Settings.
        this.pixel(this.button('language','English',944,196,88,30,()=>{const i18n=(window as any).kitchenI18n;i18n?.setLanguage(i18n.language==='en'?'zh':'en');},this.cover).getComponentInChildren(Label)!,12);
        if(sys.isNative)this.buttons.language.node.active=false;
        this.text('welcome-tip','先看操作说明，准备好了就开店。',333,577,614,19,11,this.cover).horizontalAlign=Label.HorizontalAlign.CENTER;
        // The round record shares the tip's row: the tip shows before a round, the record after it.
        this.button('record','本局记录',561,566,158,36,()=>this.openRecord(),this.cover);
        this.buttons.record.node.active=false;
        if(!sys.isNative){
            // Screen-reader proxies for every canvas button. Canvas focus moves DOM
            // focus to the matching proxy so assistive technology follows it.
            this.controlAccess=document.createElement('div');
            this.controlAccess.style.cssText='position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);';
            for(const id of TAB_ORDER)this.controlAccess.appendChild(this.proxyButton(id));
            document.body.appendChild(this.controlAccess);
            const canvas=document.getElementById('GameCanvas');
            canvas?.setAttribute('role','img');canvas?.setAttribute('aria-label','ChefJeff 厨房画面');
        }
        this.installControls();
        game.on(Game.EVENT_HIDE,this.onHide,this);game.on(Game.EVENT_SHOW,this.onShow,this);
        if(!sys.isNative){window.addEventListener('kitchen-language-changed',this.onLanguage);window.addEventListener('kitchen-confirmed',this.onConfirmed);window.addEventListener('keydown',this.onKey,true);window.addEventListener('keyup',this.onKeyUp,true);window.addEventListener('mousedown',this.onMouseDown,true);window.addEventListener('mouseup',this.onMouseUp,true);window.addEventListener('blur',this.onBlur);document.addEventListener('visibilitychange',this.onVisibility);document.addEventListener('contextmenu',this.onContextMenu);}
        // Idle screens need neither gameplay frame rate nor five snapshots a second.
        game.frameRate=15;
        this.audio.load(this.node);
        this.art.load().then(()=>{this.artLoaded=true;this.loadingStep('正在连接厨房…');if(this.isValid)this.poll();});
        if(!sys.isNative)(document as any).fonts?.load('24px ChefJeffPixel').then(()=>{
            // Labels drawn before the pixel face arrived keep the fallback until re-rendered.
            for(const l of this.node.getComponentsInChildren(Label))l.updateRenderData(true);
            this.tagText={};if(this.state&&this.mounted)this.render();
        }).catch(()=>{});this.schedule(this.scheduledPoll,.2);
    }
    // The page's loading screen stays up until the kitchen first answers (or fails), so the
    // cover never flashes placeholder art or a second "connecting" state.
    private loadingStep(text:string){const el=!sys.isNative&&document.querySelector('#kitchen-loading span');if(el)el.textContent=text;}
    private hideLoading(){if(!sys.isNative)document.getElementById('kitchen-loading')?.remove();}
    onDestroy(){this.audio.destroy();this.controlAccess?.remove();this.clearInput();game.off(Game.EVENT_HIDE,this.onHide,this);game.off(Game.EVENT_SHOW,this.onShow,this);if(!sys.isNative){window.removeEventListener('kitchen-touch-mode',this.onTouchMode);if((window as any).kitchenControls===this.controls)delete (window as any).kitchenControls;window.removeEventListener('kitchen-language-changed',this.onLanguage);window.removeEventListener('kitchen-confirmed',this.onConfirmed);window.removeEventListener('keydown',this.onKey,true);window.removeEventListener('keyup',this.onKeyUp,true);window.removeEventListener('mousedown',this.onMouseDown,true);window.removeEventListener('mouseup',this.onMouseUp,true);window.removeEventListener('blur',this.onBlur);document.removeEventListener('visibilitychange',this.onVisibility);document.removeEventListener('contextmenu',this.onContextMenu);}}
    private onHide(){this.hidden=true;this.clearInput();if(this.state?.phase==='running')this.post('/api/pause',{reason:'hidden'});}
    private onShow(){this.hidden=false;this.poll();}
    private onBlur=()=>this.clearInput();
    private onVisibility=()=>{if(document.hidden)this.clearInput();};
    private onContextMenu=(e:MouseEvent)=>{if((e.target as HTMLElement)?.closest('canvas'))e.preventDefault();};
    private onMouseDown=(e:MouseEvent)=>{
        if(!sys.isNative&&e.isTrusted)window.dispatchEvent(new CustomEvent('kitchen-manual-input',{detail:{source:'mouse'}}));
        if(e.button===2&&(e.target as HTMLElement)?.closest('canvas')){e.preventDefault();e.stopImmediatePropagation();}
    };
    private onMouseUp=(e:MouseEvent)=>{if(e.button===2&&(e.target as HTMLElement)?.closest('canvas')){e.preventDefault();e.stopImmediatePropagation();}};
    private openRecord(){if(!sys.isNative&&this.state?.round_summary)window.dispatchEvent(new CustomEvent('kitchen-open-record',{detail:this.state.round_summary}));}
    private openHelp(){this.clearInput();if(this.touchLayout?.active)this.blockTouch(true);if(!sys.isNative)window.dispatchEvent(new Event('kitchen-open-help'));}
    private openConnection(){this.clearInput();if(this.touchLayout?.active)this.blockTouch(true);if(!sys.isNative)window.dispatchEvent(new Event('kitchen-open-connection'));}
    // Keyboard and touch share gameplay actions; the web shell only owns pointer gestures and layout.
    private installControls(){
        if(sys.isNative)return;
        this.controls={
            getState:()=>this.controlsState(),move:(x:number,y:number)=>this.setTouchMove(x,y),
            press:()=>this.pressInteract(),release:()=>this.releaseInteract(),
            cancel:()=>this.clearInput(),dash:()=>this.dash(),block:(blocked:boolean)=>this.blockTouch(blocked),
            pause:()=>{this.clearInput();if(this.connected&&this.state?.phase==='running')this.post('/api/pause');},
            resume:()=>this.controlButton('resume'),main:()=>this.controlButton('main'),
            settings:()=>this.openConnection(),help:()=>this.openHelp(),end:()=>this.controlButton('end'),
            record:()=>this.openRecord(),bookmark:()=>{if(this.canInput())this.bookmark();},
            level:(id:string)=>{if(this.connected&&!this.pending&&['ready','ended'].includes(this.state?.phase||'')&&this.state?.levels?.some((l:any)=>l.id===id))this.post('/api/level',{level:id});},
            language:()=>{const i18n=(window as any).kitchenI18n;i18n?.setLanguage(i18n.language==='en'?'zh':'en');}
        };
        (window as any).kitchenControls=this.controls;
        window.addEventListener('kitchen-touch-mode',this.onTouchMode);
        window.dispatchEvent(new CustomEvent('kitchen-controls-ready'));
        this.publishControls();
    }
    private controlButton(id:string){
        if(this.pending)return;
        if(this.touchLayout?.active&&!this.touchLayout.landscape)return;
        if(!sys.isNative&&document.querySelector('dialog[open]'))return;
        if(id==='main'&&this.state?.phase==='ready'&&this.state.connection&&!this.state.connection.configured){this.openConnection();return;}
        const b=this.buttons[id];if(b?.enabled&&!this.pending)b.callback();
    }
    private canInput(){return !!this.state&&this.connected&&!this.hidden&&!this.touchBlocked&&this.state.phase==='running'&&(sys.isNative||!document.querySelector('dialog[open]'));}
    private blockTouch(blocked:boolean){
        if(this.touchBlocked===!!blocked)return;this.touchBlocked=!!blocked;
        if(blocked){this.clearInput();if(this.connected&&this.state?.phase==='running')this.post('/api/pause');}
        this.publishControls();
    }
    private onTouchMode=(e:Event)=>{
        const next=(e as CustomEvent).detail||{},old=this.touchLayout;
        this.touchLayout=next;
        if(old?.active!==next.active||old?.landscape!==next.landscape)this.clearInput();
        if(next.active&&!next.landscape)this.blockTouch(true);
        if(this.connected)game.frameRate=this.state?.phase==='running'?(next.active?30:60):15;
        this.applyTouchLayout();if(this.mounted)this.render();this.publishControls();
    };
    private controlsState(){
        const s=this.state,k=s?.kitchen,c=k?.chefs?.human;
        const text=(id:string)=>this.labels[id]?this.labelSources.get(this.labels[id])||'':'';
        return {game_id:s?.game_id,phase:s?.phase||'loading',connected:this.connected,pending:this.pending,canInput:this.canInput(),
            canInteract:!!s?.interaction,canThrow:!!c?.holding&&c.can_throw!==false,
            canDash:this.canInput()&&!this.aiming&&!!c?.sprint?.available&&(this.manualDirection.x!==0||this.manualDirection.y!==0),
            holding:c?.holding||null,interaction:s?.interaction?.label.split('（')[0]||'',interactionHint:s?.interaction_hint||'',
            aiming:this.aiming?{...this.aiming}:null,sprint:c?.sprint||{},event:text('event'),
            orders:(k?.orders||[]).filter((o:any)=>o.status==='pending').map((o:any)=>this.touchOrder(o)),
            money:k?.money||0,served:k?.served||0,timeLabel:text('clock'),handLabel:text('hand'),aiStatus:text('ai-status'),
            coverTitle:text('coverTitle'),coverText:text('coverText'),mainLabel:this.buttons.main?this.labelSources.get(this.buttons.main.label)||'':'',
            mainEnabled:!!this.buttons.main?.enabled&&!this.pending,
            communicationEnabled:!!s?.communication?.allowed,endEnabled:['running','paused'].includes(s?.phase||'')&&this.connected&&!this.pending,
            recordEnabled:!!s?.round_summary&&s?.phase==='ended',levels:(s?.levels||[]).map((l:any)=>({id:l.id,name:l.name,selected:l.id===k?.level_id})),
            levelEnabled:this.connected&&!this.pending&&['ready','ended'].includes(s?.phase||'')};
    }
    private touchOrder(order:any){
        const dish=this.dishById(order.dish),ingredients:string[]=order.ingredients||dish?.components?.map((c:any)=>c.item)||[];
        const patienceTotal=order.patience||this.state?.rules?.order_patience||90;
        const recipeKey=[`dishes/${order.dish}/ready`,`food/${order.dish}_ready`].find(key=>this.art.has(key));
        return {...order,dishName:dish?.name||order.dish,patienceTotal,
            patienceRemainingFraction:Math.max(0,Math.min(1,(order.remaining||0)/patienceTotal)),
            recipeIcon:recipeKey?this.art.spriteInfo(recipeKey):null,
            ingredientDetails:ingredients.map(id=>{
                const required=dish?.components?.find((c:any)=>c.item===id)?.state,state=required&&required!=='chopped'?required:'raw';
                const art=this.itemArt(id,state,true);
                return {id,name:this.itemLabel(id),state,icon:art?this.art.spriteInfo(art.key):null};
            })};
    }
    private publishControls(){
        if(sys.isNative||!this.controls)return;
        const detail=this.controlsState(),signature=JSON.stringify(detail);
        if(signature===this.controlsSignature)return;this.controlsSignature=signature;
        window.dispatchEvent(new CustomEvent('kitchen-controls-state',{detail}));
    }
    private setTouchMove(x:number,y:number){
        if(!Number.isFinite(x)||!Number.isFinite(y))return;
        const length=Math.hypot(x,y),d=length?{x:x/length,y:y/length}:{x:0,y:0};
        if(length&&!this.canInput())return;
        this.touchDirection=d;
        if(this.aiming){if(length){this.aiming=d;this.drawAim();this.publishControls();}return;}
        if(this.touchNeedsNeutral){if(length)return;this.touchNeedsNeutral=false;}
        this.touchMoveDirty=true;
        if(!length)this.flushTouchMove();
    }
    private flushTouchMove(){
        if(!this.touchMoveDirty)return;this.touchMoveDirty=false;this.touchMoveAt=this.clock;
        this.refreshMovement();this.publishControls();
    }
    private pressInteract(){
        if(!this.canInput()||this.pending||this.spaceDownAt!==null||this.aiming)return;
        const held=this.state!.kitchen.chefs.human.holding;
        if(held&&this.state!.kitchen.chefs.human.can_throw!==false){this.spaceDownAt=this.clock;this.spaceItemId=held.id;}
        else{this.handsBusyUntil=this.clock+.35;this.post('/api/interact',{expected_item:held?.id||null});}
    }
    private releaseInteract(){
        const held=this.state?.kitchen.chefs.human.holding;
        if(this.spaceItemId!==null&&(!this.canInput()||held?.id!==this.spaceItemId)){this.clearInput();return;}
        if(this.aiming){
            const d=this.aiming,wasTouch=this.touchDirection.x!==0||this.touchDirection.y!==0;
            this.endAim();this.touchNeedsNeutral=wasTouch;
            if(held&&this.canInput()){this.throwReleases.human={dx:d.x,dy:d.y,until:this.clock+.3};this.post('/api/throw',{expected_item:held.id,direction:[d.x,d.y]});}
            this.refreshMovement();
        }else if(this.spaceDownAt!==null){
            this.spaceDownAt=null;this.spaceItemId=null;this.handsBusyUntil=this.clock+.35;
            this.post('/api/interact',{expected_item:held?.id||null});
        }
        this.publishControls();
    }
    private dash(){
        if(!this.canInput()||this.aiming)return;
        const sprint=this.state?.kitchen.chefs.human.sprint;
        if(sprint&&(sprint.available===false||sprint.active_remaining>0||sprint.cooldown_remaining>0))return;
        this.flushTouchMove();
        if(this.manualDirection.x!==0||this.manualDirection.y!==0)this.sendMove(this.manualDirection.x,this.manualDirection.y,true);
    }
    private togglePause(e:KeyboardEvent){
        if(this.state?.phase==='running'){e.preventDefault();this.clearInput();this.post('/api/pause');}
        else if(this.state?.phase==='paused'&&this.connected){e.preventDefault();this.post('/api/resume');}
    }
    private onKey=(e:KeyboardEvent)=>{
        // Give a held controller back to the keyboard before applying this key.
        if(!sys.isNative&&e.isTrusted)window.dispatchEvent(new CustomEvent('kitchen-manual-input',{detail:{source:'keyboard'}}));
        // The communication dock keeps native Tab/Enter/Space; Esc hands the keyboard back.
        const dock=!sys.isNative?(document.activeElement as HTMLElement)?.closest('#kitchen-communication') as HTMLElement|null:null;
        if(e.key==='Escape'){
            if(dock){(document.activeElement as HTMLElement).blur();return;}
            if(e.repeat||(!sys.isNative&&document.querySelector('dialog[open]')))return;
            this.togglePause(e);
            return;
        }
        if(e.isComposing||e.keyCode===229)return;
        if(!sys.isNative&&(document.querySelector('dialog[open]')||(document.activeElement as HTMLElement)?.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]')))return;
        // P pauses and resumes like Esc, for keyboards without an Esc key (iPad Magic Keyboard).
        // Typing fields and open dialogs are excluded above.
        if(e.code==='KeyP'&&!e.ctrlKey&&!e.altKey&&!e.metaKey){
            if(!e.repeat)this.togglePause(e);else e.preventDefault();
            return;
        }
        if(dock&&(e.key==='Enter'||e.code==='Space'||e.key==='Tab'))return;
        // Enter bookmarks the moment, unless a focused on-screen control should be pressed.
        if(e.key==='Enter'&&this.state?.phase==='running'&&!(this.focusId&&this.buttons[this.focusId]?.enabled&&this.buttons[this.focusId].node.activeInHierarchy)){
            e.preventDefault();e.stopImmediatePropagation();
            if(!e.repeat&&!e.ctrlKey&&!e.altKey&&!e.metaKey)this.bookmark();
            return;
        }
        if(this.canInput()){
            // Keys that keep the WASD fingers in place: Space (thumb) = whatever the faced target needs,
            // including chop, wash and extinguish; hold Space to aim a throw; Shift (little finger) =
            // dash (Overcooked's Alt, which browsers reserve).
            if(e.key==='Shift'){
                e.preventDefault();
                if(!e.repeat)this.dash();
                return;
            }
            if(e.code==='Space'){
                e.preventDefault();
                if(!e.repeat&&!e.ctrlKey&&!e.altKey&&!e.metaKey){
                    this.pressInteract();
                }
                return;
            }
            const key=e.key.toLowerCase();if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright'].includes(key)){e.preventDefault();
                this.heldKeys.add(key);if(this.aiming)this.steerAim();else this.refreshMovement();return;}
        }
        if(e.key==='Tab'){
            e.preventDefault();const ids=this.tabOrder().filter(id=>this.buttons[id]?.enabled&&this.buttons[id].node.activeInHierarchy);
            if(!ids.length)return;const at=ids.indexOf(this.focusId);
            this.setFocus(ids[(at+(e.shiftKey?-1:1)+ids.length)%ids.length]);
        }else if(e.key==='Enter'&&this.focusId){const b=this.buttons[this.focusId];if(b?.enabled&&b.node.activeInHierarchy){e.preventDefault();this.audio.play('ui_click');b.callback();}}
    };
    private setFocus(id:string){
        const old=this.focusId;this.focusId=id;this.styleButton(old);this.styleButton(id);
        const proxy=this.controlAccess?.querySelector(`[data-control="${id}"]`) as HTMLButtonElement|null;
        if(proxy&&!proxy.hidden)proxy.focus({preventScroll:true});
        else if(this.controlAccess?.contains(document.activeElement))(document.activeElement as HTMLElement).blur();
    }
    // Ending or abandoning a live round asks first; the round is paused meanwhile.
    private async confirm(kind:'end'|'restart'){
        const phase=this.state?.phase;
        if(sys.isNative||(kind==='restart'&&phase!=='paused')){this.post(kind==='end'?'/api/end':'/api/restart');return;}
        this.clearInput();const resume=phase==='running';
        if(resume)await this.post('/api/pause');
        window.dispatchEvent(new CustomEvent('kitchen-confirm',{detail:{kind,resume}}));
    }
    private onConfirmed=(e:Event)=>{
        const d=(e as CustomEvent).detail;
        if(d.ok)this.post(d.kind==='end'?'/api/end':'/api/restart');
        else if(d.resume&&this.state?.phase==='paused')this.post('/api/resume');
    };
    private announce(message:string){if(!sys.isNative&&message)window.dispatchEvent(new CustomEvent('kitchen-announce',{detail:{message}}));}
    private onKeyUp=(e:KeyboardEvent)=>{
        if(e.code==='Space'){
            this.releaseInteract();
            return;
        }
        const key=e.key.toLowerCase();if(this.heldKeys.delete(key)){if(this.aiming)this.steerAim();else this.refreshMovement();}
    };
    private keyDirection(){
        const x=(this.heldKeys.has('d')||this.heldKeys.has('arrowright')?1:0)-(this.heldKeys.has('a')||this.heldKeys.has('arrowleft')?1:0);
        const y=(this.heldKeys.has('s')||this.heldKeys.has('arrowdown')?1:0)-(this.heldKeys.has('w')||this.heldKeys.has('arrowup')?1:0),mag=Math.hypot(x,y);
        if(mag)return {x:x/mag,y:y/mag};
        return !this.touchNeedsNeutral&&(this.touchDirection.x!==0||this.touchDirection.y!==0)?this.touchDirection:null;
    }
    /** Space held long enough: stop, and aim along the held direction (or the facing). */
    private startAim(){
        const human=this.state?.kitchen.chefs.human;
        if(!this.connected||this.state?.phase!=='running'||!human?.holding||human.holding.id!==this.spaceItemId||human.can_throw===false){this.endAim();return;}
        this.spaceDownAt=null;
        const c=this.state?.kitchen.chefs.human,f=FACING_DIR[c?.facing]||[0,1];
        this.aiming=this.keyDirection()||{x:f[0],y:f[1]};
        if(this.manualDirection.x!==0||this.manualDirection.y!==0){this.manualDirection={x:0,y:0};this.sendMove(0,0);}
        this.drawAim();this.publishControls();
    }
    private steerAim(){const d=this.keyDirection();if(d&&this.aiming){this.aiming=d;this.drawAim();}}
    private endAim(){this.aiming=null;this.spaceDownAt=null;this.spaceItemId=null;if(this.aimArrow?.isValid)this.aimArrow.active=false;}
    private drawAim(){
        const chef=this.people['human'];if(!this.aiming||!this.world||!chef)return;
        if(!this.aimArrow?.isValid){this.aimArrow=this.child(this.world,'aim-arrow',10,10);this.aimArrow.addComponent(Graphics);}
        const a=this.aimArrow,k=this.state!.kitchen,reach=(k.map.pass_range||k.map.throw_range||4)*TILE;
        a.active=true;a.setSiblingIndex(this.world.children.length-1);a.setPosition(chef.position.x,chef.position.y+18);
        const g=a.getComponent(Graphics)!;g.clear();
        // Same rule as the server's aimed throw: a teammate roughly on the aim line, within reach,
        // is the target, so the ribbon bends to them and they are ringed; otherwise full reach.
        const me=k.chefs?.human?.position,mate=k.chefs?.jeff?.position,range=k.map.pass_range||k.map.throw_range||4;
        let ex=this.aiming.x*reach,ey=-this.aiming.y*reach,toMate=false;
        if(me&&mate){
            const ox=mate[0]-me[0],oy=mate[1]-me[1],ahead=ox*this.aiming.x+oy*this.aiming.y,side=Math.abs(ox*this.aiming.y-oy*this.aiming.x);
            if(ahead>0&&ahead<=range&&side<=(k.map.catch_radius??.75)){ex=ox*TILE;ey=-oy*TILE;toMate=true;}
        }
        const left:[number,number][]=[],right:[number,number][]=[];
        // The ground path is still straight. Only the item's height bends the
        // screen projection; the hand starts 18px above the ground endpoint.
        for(let i=0;i<=32;i++){
            const t=i/32,x=ex*t,y=ey*t+35*Math.sin(Math.PI*t)-18*t;
            const tx=ex,ty=ey+35*Math.PI*Math.cos(Math.PI*t)-18,length=Math.hypot(tx,ty)||1;
            const nx=-ty/length*5,ny=tx/length*5;
            left.push([x+nx,y+ny]);right.push([x-nx,y-ny]);
        }
        g.fillColor=new Color(59,146,180,72);g.strokeColor=new Color(42,90,158,120);g.lineWidth=1;
        g.moveTo(left[0][0],left[0][1]);
        for(let i=1;i<left.length;i++)g.lineTo(left[i][0],left[i][1]);
        for(let i=right.length-1;i>=0;i--)g.lineTo(right[i][0],right[i][1]);
        g.close();g.fill();g.stroke();
        if(toMate){
            // Aimed at Jeff: ring his feet in the player's denim (the UI's navy), the throw goes to him.
            g.fillColor=new Color(42,90,158,56);g.strokeColor=color(COLORS.human);g.lineWidth=2.5;
            g.ellipse(ex,ey-18,22,11);g.fill();g.stroke();
        }else{
            // A maximum-range guide, not a prediction of collision or catching.
            g.fillColor=new Color(59,146,180,36);g.strokeColor=new Color(42,90,158,145);g.lineWidth=1.5;
            g.ellipse(ex,ey-18,13,7);g.fill();g.stroke();
        }
    }
    // Anything held can be thrown or passed; the server applies each item's range (currently 4 tiles for all).
    private async sendMove(dx:number,dy:number,sprint=false){if(!this.state||this.state.phase!=='running'||!this.connected)return;const seq=++this.moveSeq;this.lastMoveAt=this.clock;try{await this.request('/api/move',{game_id:this.state.game_id,dx,dy,seq,sprint});}catch(e){this.set('event',(e as Error).message);}}
    private refreshMovement(){
        if(this.aiming)return;
        const d=this.canInput()?this.keyDirection():null,dx=d?.x||0,dy=d?.y||0;
        if(dx===this.manualDirection.x&&dy===this.manualDirection.y)return;
        this.manualDirection={x:dx,y:dy};this.sendMove(dx,dy);
    }
    private predictHuman(k:any,c:any,dt:number,n:Node){
        const d=this.manualDirection;
        if(!c.position){this.predicted=this.releasedAt=null;return null;}
        if(this.clock<this.handsBusyUntil){this.predicted=this.releasedAt=null;return null;}
        if(d.x===0&&d.y===0){
            // Released: stay put until a state requested after the stop arrives, then ease onto it (no stale pull-back).
            if(this.predicted&&this.releasedAt===null)this.releasedAt=this.clock;
            if(this.predicted&&this.stateSentAt<=this.releasedAt!&&this.clock-this.releasedAt!<.6)return this.predicted;
            this.predicted=this.releasedAt=null;return null;
        }
        this.releasedAt=null;
        const walk=(k.map.walk_speed||4.5)*(c.sprint?.active_remaining>0?1.4:1),rate=walk*this.state!.speed,other=k.chefs.jeff?.position;
        // The server moves the chef in 50 ms game ticks (tick_game_ms); stepping the same distances from
        // the same rules keeps diagonal slides along counters on its path. Drawn between ticks.
        const tick=walk*.05,step=(p:number[])=>predictWalk(k.map,p,d.x*tick,d.y*tick,other,tick);
        let plan=this.walkPlan;
        if(!this.predicted||!plan||plan.dx!==d.x||plan.dy!==d.y){
            const from=this.predicted||[(n.position.x+640-MAPX)/TILE-.5,(360-MAPY-n.position.y)/TILE-.5];
            plan=this.walkPlan={dx:d.x,dy:d.y,at:from,next:step(from),frac:0};
        }
        plan.frac+=dt*this.state!.speed/.05;
        while(plan.frac>=1){plan.frac-=1;plan.at=plan.next;plan.next=step(plan.at);}
        let next=[plan.at[0]+(plan.next[0]-plan.at[0])*plan.frac,plan.at[1]+(plan.next[1]-plan.at[1])*plan.frac];
        // Until the server reports this same direction it has not received the key yet: trust the prediction.
        // Afterwards ease toward its position carried forward to now; snap only on a large disagreement (e.g. a push).
        const heading=c.move_direction||[0,0],synced=!!c.manual_moving&&Math.abs(heading[0]-d.x)<1e-6&&Math.abs(heading[1]-d.y)<1e-6;
        const age=synced?Math.min(.3,Math.max(0,this.clock-this.received)):0,server=predictWalk(k.map,c.position,d.x*rate*age,d.y*rate*age,other,tick);
        const ex=server[0]-next[0],ey=server[1]-next[1],pull=Math.min(1,dt*4);
        if(Math.hypot(ex,ey)>1.2){next=server;this.walkPlan={dx:d.x,dy:d.y,at:server,next:step(server),frac:0};}
        else if(synced){
            // Ease toward the server by shifting the whole tick plan, keeping its tick phase.
            const sx=ex*pull,sy=ey*pull,eased=[next[0]+sx,next[1]+sy];
            if(footWalkable(k.map,eased[0],eased[1])){next=eased;plan.at=[plan.at[0]+sx,plan.at[1]+sy];plan.next=step(plan.at);}
        }
        return this.predicted=next;
    }
    private clearInput(){this.endAim();this.heldKeys.clear();this.touchDirection={x:0,y:0};this.touchMoveDirty=false;this.touchNeedsNeutral=false;const wasMoving=this.manualDirection.x!==0||this.manualDirection.y!==0;this.manualDirection={x:0,y:0};if(wasMoving)this.sendMove(0,0);this.publishControls();}
    private applyTouchLayout(){
        if(!this.node||!this.world||!this.state)return;
        const mobile=!!this.touchLayout?.active;
        // All kitchen art shares one transform; desktop HUD and cover have a readable HTML counterpart on phones.
        if(mobile){for(const n of this.node.children)if(n!==this.world&&n.name!=='background'&&n.getComponent(UITransform)){
            if(!this.touchNodeVisibility.has(n))this.touchNodeVisibility.set(n,n.active);n.active=false;
        }}else{
            for(const [n,active] of this.touchNodeVisibility)if(n.isValid)n.active=active;
            this.touchNodeVisibility.clear();this.world.setScale(1,1,1);this.world.setPosition(0,0);return;
        }
        const r=this.touchLayout.boardRect;if(!r||!this.touchLayout.landscape)return;
        const w=this.touchLayout.width||innerWidth,h=this.touchLayout.height||innerHeight;
        const screenScale=Math.min(w/1280,h/720),gx=(w-1280*screenScale)/2,gy=(h-720*screenScale)/2;
        const map=this.state.kitchen.map,bw=map.width*TILE+24,bh=map.height*TILE+44;
        const scale=Math.min(r.width/bw,r.height/bh)/screenScale;
        const cx=MAPX+map.width*TILE/2-640,cy=360-(MAPY+map.height*TILE/2-10);
        this.world.setScale(scale,scale,1);
        this.world.setPosition((r.left+r.width/2-gx)/screenScale-640-cx*scale,360-(r.top+r.height/2-gy)/screenScale-cy*scale);
    }
    private make(name:string,x:number,y:number,w:number,h:number,parent=this.node){
        const n=new Node(name);n.layer=Layers.Enum.UI_2D;parent.addChild(n);
        n.addComponent(UITransform).setContentSize(w,h);n.setPosition(x-640,360-y);return n;
    }
    private child(parent:Node,name:string,w:number,h:number,x=0,y=0){
        const n=new Node(name);n.layer=Layers.Enum.UI_2D;parent.addChild(n);n.addComponent(UITransform).setContentSize(w,h);n.setPosition(x,y);return n;
    }
    private rect(g:Graphics,x:number,y:number,w:number,h:number,fill:string){g.fillColor=color(fill);g.rect(x,y,w,h);g.fill();}
    private pixel(l:Label,size:number){l.fontFamily=PIXEL;l.fontSize=size;l.lineHeight=size+4;l.isBold=false;return l;}
    // What Space or E would act on: a faint lift of that surface (Overcooked-style), no frame.
    private facedGlow(g:Graphics,x:number,y:number,w:number,h:number){g.fillColor=new Color(255,250,236,70);g.rect(x,y,w,h);g.fill();}
    private paintBox(n:Node,w:number,h:number,fill:string){
        const g=n.getComponent(Graphics)||n.addComponent(Graphics);g.clear();
        this.rect(g,-w/2,-h/2-3,w,h,COLORS.wood);this.rect(g,-w/2,-h/2,w,h,fill);return g;
    }
    private box(parent:Node,name:string,x:number,y:number,w:number,h:number,fill:string){const n=this.make(name,x,y,w,h,parent);this.paintBox(n,w,h,fill);return n;}
    private text(id:string,value:string,x:number,y:number,w:number,h:number,size=18,parent=this.node){
        const n=this.make(id,x+w/2,y,w,h,parent);const l=n.addComponent(Label);
        this.writeLabel(l,value);l.fontSize=size;l.lineHeight=size+6;l.color=color(COLORS.ink);l.fontFamily='sans-serif';
        l.horizontalAlign=Label.HorizontalAlign.LEFT;l.verticalAlign=Label.VerticalAlign.CENTER;
        l.overflow=Label.Overflow.SHRINK;this.labels[id]=l;return l;
    }
    private button(id:string,title:string,x:number,y:number,w:number,h:number,callback:()=>void,parent=this.node,tone='normal'){
        const n=this.make('button-'+id,x,y,w,h,parent);
        const labelNode=new Node('label');labelNode.layer=Layers.Enum.UI_2D;n.addChild(labelNode);labelNode.addComponent(UITransform).setContentSize(w-22,h-6);
        const l=labelNode.addComponent(Label);this.writeLabel(l,title);this.pixel(l,24);l.overflow=Label.Overflow.SHRINK;l.verticalAlign=Label.VerticalAlign.CENTER;
        this.buttons[id]={node:n,label:l,callback,enabled:true,width:w,height:h,tone,hover:false};this.styleButton(id);
        n.on(Node.EventType.MOUSE_ENTER,()=>{const b=this.buttons[id];if(b){b.hover=true;this.styleButton(id);}});
        n.on(Node.EventType.MOUSE_LEAVE,()=>{const b=this.buttons[id];if(b){b.hover=false;this.styleButton(id);}});
        n.on(Node.EventType.TOUCH_END,()=>{const b=this.buttons[id];if(b?.enabled){this.audio.play('ui_click');b.callback();}else if(b)this.audio.play('ui_blocked');});return n;
    }
    private styleButton(id:string){
        const b=this.buttons[id];if(!b)return;
        // Pressable: 2px ink border over a 3px ink shadow. Selected sits pressed-in on honey;
        // disabled goes flat on the surface so the two never look alike.
        const sel=!!b.selected,flat=sel||!b.enabled,dy=sel?-3:0,w=b.width,h=b.height;
        const fill=sel?COLORS.honey:!b.enabled?COLORS.bg:b.tone==='primary'?(b.hover?COLORS.humanHover:COLORS.human)
            :b.tone==='danger'?(b.hover?COLORS.hotHover:COLORS.hot):b.hover?COLORS.honeyTint:COLORS.paper;
        const g=b.node.getComponent(Graphics)||b.node.addComponent(Graphics);g.clear();
        if(!flat)this.rect(g,-w/2,-h/2-3,w,h,COLORS.ink);
        this.rect(g,-w/2,-h/2+dy,w,h,fill);
        g.strokeColor=color(flat&&!sel?COLORS.muted:COLORS.ink);g.lineWidth=2;g.rect(-w/2+1,-h/2+1+dy,w-2,h-2);g.stroke();
        // Keyboard focus: an ink ring outside the button (and its shadow) with a gap.
        if(this.focusId===id){g.strokeColor=color(COLORS.ink);g.lineWidth=3;g.rect(-w/2-5,-h/2-8,w+10,h+13);g.stroke();}
        b.label.node.setPosition(0,dy);
        b.label.color=color(sel?COLORS.ink:!b.enabled?COLORS.muted:b.tone==='primary'||b.tone==='danger'?COLORS.paper:COLORS.ink);
    }
    private proxyButton(id:string){
        const b=document.createElement('button');b.dataset.control=id;b.tabIndex=-1;
        b.onclick=()=>{if(this.buttons[id]?.enabled)this.buttons[id].callback();};
        return b;
    }
    private levelIds:string[]=[];
    private tabOrder(){return [TAB_ORDER[0],...this.levelIds.map(id=>'level:'+id),...TAB_ORDER.slice(1)];}
    /** One button per level the server lists (menu order), laid out to fit the cover; rebuilt when the list changes. */
    private syncLevelButtons(levels:any[]){
        const sorted=[...levels].sort((a,b)=>(a.menu_order??0)-(b.menu_order??0)),ids=sorted.map(l=>l.id);
        if(ids.join()===this.levelIds.join())return;
        for(const id of this.levelIds){
            this.buttons['level:'+id]?.node.destroy();delete this.buttons['level:'+id];
            this.controlAccess?.querySelector(`[data-control="level:${id}"]`)?.remove();
        }
        this.levelIds=ids;
        const slots=levelButtonLayout(ids.length),anchor=this.controlAccess?.querySelector('[data-control="main"]');
        ids.forEach((id,i)=>{
            const r=slots[i];
            this.pixel(this.button('level:'+id,'',r.x,r.y,r.w,r.h,()=>this.post('/api/level',{level:id}),this.cover).getComponentInChildren(Label)!,12);
            if(this.controlAccess)this.controlAccess.insertBefore(this.proxyButton('level:'+id),anchor||null);
        });
    }
    private enable(id:string,enabled:boolean){const b=this.buttons[id];if(!b)return;if(b.enabled!==enabled){b.enabled=enabled;this.styleButton(id);}}
    private labelSources=new WeakMap<Label,string>();
    private writeLabel(label:Label,value:string){
        this.labelSources.set(label,value);
        label.string=!sys.isNative?(window as any).kitchenI18n?.t(value)??value:value;
    }
    private onLanguage=()=>{
        this.clearInput();
        for(const label of this.node.getComponentsInChildren(Label)){
            const source=this.labelSources.get(label);if(source!==undefined)this.writeLabel(label,source);
        }
        this.render();
    };
    private set(id:string,value:string){if(this.labels[id])this.writeLabel(this.labels[id],value);}
    private icon(parent:Node,name:string,x:number,y:number,type:string,scale=1){
        const n=this.make(name,x,y,42,42,parent);n.setScale(scale,scale,1);const g=n.addComponent(Graphics);this.drawIcon(g,type);return n;
    }
    private drawIcon(g:Graphics,type:string){
        g.clear();
        if(this.useArt&&this.artIcon(g.node,type))return;
        this.art.hide(g.node);
        const r=(x:number,y:number,w:number,h:number,c:string)=>this.rect(g,x,y,w,h,c);
        if(type.startsWith('vessel:')){
            const [,,item,stage]=type.split(':');this.drawIcon(g,'vessel');if(item)r(-10,-4,20,13,this.itemColor(item,stage));
        }else if(type==='stove'){
            r(-23,-19,46,35,COLORS.wood);r(-20,-15,40,28,'#a3aaa0');r(-12,-6,24,16,COLORS.ink);r(-8,-3,16,10,'#6e746b');
        }else if(type==='continuous_counter'){
            // Continuous worktop is painted once in the map layer.
        }else if(type.startsWith('source:')){
            this.drawIcon(g,'item:'+type.slice(7)+':raw');
        }else if(type.startsWith('item:')){
            const [,item,stage]=type.split(':'),c=this.itemColor(item,stage);
            if(this.cooks(item)){
                // Items that cook: a piece on a paper card; ingredients that don't: a plain shape.
                r(-19,-13,38,26,COLORS.paper);r(-14,-10,28,20,COLORS.ink);r(-13,-6,26,15,c);r(-9,9,18,3,c);r(-6,-2,4,4,'#efd3ae');r(3,3,6,3,'#efd3ae');
            }else{
                r(-18,-12,36,24,c);r(-12,12,24,5,c);
                if(stage==='chopped'){r(-2,-12,3,27,COLORS.paper);r(-18,-1,36,3,COLORS.paper);}
            }
        }else if(type.startsWith('assembly:')){
            this.drawIcon(g,'clean_plate');
            const parts=type.slice(9).split(','),burnt=parts.includes('burnt');let y=-8;
            for(const layer of this.plateLayers(parts.filter(x=>x!=='burnt'))){r(-13,y,26,5,this.itemColor(layer.item,burnt&&this.burns(layer.item)?'burnt':'ready'));y+=5;}
        }else if(type==='counter'){
            r(-24,-19,48,36,COLORS.wood);r(-20,-14,40,26,'#b48b5e');r(-24,12,48,8,'#dfbd88');r(-2,-10,3,20,COLORS.wood);
        }else if(type.startsWith('dish:')){
            const [,dish,stage]=type.split(':'),item=this.dishById(dish)?.components?.[0]?.item;
            r(-23,-17,46,7,'#829fac');r(-21,-14,42,30,COLORS.paper);
            r(-17,-11,34,24,'#c4dce0');r(-15,-9,30,20,COLORS.paper);
            r(-12,-5,24,15,this.itemColor(item,stage));r(-7,3,4,3,'#d6af74');
        }else if(type==='clean_plate'||type==='dirty_plate'||type==='plates'||type==='returns'){
            r(-22,-15,44,28,'#8ca7ac');r(-19,-12,38,24,COLORS.paper);r(-14,-8,28,16,'#dbe7df');
            if(type==='dirty_plate'||type==='returns'){r(-11,-5,12,5,'#917451');r(5,2,6,4,'#917451');}
            if(type==='plates'){r(-22,-20,44,3,COLORS.paper);r(-22,-24,44,3,'#8ca7ac');}
        }else if(type==='sink'){
            r(-23,-18,46,36,'#718f95');r(-19,-13,38,26,'#bbd6d6');r(-15,-8,30,16,'#729ca8');
            r(8,13,5,14,COLORS.ink);r(-4,23,16,5,COLORS.ink);r(-5,14,5,10,'#b9d6dc');
        }else if(type==='vessel'){
            r(-18,-13,36,27,COLORS.ink);r(-14,-10,28,21,'#747e75');r(-21,7,42,5,COLORS.ink);r(-24,1,7,7,COLORS.ink);r(17,1,7,7,COLORS.ink);r(-9,15,18,4,'#aab7a4');r(-3,19,6,4,COLORS.ink);
        }else if(type==='board'){
            r(-21,-15,42,30,COLORS.wood);r(-18,-11,36,23,'#dcb16b');r(-13,-6,20,2,'#bd8849');r(-3,2,17,7,'#e8e7dc');r(-13,3,10,5,COLORS.ink);
        }else if(type==='serve'){
            r(-23,-19,46,39,COLORS.wood);r(-19,-13,38,29,'#4e6654');r(-15,-4,30,5,COLORS.paper);r(-10,1,20,5,COLORS.paper);r(-4,9,8,3,'#e7b94c');r(-25,-20,50,7,'#c1965c');
        }else if(type==='bin'){
            r(-14,-19,28,34,'#656b59');r(-18,14,36,5,COLORS.ink);r(-6,19,12,4,COLORS.ink);r(-8,-13,3,24,'#939c84');r(4,-13,3,24,'#939c84');
        }else if(type==='extinguisher'){
            r(-10,-21,20,34,COLORS.hot);r(-7,-18,14,29,'#d6694a');r(-10,-1,20,10,COLORS.paper);r(-4,13,8,9,COLORS.ink);r(4,16,13,4,COLORS.ink);r(14,3,4,16,COLORS.ink);
        }else if(type==='fire'){
            r(-12,-18,24,27,'#c94d30');r(-6,9,12,14,'#c94d30');r(-17,-10,8,17,'#c94d30');r(9,-10,8,14,'#c94d30');r(-8,-15,16,19,'#efae3e');r(-3,-13,6,12,'#ffe29a');
        }else{
            const c=FOOD_COLORS[type]||FOOD_COLORS.raw;
            r(-19,-13,38,26,COLORS.paper);r(-14,-10,28,20,COLORS.ink);r(-13,-6,26,15,c);r(-9,9,18,3,c);r(-6,-2,4,4,'#d6af74');r(3,3,6,3,'#d6af74');
        }
    }
    // Recipe data from the server snapshot: names, colours, cooking states and plating order.
    private itemDef(item:string|undefined):any{return item?this.state?.kitchen.items?.[item]:undefined;}
    private itemLabel(item:string){return this.itemDef(item)?.name||item;}
    private cooks(item:string|undefined){return !!this.itemDef(item)?.states?.includes('cooking');}
    private burns(item:string|undefined){return !!this.itemDef(item)?.states?.includes('burnt');}
    /** Fallback swatch (no art): burnt is charred, every other stage is the item's own colour. */
    private itemColor(item:string|undefined,stage:string){
        if(stage==='burnt')return FOOD_COLORS.burnt;
        return this.itemDef(item)?.color||FOOD_COLORS[stage]||FOOD_COLORS.ready;
    }
    private dishById(id:string|undefined):any{return id?(this.state?.kitchen.dishes||this.state?.kitchen.menu||[]).find((d:any)=>d.id===id):undefined;}
    /** The menu dish a plate is heading for: one whose components include every item on it. */
    private targetDish(components:string[]):any{
        return (this.state?.kitchen.menu||[]).find((d:any)=>components.every(x=>d.components?.some((c:any)=>c.item===x)));
    }
    private plateLayers(components:string[]){return plateLayers(this.targetDish(components)?.plating,components);}
    /** The item an ingredient source hands out (equipment data; the station id is the last resort). */
    private sourceItem(id:string){const e=this.state?.kitchen.map.equipment[id];return e?.item||e?.params?.item||id;}
    private artIcon(node:Node,type:string):boolean {
        for(const child of node.children)if(child.name==='assembly-parts'||child.name==='supply-symbol'||child.name==='vessel-contents'||child.name==='burnt-cue')child.active=false;
        if(this.useModularArt){
            if(type==='bin'){this.art.hide(node);return true;}
            const tops:Record<string,string>={board:'top_board',sink:'top_sink',stove:'top_stove',returns:'top_returns',serve:'serving_window',bin:'bin'};
            // The rack is a plain counter top; its extinguisher is drawn as the station's item while present.
            if(type==='extinguisher_rack'){this.art.hide(node);return true;}
            if(type==='serve'){
                const facing=this.state?.kitchen.map.equipment.serve?.facing;
                return this.art.tile(node,facing==='east'?'serving_east':'serving_west',TILE);
            }
            if(tops[type]&&this.art.tile(node,tops[type],TILE))return true;
            if(type.startsWith('source:')){
                this.art.hide(node);
                let symbol=node.getChildByName('supply-symbol');
                if(!symbol){symbol=this.child(node,'supply-symbol',40,32,0,22*TILE/64);symbol.addComponent(Graphics);}
                symbol.active=true;const g=symbol.getComponent(Graphics)!;g.clear();
                const sourceKey='modular/source_'+type.slice(7);
                if(!this.art.centered(symbol,sourceKey,28,28)){
                    const fallback=symbol.getChildByName('fallback')||this.child(symbol,'fallback',28,28);
                    const fg=fallback.getComponent(Graphics)||fallback.addComponent(Graphics);fallback.setScale(.6,.6,1);this.drawIcon(fg,'item:'+type.slice(7)+':raw');
                }
                return true;
            }
        }
        if(type.startsWith('item:')){
            const [,item,stage]=type.split(':'),art=this.itemArt(item,stage,true);
            return !!art&&this.art.centered(node,art.key,art.size,art.size);
        }
        if(type.startsWith('dish:')){
            const [,dish,stage]=type.split(':');
            if(!this.art.has(`dishes/${dish}/${stage}`)||!this.art.centered(node,`dishes/${dish}/${stage}`,TILE*.76,TILE*.76))return false;
            if(stage==='burnt')this.burntCue(node);
            return true;
        }
        const assembly=type.startsWith('assembly:')?type.slice(9).split(','):null;
        if(assembly&&this.plateLayers(assembly.filter(x=>x!=='burnt')).every(l=>this.art.has('feedback/'+l.layer))){
            this.art.centered(node,'objects/clean_plate',TILE*.76,TILE*.76);
            let parts=node.getChildByName('assembly-parts');
            if(!parts)parts=this.child(node,'assembly-parts',44,44);
            parts.active=true;for(const child of parts.children)child.active=false;
            const burnt=assembly.includes('burnt');
            this.plateLayers(assembly.filter(x=>x!=='burnt')).forEach((layer,i)=>{
                const item=parts!.getChildByName(layer.layer)||this.child(parts!,layer.layer,36,24);
                item.active=true;item.setPosition(0,-3+i*4);item.setSiblingIndex(parts!.children.length-1);
                this.art.centered(item,'feedback/'+layer.layer,34,22);
                // No separate charred sprite: char the layers whose item can burn; reused nodes reset to white.
                const sprite=item.getChildByName('reviewed-art')?.getComponent(Sprite);
                if(sprite)sprite.color=burnt&&this.burns(layer.item)?new Color(44,36,34,255):Color.WHITE;
            });
            if(burnt)this.burntCue(node);
            return true;
        }
        const keys:Record<string,string>={board:'workstations/board',stove:'workstations/stove',
            sink:'workstations/sink',serve:'workstations/serve',returns:'workstations/returns',
            bin:'workstations/bin',extinguisher_rack:'workstations/extinguisher_rack',extinguisher:'objects/extinguisher',
            clean_plate:'objects/clean_plate',dirty_plate:'objects/dirty_plate',
            fire:'vfx/fire_0'};
        if(type==='continuous_counter'){this.art.hide(node);return true;}
        if(type.startsWith('vessel:')){
            const [,kind,item,stage]=type.split(':'),drawn=this.drawVessel(node,kind,1,item,stage);
            if(!drawn)return false;
            let contents=node.getChildByName('vessel-contents');
            if(!contents)contents=this.child(node,'vessel-contents',22,22,0,4);
            const art=item&&drawn==='empty'?this.itemArt(item,stage,false):null;
            contents.active=!!art&&this.art.centered(contents,art.key,20,20);
            return true;
        }
        const contents=node.getChildByName('vessel-contents');if(contents)contents.active=false;
        const key=keys[type];if(!key)return false;
        const size=key.startsWith('workstations/')?49:key.startsWith('ingredients/')?29:TILE*.76;
        if(!this.art.centered(node,key,size,size))return false;
        return true;
    }
    /** Smoke over a burnt dish, wherever it is: upper layers can hide the charred layer. */
    private burntCue(node:Node){
        let cue=node.getChildByName('burnt-cue');
        if(!cue)cue=this.child(node,'burnt-cue',26,32,14,20);
        cue.active=this.art.show(cue,'vfx/smoke_3',26,32);cue.setSiblingIndex(node.children.length-1);
        const sprite=cue.getChildByName('reviewed-art')?.getComponent(Sprite);if(sprite)sprite.color=new Color(120,112,106,255);
    }
    /** Art for one item state: a chopped item that is plated chopped shows its plating layer
     * (when allowed), then food/<item>_<stage>, then ingredients/<item>/<stage> (chopped: prepared). */
    private itemArt(item:string,stage:string,layer:boolean):{key:string;size:number}|null{
        if(layer&&stage==='chopped'&&this.itemDef(item)?.platable_states?.includes('chopped')&&this.art.has('feedback/'+item))return {key:'feedback/'+item,size:30};
        if(this.art.has(`food/${item}_${stage}`))return {key:`food/${item}_${stage}`,size:30};
        for(const key of [`ingredients/${item}/${stage}`,`ingredients/${item}/${stage==='chopped'?'prepared':stage}`])
            if(this.art.has(key))return {key,size:29};
        return null;
    }
    /** A vessel of the given kind (server data), turned along its station or the holder's facing. */
    /** A vessel of the given kind (server data), turned along its station or the holder's facing.
     * A frame drawn with the contents in it (<vessel frame>/<item>/<stage>) is used when it exists:
     * returns 'filled' then, so the caller does not draw the contents again; 'empty' for the
     * vessel alone; '' when there is no art. */
    private drawVessel(node:Node,kind:string,scale=1,item?:string,stage?:string):''|'empty'|'filled'{
        const station=node.parent?.name.startsWith('station-')?node.parent.name.slice(8):'';
        const holder=node.parent?.name==='body'?node.parent.parent?.name:'';
        const facing=holder?this.state?.kitchen.chefs[holder]?.facing:'';
        const axis=station?stationView(this.state!.kitchen.map,station).device_axis:(facing==='up'||facing==='down'?'vertical':'horizontal');
        // A pan's handle points at the chef: on a station, toward its operation side; in hand, back
        // toward the holder. vertical = handle south, horizontal = east, plus pan_west / pan_north.
        const handle=station?panHandleSide(this.state!.kitchen.map.equipment[station]):holder?({down:'north',up:'south',left:'east',right:'west'} as Record<string,string>)[facing]||'east':'';
        const handleKey=handle?`modular/${kind}_${({south:'vertical',east:'horizontal',west:'west',north:'north'} as Record<string,string>)[handle]}`:'';
        const turned=!!handleKey&&this.art.has(handleKey);
        const stem=[kind,VESSEL_ART_FALLBACK].find(stem=>!!stem&&this.art.has(`modular/${stem}_${axis}`));
        const base=turned?handleKey:stem?`modular/${stem}_${axis}`:this.art.has('objects/'+kind)?'objects/'+kind:'objects/'+VESSEL_ART_FALLBACK;
        const upright=turned?handle==='north'||handle==='south':axis==='vertical';
        const filled=item?`${base}/${item}/${stage}`:'';
        const key=filled&&this.art.has(filled)?filled:base;
        if(!this.art.centered(node,key,TILE*(upright?.62:.76)*scale,TILE*.76*scale))return '';
        return key===filled?'filled':'empty';
    }
    private closingSummary(k:any,won:boolean){
        const count=(status:string)=>k.orders.filter((o:any)=>o.status===status).length,target=k.goals.target_money;
        // Each line ends in fixed text so its translation template cannot swallow the next line.
        return `净收入 ¥${k.money}（目标 ¥${target}）`+(won?'':`，还差 ¥${Math.max(0,target-k.money)} 元`)
            +`\n完成 ${k.served} 单 · 超时 ${count('expired')} 单 · 关店时未完成 ${count('unresolved_at_close')} 单`
            +'\n本局已结束，点“准备下一局”再来一局。';
    }
    private itemName(f:any){
        if(!f)return '空手';
        if(f.plate_id){
            if(f.stage==='burnt')return '糊菜';
            const dish=this.dishById(f.dish)||this.wholeDish(f);
            return dish?dish.name:'待组装 · '+this.plateItems(f).map((x:string)=>this.itemLabel(x)).join('+');
        }
        return f.meaning||STAGES[f.stage]||f.stage;
    }
    private plateItems(f:any):string[]{return f.components?.length?f.components:f.ingredient?[f.ingredient]:[];}
    /** A dish drawn as one plated sprite: exactly the plate's items and no plating layers. */
    private wholeDish(f:any):any{
        const items=Array.from(new Set(this.plateItems(f))).sort().join();
        const same=(d:any)=>Array.from(new Set((d.components||[]).map((c:any)=>c.item))).sort().join()===items;
        // The menu decides first; a servable dish that is off this level's menu still gets its plate art.
        const dish=(this.state?.kitchen.menu||[]).find(same)||(this.state?.kitchen.dishes||[]).find(same);
        return dish&&!dish.plating?dish:undefined;
    }
    private itemStage(f:any){
        // Vessels (any kind) carry their contents; the kind comes from the server.
        // Only real vessels: in-flight items always carry a contents field, null unless they are one.
        if(f&&(f.vessel||f.contents))return `vessel:${f.vessel||''}`+(f.contents?.ingredient?`:${f.contents.ingredient}:${f.contents.stage}`:'');
        if(f?.plate_id&&this.plateItems(f).length){
            const whole=this.wholeDish(f);if(whole)return `dish:${whole.id}:${f.stage}`;
            // Burnt plates keep their layers (burnt dishes can be served); items that burn are drawn charred.
            return 'assembly:'+this.plateItems(f).join(',')+(f.stage==='burnt'?',burnt':'');
        }
        if(f?.ingredient){
            const chopping=this.useArt&&f.stage==='raw'&&f.chop_remaining<(this.state?.rules?.chop_seconds||6)&&this.art.has(`ingredients/${f.ingredient}/processing`);
            return `item:${f.ingredient}:${chopping?'processing':f.stage}`;
        }
        return f?.stage;}
    private chef(parent:Node,name:string,x:number,y:number,who:string,scale=1){
        const n=this.make(name,x,y,40,64,parent);n.setScale(scale,scale,1);
        const shadow=this.child(n,'contact-shadow',40,10,0,-29),sg=shadow.addComponent(Graphics);
        if(this.useModularArt)shadow.setPosition(0,0);
        const shade=new Color(65,48,31,46);sg.fillColor=shade;sg.rect(-16,-3,32,6);sg.rect(-12,-5,24,10);sg.fill();
        const body=this.child(n,'body',40,64),g=body.addComponent(Graphics);
        const r=(x:number,y:number,w:number,h:number,c:string)=>this.rect(g,x,y,w,h,c);
        // Pixel-art body stays upright as a single directional sprite; limbs are
        // separate nodes so footsteps and chopping never move the chef's position.
        r(-17,-30,34,5,'#a99470');
        r(-16,-12,32,23,COLORS[who]);r(-9,-10,18,17,COLORS.paper);
        r(-12,8,24,21,COLORS.ink);r(-10,10,20,18,'#e4b888');
        r(-17,29,34,8,COLORS.paper);r(-12,37,24,7,COLORS.paper);r(-14,28,28,4,'#d4ccb4');
        const eyes=this.child(body,'eyes',20,8,0,19),eyeG=eyes.addComponent(Graphics);
        this.rect(eyeG,-7,-1,3,4,COLORS.ink);this.rect(eyeG,4,-1,3,4,COLORS.ink);
        const profile=this.child(body,'profile',26,24),profileG=profile.addComponent(Graphics);
        this.rect(profileG,-10,10,20,18,'#e4b888');this.rect(profileG,10,15,4,7,'#e4b888');this.rect(profileG,5,18,3,4,COLORS.ink);profile.active=false;
        const back=this.child(body,'back',32,40),backG=back.addComponent(Graphics);
        this.rect(backG,-10,10,20,18,'#78624b');this.rect(backG,-10,-10,20,18,COLORS[who]);back.active=false;
        const limb=(id:string,w:number,h:number,x:number,y:number,fill:string)=>{
            const node=this.child(body,id,w,h,x,y),lg=node.addComponent(Graphics);this.rect(lg,-w/2,-h/2,w,h,fill);return node;
        };
        const leftLeg=limb('left-leg',8,15,-7,-24,COLORS.ink),rightLeg=limb('right-leg',8,15,7,-24,COLORS.ink);
        const leftArm=limb('left-arm',6,14,-19,-4,'#dbab7c'),rightArm=limb('right-arm',6,14,19,-4,'#dbab7c');
        const knife=this.child(rightArm,'knife',14,5,9,-5),kg=knife.addComponent(Graphics);this.rect(kg,-1,-2,11,4,'#d8ded5');this.rect(kg,9,-1,4,3,COLORS.ink);
        knife.active=false;return n;
    }
    private async request(path:string,body?:object):Promise<any>{
        const hosted=typeof window!=='undefined'?(window as any).chefjeffHostedRequest:null;
        if(hosted)return hosted(path,body);
        return new Promise((resolve,reject)=>{
            const xhr=new XMLHttpRequest();xhr.open(body?'POST':'GET',this.endpoint+path,true);xhr.timeout=5000;
            xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);xhr.status===200?resolve(data):reject(new Error(data.error||'操作失败'));}catch(e){reject(new Error('厨房返回了无效数据'));}};
            xhr.onerror=()=>reject(new Error('无法连接厨房后端'));xhr.ontimeout=()=>reject(new Error('厨房连接超时'));
            if(body)xhr.setRequestHeader('Content-Type','application/json');xhr.send(body?JSON.stringify(body):null);
        });
    }
    private scheduledPoll=()=>{
        const interval=this.state?.phase==='running'?.2:1;
        if(this.clock-this.lastScheduledPoll<interval-.01)return;
        this.lastScheduledPoll=this.clock;this.poll();
    };
    private poll=async()=>{
        if(this.polling||this.hidden||!this.artLoaded)return;this.polling=true;
        try{
            const sent=this.clock,next:KitchenState=await this.request('/api/state');
            // A live old round may keep its backend until the player approves
            // restarting it. Do not pair new Space controls with old rules.
            if(!/^level-[1-9][0-9]*-[1-9][0-9]*$/.test(next.kitchen?.map?.layout_version||'')||next.release?.version!=='0.6.0-beta.1'){
                this.connected=false;this.clearInput();this.cover.active=true;
                this.set('coverTitle','等待厨房更新');
                this.set('coverText','新版页面已就绪，厨房服务仍在保留旧对局。\n服务更新后会自动连接，请先完成更新确认。');
                for(const id of ['main','reset','cover-connection'])this.enable(id,false);
                this.hideLoading();return;
            }
            this.enable('cover-connection',true);
            if(this.mounted&&this.mountedLayout!==next.kitchen.map.layout_version){
                for(const n of [...this.mapNodes,...Object.values(this.ground),...Object.values(this.flights)])n.destroy();
                this.devices={};this.people={};this.motions={};this.potEffects={};this.cabinetFires={};this.ground={};this.flights={};this.groundStages={};this.mounted=false;
            }
            if(next.game_id!==this.state?.game_id||!this.connected){this.menuSignature='';this.foodStages={};this.readyUntil={};this.activeClock=0;
                if(this.mounted)for(const who of ['human','jeff'])this.locate(this.people[who],next.kitchen.chefs[who].position);}
            if(next.phase!=='running'||next.game_id!==this.state?.game_id||(this.spaceItemId!==null&&(next.kitchen.chefs.human.holding?.id!==this.spaceItemId||next.kitchen.chefs.human.can_throw===false)))this.clearInput();
            if(next.game_id!==this.state?.game_id)this.moveSeq=Date.now()*1000;
            this.state=next;this.connected=true;this.received=this.clock;this.stateSentAt=sent;
            const frameRate=next.phase==='running'?(this.touchLayout?.active?30:60):15;
            if(game.frameRate!==frameRate)game.frameRate=frameRate;
            if(!sys.isNative)window.dispatchEvent(new CustomEvent('kitchen-state',{detail:{game_id:next.game_id,phase:next.phase,connection:next.connection,memory:next.memory,limits:next.limits,release:next.release,communication:next.communication,hosted:next.hosted}}));
            if(!this.mounted)this.mountMap();this.processEvents();this.render();this.hideLoading();
            this.audio.onState(next);
        }catch(e){this.hideLoading();game.frameRate=15;this.clearInput();this.connected=false;if(this.jeffThinking)this.jeffThinking.active=false;this.set('event',String((e as Error).message)+'，厨房会自动暂停。');this.cover.active=true;this.set('coverTitle','连接厨房');this.set('coverText','暂时连接不上厨房，请稍后重试。\n连接中断时，游戏会自动暂停。');this.writeLabel(this.buttons.main.label,'重新连接');this.buttons.reset.node.active=false;this.buttons.record.node.active=false;this.labels['welcome-tip'].node.active=true;
        }finally{this.polling=false;this.applyTouchLayout();this.publishControls();}
    };
    private async bookmark(){
        if(!this.state||this.hidden)return;
        const round=this.state.game_id;
        const notice=(message:string)=>{if(!sys.isNative&&this.state?.game_id===round)
            window.dispatchEvent(new CustomEvent('kitchen-bookmark-notice',{detail:{message}}));};
        if(!this.connected){notice('标记未保存，请重试。');return;}
        // Independent request: do not set pending, clear input, poll, or stop a job.
        try{
            const data=await this.request('/api/bookmark',{game_id:round,
                request_id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)});
            notice(data.merged?'已延长标记片段':'已标记当前片段');
        }catch(_){notice('标记未确认，请检查导出记录。');}
    }
    private async post(path:string,extra:object={}){
        if(path==='/api/action'||path==='/api/pause'||path==='/api/end'||path==='/api/reset'||path==='/api/restart')this.clearInput();
        if((this.pending&&path!=='/api/pause')||!this.state)return;
        // After closing (or while paused) gameplay input is not sent: the server would only refuse it.
        if(['/api/action','/api/interact'].includes(path)&&this.state.phase!=='running')return;
        this.pending=true;this.render();
        try{await this.request(path,{game_id:this.state.game_id,request_id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2),...extra});}
        catch(e){this.audio.play('ui_blocked');this.set('event',(e as Error).message);}
        finally{this.pending=false;this.poll();}
    }
    private act(key:string){const a=this.state?.actions.find(a=>a.key===key);if(a)this.post('/api/action',{action:key,expected:a.expected});}
    private modularWallDecor(wallNode:Node,x:number,y:number,hasSouth:boolean){
        if(y!==0||hasSouth)return;
        const faceH=GRID_ART.northFace*TILE/GRID_ART.unit;
        for(const decor of this.state!.kitchen.map.presentation?.decorations||[]){
            if(decor.cell[0]!==x)continue;
            const n=this.child(wallNode,'wall-decor-'+decor.asset,TILE,TILE,0,-TILE/2+faceH/2);
            this.art.centered(n,'modular/'+decor.asset,TILE*.65,faceH*.64);
        }
    }
    private drawWall(n:Node,x:number,y:number,map:any,walls:Set<string>){
        const neighbours=wallNeighbours(walls,x,y);
        // One logical tile is one visible boundary tile. The north-facing wall
        // uses an inset cutaway face, rather than shifting other walls/counters.
        const cap=this.child(n,'wall-top',TILE,TILE);
        this.art.centered(cap,'modular/wall_cap',TILE,TILE);
        if(y===0&&!neighbours.south){
            const h=GRID_ART.northFace*TILE/GRID_ART.unit;
            const face=this.child(n,'wall-front',TILE,h,0,-TILE/2+h/2);
            this.art.region(face,'modular/wall_face',0,0,64,GRID_ART.northFace,TILE,h);
        }
        const serve=map.equipment.serve;
        const boundary=serve&&(serve.facing==='west'?map.width-1:serve.facing==='east'?0:-1);
        if(x===boundary&&y===serve?.cell[1]){
            const slot=this.child(n,'serving-aperture',TILE*.82,TILE*.42),g=slot.addComponent(Graphics);
            this.rect(g,-TILE*.41,-TILE*.21,TILE*.82,TILE*.42,'#344756');
            this.rect(g,-TILE*.36,-TILE*.15,TILE*.72,TILE*.30,'#75543a');
            this.rect(g,-TILE*.36,-TILE*.15,TILE*.72,3,'#c99551');
        }
        this.modularWallDecor(n,x,y,neighbours.south);
    }
    private cabinetArt(n:Node,id:string){
        const map=this.state!.kitchen.map,axis=stationView(map,id).run_axis;
        const cabinet=this.child(n,'cabinet-base',TILE,TILE);
        // One body per station. Runs reuse fixed-camera modules, never rotated sprites.
        const key=axis==='horizontal'?'counter_south':'counter_east';
        this.art.tile(cabinet,key,TILE,0,this.prepSampleBoard(id)?0:-GRID_ART.cabinetSpriteLift*TILE/GRID_ART.unit);cabinet.setSiblingIndex(0);
    }
    private prepSampleBoard(id:string){return this.prepSample&&this.state!.kitchen.level===2&&id==='b1';}
    private workSurfaceY(id:string):number {return this.prepSampleBoard(id)?GRID_ART.cabinetSpriteLift*TILE/GRID_ART.unit:surfaceOffset();}
    private equipmentArt(n:Node,id:string){
        const st=this.state!.kitchen.stations[id],axis=stationView(this.state!.kitchen.map,id).device_axis;
        const g=n.getComponent(Graphics)!;g.clear();
        this.art.hide(n);
        for(const name of ['supply-symbol','assembly-parts','vessel-contents']){const child=n.getChildByName(name);if(child)child.active=false;}
        n.setPosition(0,this.workSurfaceY(id));
        if(this.prepSampleBoard(id))n.setPosition(0,this.workSurfaceY(id)+11);
        if(id.startsWith('bin')){
            const view=trashView(this.state!.kitchen.map,id);
            n.setScale(view.mirror?-1:1,1,1);
            this.art.centered(n,view.axis==='vertical'?'feedback/trash_opening_vertical':'feedback/trash_opening',TILE*.8,TILE*.8);return;
        }
        if(st.counter)return;
        if(id==='serve'){
            // Neutral double chevron points from the chef into the serving boundary.
            const east=this.state!.kitchen.map.equipment[id].facing==='west',d=east?1:-1;
            g.fillColor=color('#344756');
            for(const x of [-10,5]){g.moveTo(d*(x-5),-12);g.lineTo(d*(x+6),0);g.lineTo(d*(x-5),12);g.lineTo(d*(x-5),5);g.lineTo(d*(x-1),0);g.lineTo(d*(x-5),-5);g.close();g.fill();}
            return;
        }
        const kind=/^b[0-9]+$/.test(id)?'board':id==='returns'?'returns':id==='sink'?'sink':'';
        if(kind){this.art.centered(n,'modular/device_'+kind+'_'+axis,TILE*.84,this.prepSampleBoard(id)?28:TILE*.84);return;}
        if(st.stove){this.art.centered(n,'modular/top_stove',TILE*.82,TILE*.82);return;}
        if(this.state!.kitchen.map.equipment[id]?.type==='ingredient_source'){
            this.art.centered(n,'modular/source_'+this.sourceItem(id),TILE*.6,TILE*.6);return;
        }
    }
    private mountMap(){
        const previous=new Set(this.node.children);
        const map=this.state!.kitchen.map,walls=new Set<string>(map.walls.map((p:number[])=>p.join(','))),cells=new Set<string>(Object.values(map.equipment).reduce<string[]>((all:string[],e:any)=>all.concat((e.cells||[e.cell]).map((c:number[])=>c.join(','))),[] as string[]));
        const cabinetCells=new Set<string>(Object.values(map.equipment).reduce<string[]>((all:string[],e:any)=>all.concat((e.cells||[e.cell]).map((c:number[])=>c.join(','))),[] as string[]));
        if(this.useModularArt){
            for(let y=0;y<map.height;y++)for(let x=0;x<map.width;x++){
                if(walls.has(`${x},${y}`)&&(x===0||y===0||x===map.width-1||y===map.height-1))continue;
                const floor=this.make('floor-art',MAPX+(x+.5)*TILE,MAPY+(y+.5)*TILE,TILE,TILE);
                this.art.centered(floor,`modular/floor_${(x-1+4)%4}_${(y-1+4)%4}`,TILE,TILE);
            }
        }
        this.depthEntries=[];this.world=this.child(this.node,'kitchen-world',1280,720);
        for(let y=0;y<map.height;y++)for(let x=0;x<map.width;x++){
            const wall=walls.has(`${x},${y}`),n=this.make('tile',MAPX+(x+.5)*TILE,MAPY+(y+.5)*TILE,TILE,TILE,this.world);
            n.setScale(TILE/52,TILE/52,1);
            const g=n.addComponent(Graphics),r=(a:number,b:number,w:number,h:number,c:string)=>this.rect(g,a,b,w,h,c);
            if(wall){
                r(-26,-26,52,52,COLORS.wood);r(-26,-15,52,41,COLORS.wall);r(-24,5,48,17,'#c5a074');r(-24,-13,23,15,'#bb9062');r(2,-13,22,15,'#bb9062');r(-26,-24,52,7,'#634a37');
            }else{
                r(-26,-26,52,52,'#c7bea0');r(-25,-24,49,49,(x+y)%2?(x<7?'#e1d4ad':'#cbd3b6'):(x<7?'#eee3c1':'#dce0c7'));
                r(-23,22,45,2,'#f1e7cc');
                if(cells.has(`${x},${y}`)){r(-26,-26,52,52,COLORS.counter);if(!cells.has(`${x},${y-1}`))r(-26,22,52,4,COLORS.counterLight);if(!cells.has(`${x},${y+1}`))r(-26,-26,52,4,COLORS.counterEdge);}
            }
            if(this.useModularArt){
                n.setScale(1,1,1);
                g.clear();
                if(wall){this.drawWall(n,x,y,map,walls);this.registerDepth(n,()=>depthOrder(y,'solid'));}
            }else if(this.useArt){
                const key=wall?(y===0?'environment/wall':'environment/counter'):cells.has(`${x},${y}`)?'environment/counter':'environment/floor_cream';
                if(this.art.show(n,key,52,52)){
                    g.clear();
                    if(wall&&y!==0){const edge=this.child(n,'wall-border',52,52),eg=edge.addComponent(Graphics);eg.strokeColor=color(COLORS.wood);eg.lineWidth=3;eg.rect(-25,-25,50,50);eg.stroke();}
                }
            }
            if(!wall)this.registerDepth(n,()=>-1000);
            if(wall&&this.useModularArt)n.getComponent(UITransform)!.setAnchorPoint(.5,.5-(y===map.height-1?GRID_ART.frontWallHeight/64:GRID_ART.wallHeight/64));
        }
        // Signs sit on the wall, leaving all walkable tiles visible.

        this.text('prep-sign',this.useModularArt?'':this.state!.kitchen.level===2?'长 台 厨 房':'备 菜 区',MAPX+TILE,MAPY+25,295,24,14).horizontalAlign=Label.HorizontalAlign.CENTER;
        this.text('cook-sign',this.useModularArt?'':this.state!.kitchen.level===2?'':'烹 饪 区',MAPX+8*TILE,MAPY+25,225,24,14).horizontalAlign=Label.HorizontalAlign.CENTER;
        for(const [id,entry] of Object.entries(map.equipment)){
            const e=entry as any,n=this.make('station-'+id,MAPX+(e.cell[0]+.5)*TILE,MAPY+(e.cell[1]+.5)*TILE,TILE,TILE,this.world!);
            const overlay=this.child(n,'surface-feedback',TILE,TILE),g=overlay.addComponent(Graphics);
            if(this.useModularArt)this.cabinetArt(n,id);
            this.registerDepth(n,()=>depthOrder(e.cell[1],'solid')+.01);
            const art=new Node('equipment');art.layer=Layers.Enum.UI_2D;n.addChild(art);art.addComponent(UITransform).setContentSize(44,44);art.setPosition(0,6);
            if(this.useModularArt)art.setPosition(0,0);
            this.drawIcon(art.addComponent(Graphics),this.state!.kitchen.stations[id].counter?'continuous_counter':this.state!.kitchen.stations[id].stove?'vessel':id.startsWith('bin')?'bin':/^b[0-9]/.test(id)?'board':e.type==='ingredient_source'?'source:'+this.sourceItem(id):this.useArt&&id==='extinguisher'?'extinguisher_rack':id);
            if(this.useModularArt)this.equipmentArt(art,id);
            if(this.useModularArt){const scorch=this.child(n,'scorch',TILE,TILE);this.art.tile(scorch,'scorch',TILE);scorch.active=false;}
            const ln=new Node('label');ln.layer=Layers.Enum.UI_2D;n.addChild(ln);ln.setPosition(0,-19);ln.addComponent(UITransform).setContentSize(56,18);
            const l=ln.addComponent(Label);l.fontSize=10;l.lineHeight=13;l.isBold=true;l.color=color(COLORS.ink);l.overflow=Label.Overflow.SHRINK;
            const status=new Node('food');status.layer=Layers.Enum.UI_2D;n.addChild(status);status.addComponent(UITransform).setContentSize(30,30);status.setPosition(11,7);status.setScale(this.useModularArt?1:.6,this.useModularArt?1:.6,1);status.addComponent(Graphics);
            if(this.useModularArt){
                status.setPosition(0,this.workSurfaceY(id)+(this.prepSampleBoard(id)?18:0));
                if(this.prepSampleBoard(id))status.setScale(.5,.5,1);
                ln.active=false; // Workstations are identified by equipment, not map captions.
            }
            if(id==='sink'){
                const bubbles=new Node('washing');bubbles.layer=Layers.Enum.UI_2D;n.addChild(bubbles);
                const bg=bubbles.addComponent(Graphics);this.rect(bg,-16,0,6,6,'#eaf7f5');this.rect(bg,0,7,7,7,'#eaf7f5');this.rect(bg,12,-2,5,5,'#eaf7f5');bubbles.active=false;
            }
            if(this.useModularArt)n.getComponent(UITransform)!.setAnchorPoint(.5,.5-this.workSurfaceY(id)/TILE);
            this.devices[id]={node:n,graphics:g,label:l};
            if(!this.state!.kitchen.stations[id].stove){
                const flame=this.child(n,'cabinet-fire',58,64,0,18);flame.addComponent(Graphics);flame.active=false;this.cabinetFires[id]=flame;
                const smoke=this.child(flame,'smoke',36,44,8,36);smoke.addComponent(Graphics);
            }
            if(this.state!.kitchen.stations[id].stove){
                const steam=this.child(n,'cooking-steam',32,40,-11,38),sg=steam.addComponent(Graphics);
                this.rect(sg,-2,-17,4,8,'#f6e8ca');this.rect(sg,-9,-7,4,8,'#f6e8ca');this.rect(sg,7,2,4,8,'#f6e8ca');this.rect(sg,-2,13,4,8,'#f6e8ca');
                const smoke=this.child(n,'burnt-smoke',36,30,13,38),bg=smoke.addComponent(Graphics);
                this.rect(bg,-12,-6,9,8,'#665e57');this.rect(bg,-3,1,10,8,'#504a45');this.rect(bg,5,8,8,7,'#746b62');
                const fire=this.child(n,'fire-flame',32,34,0,39),fg=fire.addComponent(Graphics);this.drawIcon(fg,'fire');fire.setScale(.55,.55,1);
                const ready=this.child(n,'ready-pop',76,24,0,38),rg=ready.addComponent(Graphics);
                this.rect(rg,-35,-11,70,22,COLORS.honey);this.rect(rg,-32,-8,64,16,COLORS.paper);
                const cue=this.child(ready,'cue',70,22).addComponent(Label);this.writeLabel(cue,'熟了！');this.pixel(cue,12);cue.color=color(COLORS.ink);cue.horizontalAlign=Label.HorizontalAlign.CENTER;cue.verticalAlign=Label.VerticalAlign.CENTER;
                steam.active=false;smoke.active=false;fire.active=false;ready.active=false;
                this.potEffects[id]={steam,smoke,fire,ready};
            }
            overlay.setSiblingIndex(n.children.length-1);
        }
        for(const who of ['human','jeff']){
            const n=this.chef(this.world!,who,0,0,who,this.useModularArt?TILE/64:.65);  // chefs-v2 frames: 64 art px per tile, like the counters
            const dust=this.child(n,'sprint-dust',55,28,-18,-24);dust.addComponent(Graphics);dust.active=false;dust.setSiblingIndex(0);
            this.locate(n,this.state!.kitchen.chefs[who].position);
            this.registerDepth(n,()=>{const c=this.state!.kitchen.chefs[who],e=this.state!.kitchen.map.equipment[c.target];return workingChefDepth((360-MAPY-n.position.y)/TILE-.5,e?.cell[1],c.facing,!!c.working&&!!e);});
            // Name tag: a solid pixel plate in the identity colour, sized to the text in drawNameTag.
            const ln=this.child(n,'name',155,25,0,this.useModularArt?-12:-39);this.child(ln,'tag',40,18).addComponent(Graphics);
            const l=this.pixel(this.child(ln,'text',40,18).addComponent(Label),12);delete this.tagText[who]; // new nodes after a layout change need their plate drawn
            l.overflow=Label.Overflow.NONE;this.labels['person-'+who]=l;
            const body=n.getChildByName('body')!,held=this.child(body,'held',25,25,22,0);held.setScale(.9,.9,1);held.addComponent(Graphics);this.people[who]=n;
            // What the chef carries, above the head: readable from behind, where the hand is hidden.
            const bubble=this.child(n,'held-bubble',40,38,0,this.useModularArt?104:78),bg=bubble.addComponent(Graphics);
            this.rect(bg,-17,-13,34,30,COLORS.ink);this.rect(bg,-16,-10,32,26,COLORS.paper);this.rect(bg,-4,-17,8,5,COLORS.ink);this.rect(bg,-2,-15,4,4,COLORS.paper);
            const icon=this.child(bubble,'icon',42,42,0,3);icon.setScale(.62,.62,1);icon.addComponent(Graphics);bubble.active=false;
            if(this.prepSample){
                const pose=this.child(this.world!,'prep-pose-'+who,68,88);pose.active=false;this.prepPoses[who]=pose;
                this.registerDepth(pose,()=>{const c=this.state!.kitchen.chefs[who],e=this.state!.kitchen.map.equipment[c.target];return depthOrder(e?.cell[1]??c.position[1],'solid')+.02;});
            }
            this.motions[who]={body,leftLeg:body.getChildByName('left-leg')!,rightLeg:body.getChildByName('right-leg')!,
                leftArm:body.getChildByName('left-arm')!,rightArm:body.getChildByName('right-arm')!,knife:body.getChildByName('right-arm')!.getChildByName('knife')!,facing:'down',step:0};
        }
        const marker=(name:string,fill:string)=>{const n=this.child(this.people.jeff,name,30,18,0,65),g=n.addComponent(Graphics);
            g.fillColor=color(COLORS.paper);g.circle(0,0,8);g.fill();for(const x of [-5,0,5])this.rect(g,x-1,-1,2,3,fill);return n;};
        this.jeffThinking=marker('jeff-thinking',COLORS.jeff);
        const error=this.child(this.people.jeff,'jeff-api-error',24,23,0,66),eg=error.addComponent(Graphics);
        this.rect(eg,-9,-9,18,18,COLORS.hot);this.rect(eg,-2,-6,4,8,COLORS.paper);this.rect(eg,-2,4,4,3,COLORS.paper);this.jeffError=error;
        this.jeffThinking.active=false;this.jeffError.active=false;
        // Floor art and signs used to be root siblings; group them with the kitchen before fitting a phone viewport.
        for(const n of this.node.children.filter(n=>!previous.has(n)&&n!==this.world)){
            n.setParent(this.world!);this.registerDepth(n,()=>n.name==='floor-art'?-2000:1000);
        }
        this.mapNodes=[this.world!];this.mountedLayout=map.layout_version;
        this.sortWorld();this.refreshArtCharacters();
        // The cover shows a soup pot between the two chefs, like the loading card.
        const coverIcon=this.cover.getChildByName('welcome-food')!,coverG=coverIcon.getComponent(Graphics)!;
        coverG.clear();
        if(!(this.useArt&&this.art.centered(coverIcon,'objects/'+VESSEL_ART_FALLBACK,40,40)))this.drawIcon(coverG,'vessel');
        this.cover.setSiblingIndex(this.node.children.length-1);
        for(const id of ['pause','resume','end'])this.buttons[id].node.setSiblingIndex(this.node.children.length-1);this.mounted=true;this.applyTouchLayout();
    }
    private throwPoseFor(who:string):{view:string;frame:number}|null{
        const release=this.throwReleases[who];
        if(release&&this.clock<release.until)return throwPose(release.dx,release.dy,'release');
        if(who==='human'&&this.aiming)return throwPose(this.aiming.x,this.aiming.y,'windup');
        return null;
    }
    private characterArt(body:Node,who:string,facing:string,walking=false,working=false){
        const kind=who==='human'?'player':'jeff',chef=this.state?.kitchen.chefs[who];
        const station=this.state?.kitchen.map.equipment[chef?.target];
        const inWorld=!!body.parent&&['human','jeff'].includes(body.parent.name);
        const chopping=!!working&&inWorld&&chef?.action_kind==='chop'&&!!station;
        // Aiming / just thrown: turn the body to the throw and use the painted arm (any aim angle).
        const throwing=inWorld&&!chopping?this.throwPoseFor(who):null;
        const throwKey=throwing?`knifeless/characters/${kind}/${throwing.view}/chop_${throwing.frame}`:'';
        const throwMeta=throwKey&&this.art.has(throwKey)?this.art.meta(throwKey):null;
        if(throwMeta?.grip)facing=throwing!.view;
        const sampleFrame=this.prepSample?Number(new URLSearchParams(location.search).get('prepFrame')??-1):-1;
        const knifePilot=this.knifeSample&&chopping&&who==='jeff'&&facing==='down'&&this.state!.kitchen.level===2&&chef.target==='b1';
        // Raise, swing, strike, recover: the chop frames move arms and knife together.
        const beat=((this.activeClock/.4+(who==='human'?0:.27))%1+1)%1;
        const phase=knifePilot?1:Number.isInteger(sampleFrame)&&sampleFrame>=0&&sampleFrame<4?sampleFrame:beat<.3?0:beat<.45?1:beat<.75?2:3;
        const paintedKey=`characters/${kind}/${facing}/chop_${phase}`,knifeless='knifeless/'+paintedKey;
        // With the knife layer, the body comes from the knife-free poses; the painted knife is a fallback.
        const layered=chopping&&this.art.has(knifeless)&&this.art.has(KNIFE_VIEW[facing][0]+'0');
        const actionKey=layered?knifeless:paintedKey;
        const hasAction=chopping&&this.art.has(actionKey);
        const pilot=hasAction&&who==='jeff'&&facing==='down'&&this.prepSampleBoard(chef.target)&&this.art.has('prep/jeff/down/contact-body');
        const frame=walking?`walk_${Math.floor(this.activeClock*12)%8}`:'idle_0';
        // All poses share the actor's floor anchor and depth. An upper-body slice
        // is not a tool: painting it above the station puts the chef on the board.
        const key=pilot?'prep/jeff/down/contact-body':hasAction?actionKey:throwMeta?.grip?throwKey:`characters/${kind}/${facing}/${frame}`;
        const shown=this.useArt&&this.art.show(body,key,68,88,0,inWorld&&this.useModularArt?0:-29);
        if(who==='jeff'&&inWorld)this.knifeOnlySample(knifePilot,actionKey);
        const prep=this.prepPoses[who];
        if(inWorld&&prep){
            prep.active=!!pilot;
            if(pilot){
                // Only the actual hands/blade overlap the surface; never paint feet above it.
                const actor=this.people[who];prep.setPosition(actor.position);prep.setScale(actor.scale);
                this.art.show(prep,'prep/jeff/down/contact-tool',68,88);
            }
        }
        body.getComponent(Graphics)!.enabled=!shown;
        for(const child of body.children)if(!['held','held-hand','reviewed-art'].includes(child.name))child.active=!shown;
        if(inWorld&&chopping)this.knifeStrike(who,beat,.45);
        if(shown){
            // Behind a waist-high counter the body sinks so the counter hides the legs; by
            // position only (never by action), so walking up and starting work look the same.
            const sink=inWorld&&this.useModularArt?behindCounter(this.state!.kitchen.map,this.mapPoint(body.parent!)):0;
            body.setScale(1,1,1);body.angle=0;body.setPosition(0,-10*sink);
            if(inWorld&&this.useModularArt){
                body.parent!.getChildByName('contact-shadow')?.setPosition(0,0);
                body.parent!.getChildByName('name')?.setPosition(0,-12);
            }
            const held=body.getChildByName('held');
            let hand=body.getChildByName('held-hand');
            if(held&&throwMeta?.grip){
                // The item sits in the painted hand at the usual carry size: canvas px -> body coords (feet anchor at y=83).
                const [px,py]=throwItemPoint(throwMeta.grip,throwMeta.arm_deg||0),lift=inWorld&&this.useModularArt?0:-29;
                held.setPosition(px-34,83-py+lift);held.setScale(.9,.9,1);
                held.setSiblingIndex(facing==='up'?0:body.children.length-1);
                // The fist closes over the item (the pose's own hand overlay), except behind the back.
                const handKey=throwKey+'_hand';
                if(facing!=='up'&&held.active&&this.art.has(handKey)){
                    if(!hand){hand=this.child(body,'held-hand',68,88);}
                    hand.active=true;this.art.show(hand,handKey,68,88,0,lift);hand.setSiblingIndex(body.children.length-1);
                }else if(hand)hand.active=false;
            }else if(held){
                held.setScale(.9,.9,1);if(hand)hand.active=false;
                held.setPosition(facing==='left'?-24:facing==='right'?24:0,(inWorld&&this.useModularArt?29:0)+(facing==='up'?8:-5));held.setSiblingIndex(facing==='up'?0:body.children.length-1);
            }
        }else{
            this.art.hide(body);
            for(const name of ['profile','back'])body.getChildByName(name)!.active=false;
            body.getChildByName('right-arm')!.getChildByName('knife')!.active=false;
        }
        // After the sink offset, so the knife stays in the hand.
        if(inWorld)this.chopKnife(who,layered&&hasAction&&!!shown?actionKey:'',facing,phase);
        if(inWorld)this.chopImpact(who,hasAction&&phase===2&&beat<.62,(beat-.45)/.17);
        return shown;
    }
    /** The knife (art standard v1) as its own layer, pivoting on the pose's grip. It is drawn just
     * above the food on the board, so the blade lands on board and food in every facing, and stays
     * behind a chef who faces up at the board. A pose's fist overlay (<pose>_hand) goes on top of
     * the knife so the hand closes around the handle. Poses name their knife frame (older poses map
     * lift, half, strike (held), half to the view's frames 2, 1, 0, 1), and the knife is turned to
     * the pose's grip_angle, so the blade sweeps a real arc in every view. */
    private chopKnife(who:string,poseKey:string,facing:string,phase:number){
        let knife=this.knives[who],hand=this.knifeHands[who];
        const pose=poseKey?this.art.meta(poseKey):null;
        this.knifeEdges[who]=null;
        if(!pose?.grip||pose.knife_hidden){if(knife?.isValid)knife.active=false;if(hand?.isValid)hand.active=false;return;}
        const depth=(lift:number)=>()=>{const c=this.state!.kitchen.chefs[who],e=this.state!.kitchen.map.equipment[c.target];return depthOrder(e?.cell[1]??c.position[1],'item')+lift;};
        if(!knife?.isValid){knife=this.child(this.world!,'chop-knife-'+who,64,64);this.knives[who]=knife;this.registerDepth(knife,depth(.01));}
        if(!hand?.isValid){hand=this.child(this.world!,'chop-hand-'+who,68,88);this.knifeHands[who]=hand;this.registerDepth(hand,depth(.011));}
        const [view,mirror]=KNIFE_VIEW[facing],key=pose.knife||view+[2,1,0,1][phase],frame=this.art.meta(key);
        if(!frame?.pivot){knife.active=false;hand.active=false;return;}
        knife.active=true;
        // Pose canvas px (top-left origin) -> the 68x88 box the body is drawn in, above its foot anchor.
        const [cw,ch]=pose.canvasSize||[68,88],footY=(pose.anchor||[.5,.068])[1]*88,handKey=poseKey+'_hand',overlay=this.art.has(handKey);
        // With a fist overlay, grip is the fist centre. Older poses give where the painted blade
        // began, and the hand closes about 3 px behind it.
        const a=(pose.grip_angle||0)*Math.PI/180,g=overlay?pose.grip:[pose.grip[0]-3*Math.cos(a),pose.grip[1]+3*Math.sin(a)];
        const actor=this.people[who],body=actor.getChildByName('body')!,sx=actor.scale.x,sy=actor.scale.y;
        const bodyX=actor.position.x+sx*body.position.x,bodyY=actor.position.y+sy*body.position.y;
        knife.setPosition(bodyX+sx*(g[0]*68/cw-34),bodyY+sy*(88-footY-g[1]*88/ch));
        // Turn the knife about the grip so the blade points along the pose's grip_angle (degrees
        // counter-clockwise from +x). Arc frames are drawn at their screen angle (pose.screen_angle_deg)
        // and need no turn, which keeps their pixels crisp. A side knife pointing left is mirrored
        // rather than turned past 90 degrees, keeping its edge underneath.
        const built=frame.pose?.screen_angle_deg??Math.atan2(frame.pivot[1]-frame.tip[1],frame.tip[0]-frame.pivot[0])*180/Math.PI;
        const want=typeof pose.grip_angle==='number'?pose.grip_angle:null,side=key.includes('/side_');
        const flip=side&&(want===null?mirror:Math.cos(want*Math.PI/180)<0);
        const turn=want===null?0:((want-(flip?180-built:built))%360+540)%360-180;
        knife.setScale(flip?-sx:sx,sy,1);
        knife.angle=Math.abs(turn)<.5?0:turn;
        // Where the edge meets the board, in world units: the strike spark sits there.
        const edge=frame.edge||frame.tip,ex=(edge[0]-frame.pivot[0])*(flip?-sx:sx),ey=(frame.pivot[1]-edge[1])*sy,r=knife.angle*Math.PI/180;
        this.knifeEdges[who]=[knife.position.x+ex*Math.cos(r)-ey*Math.sin(r),knife.position.y+ex*Math.sin(r)+ey*Math.cos(r)];
        this.art.show(knife,key,64,64,32-frame.pivot[0],frame.pivot[1]-32);
        hand.active=overlay;
        if(overlay){hand.setPosition(bodyX,bodyY);hand.setScale(sx,sy,1);this.art.show(hand,handKey,68,88);}
    }
    /** Sound one knife strike when the swing phase passes the board-contact point. */
    private knifeStrike(who:string,t:number,contact:number){
        const before=this.knifePhase[who];this.knifePhase[who]=t;
        if(before!==undefined&&t>=contact&&(before<contact||before>t))this.audio.chop();
    }
    /** A short spark on the board while the knife lands (strike frame only). */
    private chopImpact(who:string,active:boolean,p:number){
        let impact=this.chopImpacts[who];
        if(!impact?.isValid){
            if(!active)return;
            impact=this.child(this.world!,'knife-impact-'+who,52,52);impact.addComponent(Graphics);this.chopImpacts[who]=impact;
            this.registerDepth(impact,()=>{const c=this.state!.kitchen.chefs[who];return depthOrder(this.state!.kitchen.map.equipment[c.target]?.cell[1]??c.position[1],'solid')+.04;});
        }
        impact.active=active;
        const g=impact.getComponent(Graphics)!;g.clear();if(!active)return;
        const target=this.state!.kitchen.chefs[who].target;
        const edge=this.knifeEdges[who];
        if(edge)impact.setPosition(edge[0],edge[1]);else this.locate(impact,this.state!.kitchen.map.equipment[target].cell);
        g.strokeColor=new Color(255,246,220,Math.round(255*(1-p)));g.lineWidth=2;
        g.moveTo(-9+5*p,-5);g.lineTo(7+5*p,7);g.stroke();
        g.lineWidth=1;g.moveTo(-4,8);g.lineTo(4,-7);g.stroke();
        for(const [dx,dy] of [[-1,1],[1,1],[-1,-1],[1,-1]]){
            const r=6+7*p;this.rect(g,dx*r,dy*r*.6,2,2,p<.6?'#fff1c9':'#ddb471');
        }
    }
    private knifeOnlySample(active:boolean,key:string){
        if(this.knifeProbe)this.knifeProbe.active=active;
        if(this.cutProbe)this.cutProbe.active=active;
        if(!active)return;
        const params=new URLSearchParams(location.search);
        const length=Math.max(1,Math.min(4,Number(params.get('knifeScale')||2.5)||2.5));
        const handleLength=Math.max(1,Math.min(3,Number(params.get('knifeHandle')||2)||2));
        if(!this.knifeProbe){
            const root=this.child(this.world!,'knife-only-probe',68,88);
            // Separate length axes keep both thicknesses unchanged. Existing pixels only.
            const part=(name:string,pivot:number[],points:number[][])=>{
                const stretch=this.child(root,name,68,88);stretch.angle=-40;
                const stencil=this.child(stretch,name+'-mask',68,88);stencil.angle=40;
                stencil.addComponent(Mask).type=Mask.Type.GRAPHICS_STENCIL;
                const g=stencil.getComponent(Graphics)!;g.clear();
                points.forEach(([x,y],i)=>i?g.lineTo(x-pivot[0],pivot[1]-y):g.moveTo(x-pivot[0],pivot[1]-y));g.close();g.fill();
                this.art.show(stencil,key,68,88,34-pivot[0],pivot[1]-82);
            };
            part('handle',[29,61],[[29,61],[31,61],[34,64],[31,66],[29,64]]);
            part('length',[31,63],[[31,63],[34,64],[44,72],[37,73],[31,69]]);
            this.knifeProbe=root;
            this.registerDepth(root,()=>depthOrder(this.state!.kitchen.map.equipment.b1.cell[1],'solid')+.02);
            const fx=this.child(this.world!,'cut-impact-probe',52,52);fx.addComponent(Graphics);this.cutProbe=fx;
            this.registerDepth(fx,()=>depthOrder(this.state!.kitchen.map.equipment.b1.cell[1],'solid')+.03);
        }
        const actor=this.people.jeff,root=this.knifeProbe!;
        root.active=length>1||handleLength>1;root.setScale(actor.scale);
        // Pivot remains at the original grip; neither the actor nor the board moves.
        root.setPosition(actor.position.x-5*actor.scale.x,actor.position.y+21*actor.scale.y);
        root.getChildByName('handle')!.setScale(handleLength,1,1);
        const blade=root.getChildByName('length')!;
        // Move blade base with the handle tip; never scale the grip/hand or whole actor.
        const a=-40*Math.PI/180,dx=2,dy=-2,along=dx*Math.cos(a)+dy*Math.sin(a);
        blade.setPosition(dx+(handleLength-1)*along*Math.cos(a),dy+(handleLength-1)*along*Math.sin(a));
        blade.setScale(length,1,1);
        const fx=this.cutProbe!,g=fx.getComponent(Graphics)!;g.clear();
        const impact=params.get('cutFx')==='1';
        const t=params.has('cutPhase')?Math.max(0,Math.min(.999,Number(params.get('cutPhase'))||0)):(this.activeClock*3)%1;
        fx.active=impact&&t<.28;
        if(!fx.active)return;
        const cell=this.state!.kitchen.map.equipment.b1.cell;this.locate(fx,cell);
        const p=t/.28;g.strokeColor=color('#fff3cf');g.lineWidth=2;
        g.moveTo(-9+6*p,-5);g.lineTo(5+6*p,6);g.stroke();
        g.strokeColor=color('#f4cf81');g.lineWidth=1;
        for(const [dx,dy] of [[-1,1],[1,1],[-1,-1],[1,-1]]){
            const r=5+7*p;g.moveTo(dx*r,dy*r*.65);g.lineTo(dx*(r+2),dy*(r+2)*.65);g.stroke();
        }
    }
    private refreshArtCharacters(){
        for(const who of ['human','jeff']){
            if(this.useArt)this.characterArt(this.motions[who].body,who,this.state!.kitchen.chefs[who].facing||'down');
            const welcome=this.cover.getChildByName('welcome-'+who)?.getChildByName('body');
            if(welcome)this.characterArt(welcome,who,'down');
        }
    }
    private foodNode(id:string,stage:string,airborne=false){
        const n=this.make('food-'+id,0,0,44,40,this.world||this.node);n.setScale(.9,.9,1);
        this.registerDepth(n,()=>airborne?(this.flightOrder[id]??0):depthOrder((360-MAPY-n.position.y)/TILE-.5,'item')); this.drawIcon(n.addComponent(Graphics),stage);
        const child=new Node('id');child.layer=Layers.Enum.UI_2D;n.addChild(child);child.addComponent(UITransform).setContentSize(64,19);child.setPosition(0,-23);
        const l=child.addComponent(Label);this.writeLabel(l,id);l.fontSize=13;l.lineHeight=16;l.color=color(COLORS.ink);
        child.active=!this.useModularArt;
        return n;
    }
    private statColor(id:string){
        const f=this.flashes[id];if(f&&f.until>this.clock)return f.fill;
        return COLORS.ink;
    }
    // New result events: a short pop where it happened, a header pulse, and a
    // screen-reader announcement. Events already present when a round loads stay quiet.
    private processEvents(){
        const s=this.state!,fresh=s.game_id!==this.eventsGame;
        if(fresh){this.eventsGame=s.game_id;this.seenEvents.clear();}
        for(const e of s.events){
            const key=e.t+'|'+e.message;if(this.seenEvents.has(key))continue;
            this.seenEvents.add(key);if(!fresh)this.feedback(e);
        }
        if(this.seenEvents.size>300)this.seenEvents=new Set(s.events.map(e=>e.t+'|'+e.message));
    }
    private feedback(e:{message:string;kind?:string}){
        const k=this.state!.kitchen,amount=/(\d+) 元/.exec(e.message)?.[1]||'',serve=k.map.equipment.serve?.cell;
        const at=(cell:number[]|undefined)=>cell?[MAPX+(cell[0]+.5)*TILE,MAPY+(cell[1]-.1)*TILE]:[640,150];
        if(e.kind==='served'){this.pop(at(serve),'+¥'+amount,COLORS.herb);this.flash(['served','money'],COLORS.herb);}
        else if(e.kind==='expired'){this.pop([312,180],`${/^(\S+?)超时/.exec(e.message)?.[1]||''} 超时 -¥${amount}`,COLORS.alert);this.flash(['money'],COLORS.alert);}
        else if(e.kind==='fire'||e.kind==='fire_spread')this.flash(['money'],COLORS.alert);
        if(e.kind&&RESULT_ANNOUNCE.has(e.kind))this.announce(e.message);
    }
    private flash(ids:string[],fill:string){for(const id of ids){this.flashes[id]={until:this.clock+1.2,fill};this.labels[id].color=color(fill);}}
    private pop(p:number[],text:string,fill:string){
        const n=this.make('result-pop',p[0],p[1],220,28,this.world||this.node),l=n.addComponent(Label);
        this.writeLabel(l,text);this.pixel(l,24);l.horizontalAlign=Label.HorizontalAlign.CENTER;
        l.enableShadow=true;l.shadowColor=color(COLORS.ink);l.shadowOffset=new Vec2(2,-2);l.shadowBlur=0;l.color=color(fill); // hard pixel shadow
        this.pops.push({node:n,label:l,born:this.clock,y:n.position.y,fill:color(fill)});
    }
    private drawOrders(){
        const s=this.state!,k=s.kitchen,orders=k.orders.filter((o:any)=>o.status==='pending');
        // The goal is net revenue at closing.
        this.set('served',`${k.served}`);this.set('money',`¥ ${k.money} / ${k.goals.target_money}`);
        for(const id of ['served','money'])this.labels[id].color=color(this.statColor(id));
        for(let i=0;i<5;i++){
            const o=orders[i],n=this.tickets[i],g=n.getComponent(Graphics)||n.addComponent(Graphics),urgent=o&&o.remaining<=15;g.clear();
            // Paper slip clipped to the walnut rail; empty clips stay bare instead of drawing blank slips.
            this.rect(g,-10,26,20,6,COLORS.walnut);
            if(o||i===0){
                this.rect(g,-78,-36,156,62,COLORS.walnut);this.rect(g,-77,-34,154,59,COLORS.paper);
                if(o){
                    // Patience: herb while comfortable, honey past half, hot red when urgent (the label also says so).
                    const left=Math.max(0,Math.min(1,o.remaining/(o.patience||s.rules?.order_patience||90)));
                    this.rect(g,-67,-30,134,7,COLORS.ink);this.rect(g,-66,-29,132,5,COLORS.bg);
                    this.rect(g,-66,-29,132*left,5,urgent?COLORS.hot:left>.5?COLORS.herb:COLORS.honey);
                }
            }
            const signature=o?JSON.stringify(o.ingredients||[]):'';
            if(this.orderArt[i]!==signature){this.orderArt[i]=signature;
            const prev=n.getChildByName('ingredients');if(prev)prev.destroy();
            if(o){const row=this.child(n,'ingredients',150,16,0,-5);const ingredients:string[]=o.ingredients||[];
                // Each item as the dish needs it, but whole: a chopped item reads better uncut at this size.
                const need=(name:string)=>{const st=this.dishById(o.dish)?.components?.find((c:any)=>c.item===name)?.state;return st&&st!=='chopped'?st:'raw';};
                ingredients.forEach((name:string,j:number)=>{const item=this.child(row,'ingredient-'+j,30,14,66-(ingredients.length-1-j)*15,0);item.setScale(this.useArt?.5:.32,this.useArt?.5:.32,1);this.drawIcon(item.addComponent(Graphics),`item:${name}:${need(name)}`);});}}
            this.set('order-id-'+i,o?`${o.id} · ${urgent?'快超时了':'待出餐'}`:i===0?'订单夹':'');this.labels['order-id-'+i].color=color(urgent?COLORS.hot:COLORS.muted);
            this.set('order-name-'+i,o?(this.dishById(o.dish)?.name||o.dish):i===0?(k.future_orders?'等待新订单':'订单已结清'):'');
            this.set('order-time-'+i,o?`${Math.max(0,Math.ceil(o.remaining))}s`:'');this.labels['order-time-'+i].color=color(urgent?COLORS.hot:COLORS.muted);
        }
    }
    private tagText:Record<string,string>={};
    private drawNameTag(who:string){
        const l=this.labels['person-'+who];if(this.tagText[who]===l.string)return;this.tagText[who]=l.string;
        l.updateRenderData(true);const w=Math.ceil(l.node.getComponent(UITransform)!.width)+10,h=18;
        const g=l.node.parent!.getChildByName('tag')!.getComponent(Graphics)!;g.clear();
        // 1px ink border with a 2px hard ink shadow below, like the game's buttons.
        // You: denim plate, paper text. Jeff: paper plate (his white body), copper text.
        this.rect(g,-w/2-1,-h/2-3,w+2,h+4,COLORS.ink);this.rect(g,-w/2,-h/2,w,h,who==='human'?COLORS.human:COLORS.paper);
        l.color=color(who==='human'?COLORS.paper:COLORS.jeff);
    }
    /** Map cell coordinates of a world node (inverse of locate). */
    private mapPoint(n:Node){return [(n.position.x+640-MAPX)/TILE-.5,(360-MAPY-n.position.y)/TILE-.5];}
    private locate(n:Node,p:number[],height=0){n.setPosition(MAPX+(p[0]+.5)*TILE-640,360-MAPY-(p[1]+.5)*TILE+height);}
    private render(){
        if(!this.state||!this.mounted)return;const s=this.state,k=s.kitchen,active=s.phase==='running'&&!this.pending&&this.connected;
        const remaining=Math.max(0,Math.ceil(k.round_remaining));
        this.set('clock',`${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}  ${s.phase==='running'?'营业中':s.phase==='ended'?'已结算':'休息中'}`);
        const sprint=k.chefs.human.sprint;this.set('sprint-status',!sprint?'':sprint.active_remaining>0?'冲刺中':sprint.cooldown_remaining>0?'冲刺冷却 '+Math.ceil(sprint.cooldown_remaining)+'s':'冲刺 · Shift');
        this.set('fire-status',k.fire_safety?.burning_count?`着火工位 ${k.fire_safety.burning_count}/${k.fire_safety.loss_threshold}`:'');
        this.labels.clock.color=color(remaining<=30?COLORS.hot:COLORS.muted);this.drawOrders();
        for(const [id,dev] of Object.entries(this.devices)){
            const st=k.stations[id],g=dev.graphics;g.clear();
            const scorch=dev.node.getChildByName('scorch');if(scorch)scorch.active=!!st.scorched;
            const prior=this.foodStages[id];
            const foodKey=st.food?`${st.food.id}:${st.food.stage}`:'';
            if(st.food?.stage==='ready'&&prior===`${st.food.id}:cooking`)this.readyUntil[id]=this.activeClock+1.1;
            this.foodStages[id]=foodKey;
            if(st.fire&&!this.useArt){this.rect(g,-26,-26,52,52,'#f1b589');}
            if(s.interaction?.target===id||s.use_interaction?.target===id){
                if(this.useModularArt)this.facedGlow(g,-TILE/2,this.workSurfaceY(id)-TILE/2,TILE,TILE);
                else this.facedGlow(g,-27,-27,54,54);
            }
            this.writeLabel(dev.label,st.fire?'着火了！':st.food?(this.itemName(st.food)+(st.food.stage==='cooking'?` ${Math.ceil(st.ready_in)}s`:st.food.stage==='ready'&&st.heating&&st.burn_in!==undefined?` ${Math.ceil(st.burn_in)}s 后糊`:'')):this.state!.kitchen.map.equipment[id]?.type==='ingredient_source'&&this.useModularArt?this.itemLabel(this.sourceItem(id)):st.name);
            const countdown=heatCountdown(st);
            let timer=dev.node.getChildByName('heat-countdown');
            if(countdown&&!timer){
                timer=this.child(dev.node,'heat-countdown',48,15,0,this.workSurfaceY(id)+TILE/2-5);
                timer.addComponent(Graphics);
                const text=this.child(timer,'time',48,15).addComponent(Label);
                this.pixel(text,12);text.overflow=Label.Overflow.SHRINK;
            }
            if(timer){
                timer.active=!!countdown;
                if(countdown){
                    timer.setSiblingIndex(dev.node.children.length-1);
                    const tg=timer.getComponent(Graphics)!;tg.clear();
                    this.rect(tg,-24,-7.5,48,15,countdown.paused?COLORS.steel:countdown.ready?COLORS.hot:COLORS.walnut);
                    const label=timer.getChildByName('time')!.getComponent(Label)!;label.color=color(COLORS.paper);
                    this.writeLabel(label,`${countdown.paused?'Ⅱ ':''}${countdown.seconds}s ${countdown.ready?'糊':'熟'}`);
                }
            }
            dev.label.color=color(st.fire||st.food?.stage==='ready'||st.food?.stage==='burnt'?COLORS.hot:COLORS.ink);
            const food=dev.node.getChildByName('food')!;food.active=!!st.food||st.fire;if(food.active)this.drawIcon(food.getComponent(Graphics)!,st.fire?'fire':this.itemStage(st.food));
            if(this.cabinetFires[id]){this.cabinetFires[id].active=!!st.fire;if(st.fire)food.active=false;}
            if(st.counter&&!st.fire)this.writeLabel(dev.label,st.food?this.itemName(st.food):(s.interaction_focus!==id?'':'空柜台'));
            if(st.stove){
                if(this.useModularArt)this.equipmentArt(dev.node.getChildByName('equipment')!,id);
                else this.drawIcon(dev.node.getChildByName('equipment')!.getComponent(Graphics)!,this.useArt?'stove':st.vessel?'vessel:'+st.vessel:'stove');
                if(this.useArt){
                    let vessel=dev.node.getChildByName('stove-vessel');
                    if(!vessel){vessel=this.child(dev.node,'stove-vessel',34,34,0,this.useModularArt?this.workSurfaceY(id):10);vessel.setSiblingIndex(dev.node.getChildByName('equipment')!.getSiblingIndex()+1);}
                    vessel.active=!!(st.vessel||st.pot_id);
                    // A filled vessel frame already shows what is cooking: the separate food icon stays hidden.
                    if(vessel.active&&this.drawVessel(vessel,st.vessel||'',.96,st.food?.ingredient,st.food?.stage)==='filled'&&!st.fire)food.active=false;
                    food.setPosition(0,this.useModularArt?this.workSurfaceY(id)+3:13);food.setScale(.58,.58,1);
                }
            }
            if(id==='returns')this.writeLabel(dev.label,st.food?'脏盘待洗':'脏盘回收');
            if(id==='sink'&&st.food)this.writeLabel(dev.label,st.food.stage==='dirty_plate'?`待洗 ${Math.ceil(st.food.wash_remaining)}s`:'洗好了');
            let progress=-1;
            if(id==='sink'&&st.food)progress=1-st.food.wash_remaining/k.tableware.wash_seconds;
            if(st.food&&id.startsWith('b')&&!id.startsWith('bin'))progress=1-st.food.chop_remaining/(s.rules?.chop_seconds||6);
            if(st.food&&st.stove)progress=Math.min(1,st.food.heat_elapsed/(s.rules?.cook_seconds||12));
            if(progress>=0){
                const py=this.useModularArt?this.workSurfaceY(id)-TILE/2+3:-18;
                this.rect(g,-23,py-1,46,6,COLORS.ink);this.rect(g,-22,py,44*progress,4,st.fire?COLORS.hot:COLORS.paper);
            }
            const effects=this.potEffects[id];if(effects){
                effects.steam.active=!!st.food&&st.food.stage==='cooking'&&!!st.heating&&!st.fire;
                effects.smoke.active=!!st.food&&st.food.stage==='burnt'&&!!st.heating&&!st.fire;
                effects.fire.active=!!st.fire;
                effects.ready.active=(this.readyUntil[id]||0)>this.activeClock&&!!st.food&&st.food.stage==='ready';
            }
        }
        const ids=new Set(k.ground.map((g:any)=>g.food.id));
        for(const [id,n] of Object.entries(this.ground))if(!ids.has(id)){n.destroy();delete this.ground[id];delete this.groundStages[id];}
        for(const item of k.ground){
            const id=item.food.id,stage=this.itemStage(item.food);
            if(!this.ground[id]){this.ground[id]=this.foodNode(id,stage);this.groundStages[id]=stage;}
            if(this.groundStages[id]!==stage){this.drawIcon(this.ground[id].getComponent(Graphics)!,stage);this.groundStages[id]=stage;}
            this.writeLabel(this.ground[id].getChildByName('id')!.getComponent(Label)!,this.itemName(item.food));
            this.locate(this.ground[id],item.position);
        }
        for(const who of ['human','jeff']){
            const c=k.chefs[who];
            this.set('person-'+who,(who==='human'?'你':'Jeff')+(c.sprint?.active_remaining>0?' »':''));this.drawNameTag(who);
            const held=this.motions[who].body.getChildByName('held')!;held.active=!!c.holding;
            if(c.holding)this.drawIcon(held.getComponent(Graphics)!,this.itemStage(c.holding));
            const bubble=this.people[who].getChildByName('held-bubble')!;bubble.active=!!c.holding;
            if(c.holding)this.drawIcon(bubble.getChildByName('icon')!.getComponent(Graphics)!,this.itemStage(c.holding));
        }
        const apiConfigured=!!s.connection?.configured&&s.phase!=='ready'&&s.phase!=='ended';
        if(this.jeffThinking)this.jeffThinking.active=this.connected&&apiConfigured&&!!s.ai.thinking&&!s.ai.error;
        if(this.jeffError)this.jeffError.active=apiConfigured&&!!s.ai.error;
        const flightIds=new Set((k.projectiles||[]).map((p:any)=>p.id));
        for(const [id,n]of Object.entries(this.flights))if(!flightIds.has(id)){n.destroy();delete this.flights[id];delete this.flightOrder[id];}
        for(const p of k.projectiles||[])if(!this.flights[p.id]){
            this.flights[p.id]=this.foodNode(p.id,this.itemStage(p),true);
            const from=p.from||[0,0],to=p.to||from,dist=(w:string)=>Math.hypot((k.chefs[w].position?.[0]??0)-from[0],(k.chefs[w].position?.[1]??0)-from[1]);
            const thrower=dist('human')<=dist('jeff')?'human':'jeff';
            if(to[0]!==from[0]||to[1]!==from[1])this.throwReleases[thrower]={dx:to[0]-from[0],dy:to[1]-from[1],until:this.clock+.3};
        }
        this.enable('pause',active);
        this.enable('resume',s.phase==='paused'&&!this.pending&&this.connected);
        this.enable('end',['running','paused'].includes(s.phase)&&!this.pending&&this.connected);
        for(const id of ['pause','resume','end'])this.buttons[id].node.active=true;
        const held=k.chefs.human.holding;this.set('hand','手中：'+(held?this.itemName(held):'空手'));
        if(held?.stage==='assembled')this.set('hand','缺少：'+held.missing.map((x:string)=>this.itemLabel(x)).join('+'));
        {
            const short=(a:Action)=>a.label.split('（')[0],parts:string[]=[];
            if(s.interaction)parts.push('空格 · '+short(s.interaction));
            else if(s.interaction_hint)parts.push(s.interaction_hint);
            if(held&&k.chefs.human.can_throw!==false)parts.push('长按空格 · 瞄准投掷');
            this.set('interaction',this.aiming?'松开空格投掷 · 方向键改方向':parts.length?parts.join('　'):(s.interaction_hint||'面向工位或物品按空格'));
        }
        // Game results keep the event line; Jeff's decisions and errors use their own status.
        const results=s.events.filter(e=>!this.isAiNote(e));
        this.set('event',results.length?results[results.length-1].message:'');
        this.set('ai-status',this.aiStatus(s));
        this.labels['ai-status'].color=color(s.ai.error||(s.limits?.reached&&s.phase==='running')?COLORS.alert:COLORS.muted);
        this.syncLevelButtons(s.levels||[]);
        for(const level of s.levels||[]){
            const id='level:'+level.id,b=this.buttons[id],sel=k.level_id===level.id;b.node.active=s.phase==='ready'||s.phase==='ended';
            this.writeLabel(b.label,level.name+(sel?' · 当前':''));
            if(b.selected!==sel){b.selected=sel;this.styleButton(id);}this.enable(id,!this.pending&&!sel);
        }
        const lang=(window as any).kitchenI18n?.language==='en'?'中文':'English';if(this.buttons.language.label.string!==lang)this.buttons.language.label.string=lang;
        this.cover.active=s.phase!=='running';this.buttons.reset.node.active=true;
        this.enable('main',!this.pending);this.buttons.main.node.active=true;
        this.enable('reset',!this.pending&&s.phase!=='ready');
        this.writeLabel(this.buttons.main.label,s.phase==='ready'?'开始经营':s.phase==='paused'?'继续经营':'准备下一局');
        if(s.phase==='ready'&&s.connection&&!s.connection.configured)this.writeLabel(this.buttons.main.label,'先连接搭档');
        this.labels['welcome-tip'].node.active=s.phase==='ready';
        this.buttons.record.node.active=s.phase==='ended'&&!!s.round_summary;
        // Shown once per round, as soon as its record exists; the button reopens it.
        if(s.phase==='ended'&&s.round_summary&&this.recordShown!==s.game_id){this.recordShown=s.game_id;this.openRecord();}
        // Rounds close at the time limit: say so plainly, whatever the outcome.
        const closed=s.phase==='ended'&&!s.aborted&&k.failure_reason!=='fire_spread';
        this.set('coverTitle',s.phase==='ready'?'ChefJeff':s.phase==='paused'?'歇一小会儿':k.failure_reason==='fire_spread'?'火势失控':s.aborted?'本局已结束':closed?(s.won?'关店结算 · 达成目标':'关店结算 · 未达目标'):s.won?'今天，配合得不错！':'明天再接再厉');
        this.set('coverText',s.phase==='ready'?`你和 AI 搭档，一起照顾这间小厨房。\n本局目标：关店时净收入达到 ¥${k.goals.target_money}`:s.phase==='paused'?'锅火和订单都按下了暂停。\n准备好了，就和 Jeff 接着做菜。':closed?this.closingSummary(k,!!s.won):`出餐 ${k.served} 单 · 净收入 ¥${k.money} / ¥${k.goals.target_money}`);
        this.syncAccess();
        if(this.overlayPhase!==s.phase){
            // Pause defaults to "Resume" so Enter, Space or Esc all return to the kitchen.
            const first=!this.overlayPhase;this.overlayPhase=s.phase;this.setFocus(s.phase==='paused'?'main':'');
            if(!first&&s.phase!=='running')this.announce(this.labelSources.get(this.labels.coverTitle)+'\n'+this.labelSources.get(this.labels.coverText));
        }
        if(s.ai.error&&s.ai.error!==this.lastAiError)this.announce(s.ai.error);
        this.lastAiError=s.ai.error;
        this.cover.setSiblingIndex(this.node.children.length-1);
        for(const id of ['pause','resume','end'])this.buttons[id].node.setSiblingIndex(this.node.children.length-1);
        this.applyTouchLayout();this.syncAccess();this.publishControls();
    }
    private isAiNote(e:{message:string;kind?:string}){return !e.kind&&/^(Jeff |本局 AI)/.test(e.message);}
    private aiStatus(s:KitchenState){
        if(s.limits?.reached&&s.phase==='running')return 'Jeff 已达本局调用上限';
        if(s.ai.error)return 'Jeff 暂时连不上，正在重试';
        const note=[...s.events].reverse().find(e=>this.isAiNote(e));
        const m=note&&/^Jeff 选择：(.*?) \| [\d.]+s(?: \| 未执行：(.*))?$/s.exec(note.message);
        if(m)return m[2]?`Jeff：${m[1]}（未执行）`:`Jeff：${m[1]}`; // full reason stays in the event log/export
        return note?.message.startsWith('Jeff 请求失败')?'Jeff 暂时连不上，正在重试':'';
    }
    // Keeps the screen-reader proxies in step with the visible canvas buttons.
    private syncAccess(){
        if(!this.controlAccess)return;
        const icons:Record<string,string>={pause:'暂停',resume:'继续经营',end:'结束本局'};
        for(const id of this.tabOrder()){
            const b=this.buttons[id],proxy=this.controlAccess.querySelector(`[data-control="${id}"]`) as HTMLButtonElement|null;if(!proxy)continue;
            const text=id==='language'?b.label.string:icons[id]||this.labelSources.get(b.label)||id;
            if(id==='language')proxy.setAttribute('data-no-i18n','');
            if(proxy.dataset.source!==text){proxy.dataset.source=text;proxy.textContent=text;}
            proxy.disabled=!b.enabled;proxy.hidden=!b.node.activeInHierarchy;
        }
    }
    update(dt:number){
        this.clock+=dt;this.audio.update(dt);if(!this.state||!this.mounted)return;const k=this.state.kitchen;
        if(this.touchMoveDirty&&this.clock-this.touchMoveAt>=.05)this.flushTouchMove();
        if(this.spaceDownAt!==null&&this.clock-this.spaceDownAt>=AIM_HOLD)this.startAim();
        if(this.aiming&&this.state.phase!=='running')this.endAim();
        if(this.aiming)this.drawAim();
        // Result pops rise and fade over 1.4s (no rise with reduced motion); header numbers pulse.
        this.pops=this.pops.filter(p=>{
            const age=(this.clock-p.born)/1.4;if(age>=1||!p.node.isValid){p.node.destroy();return false;}
            if(!this.reduceMotion)p.node.setPosition(p.node.position.x,p.y+34*(1-(1-age)*(1-age)));
            const a=Math.round(255*(age<.6?1:1-(age-.6)/.4));
            p.label.color=new Color(p.fill.r,p.fill.g,p.fill.b,a);p.label.shadowColor=new Color(43,26,18,a);return true;
        });
        for(const [id,f] of Object.entries(this.flashes)){
            const left=f.until-this.clock,n=this.labels[id].node;
            if(left<=0){delete this.flashes[id];n.setScale(1,1,1);this.labels[id].color=color(this.statColor(id));continue;}
            const s=this.reduceMotion?1:1+.18*Math.max(0,left-.9)/.3;n.setScale(s,s,1);
        }
        const running=this.connected&&!this.hidden&&this.state.phase==='running';
        const animate=running&&!this.qaNoMotion;
        if(animate)this.activeClock+=dt;
        for(const who of ['human','jeff']){
            const c=k.chefs[who],p=c.position,n=this.people[who],motion=this.motions[who];
            // A chef who isn't chopping never shows a knife, even on frames that skip characterArt.
            if(!(c.working&&c.action_kind==='chop'))for(const layer of [this.knives[who],this.knifeHands[who]])if(layer?.isValid)layer.active=false;
            const dust=n.getChildByName('sprint-dust')!;
            dust.active=!!animate&&c.sprint?.active_remaining>0&&(c.manual_moving||c.travel_remaining>0);
            if(dust.active){
                const frame=Math.floor(this.activeClock*10)%7,g=dust.getComponent(Graphics)!;
                dust.setPosition(motion.facing==='left'?22:motion.facing==='right'?-22:0,this.useModularArt?(motion.facing==='up'?-12:motion.facing==='down'?12:-2):-25);
                if(this.useModularArt&&this.art.centered(dust,`modular/sprint_dust_${frame%4}`,32,14))g.clear();
                else if(this.useArt&&this.art.show(dust,`vfx/landing_${frame}`,52,28))g.clear();
                else {g.clear();for(let i=0;i<3;i++)this.rect(g,-20+i*13,-3+(frame+i)%3*3,7,5,'#d8bf93');}
            }
            if(running&&p){
                const predicted=who==='human'?this.predictHuman(k,c,dt,n):null,at=predicted||p;
                const x=MAPX+(at[0]+.5)*TILE-640,y=360-MAPY-(at[1]+.5)*TILE,t=predicted?1:Math.min(1,dt*16);
                const oldX=n.position.x,oldY=n.position.y;
                n.setPosition(oldX+(x-oldX)*t,oldY+(y-oldY)*t);
                const dx=n.position.x-oldX,dy=n.position.y-oldY,moved=Math.hypot(dx,dy)>.08&&(!!predicted||(c.travel_remaining||0)>0||Math.hypot(x-n.position.x,y-n.position.y)>1);
                if(moved){
                if((c.manual_moving||predicted)&&who==='human'&&(this.manualDirection.x!==0||this.manualDirection.y!==0)){
                    if(Math.abs(this.manualDirection.x)>=Math.abs(this.manualDirection.y))motion.facing=this.manualDirection.x<0?'left':'right';
                    else motion.facing=this.manualDirection.y<0?'up':'down';
                }else if(Math.abs(dx)>=Math.abs(dy))motion.facing=dx<0?'left':'right';
                else motion.facing=dy>0?'up':'down';
                }
                // Authoritative orientation survives short actions between polls.
                if(!moved&&c.facing)motion.facing=c.facing;
                if(c.working&&c.facing)motion.facing=c.facing;
                const held=who==='human'&&(this.manualDirection.x!==0||this.manualDirection.y!==0);
                const walkIntent=(predicted?held:!!c.manual_moving)||(!c.working&&(c.travel_remaining||0)>0);
                if(this.characterArt(motion.body,who,motion.facing,animate&&walkIntent,!!c.working))continue;
                motion.body.angle=0;
                const side=motion.facing==='left'||motion.facing==='right';
                motion.body.getChildByName('eyes')!.active=motion.facing!=='up'&&!side;
                motion.body.getChildByName('profile')!.active=side;
                motion.body.getChildByName('eyes')!.setPosition(side?4:0,19);
                motion.body.getChildByName('eyes')!.setScale(side?.65:1,1,1);
                motion.body.getChildByName('back')!.active=motion.facing==='up';
                const facingScale=motion.facing==='left'?-.87:motion.facing==='right'?.87:1;
                const walking=animate&&walkIntent;
                const chopping=animate&&!walking&&c.action_kind==='chop'&&c.working&&(c.work_remaining||0)>.02;
                motion.knife.active=chopping;
                if(walking||chopping){
                    motion.step+=dt*(chopping?13:16.5);
                    const swing=Math.sin(motion.step);
                    motion.leftLeg.setPosition(-7,walking? -24+Math.max(0,swing)*3:-24);
                    motion.rightLeg.setPosition(7,walking? -24+Math.max(0,-swing)*3:-24);
                    motion.leftArm.angle=walking?-swing*15:0;
                    motion.rightArm.angle=chopping?Math.sin(motion.step*1.8)*48:walking?swing*15:0;
                    if(chopping)this.knifeStrike(who,(motion.step*1.8/(2*Math.PI)+.75)%1,.5);
                    motion.body.setPosition(0,walking?Math.abs(swing)*1.2:0);
                    motion.body.setScale(facingScale,1,1);
                }else{
                    motion.leftLeg.setPosition(-7,-24);motion.rightLeg.setPosition(7,-24);
                    motion.leftArm.angle=0;motion.rightArm.angle=0;
                    const breath=c.action_kind||!animate?0:Math.sin(this.activeClock*2.2);
                    motion.body.setPosition(0,breath*.7);motion.body.setScale(facingScale,1+breath*.008,1);
                }
            }
        }
        for(const flame of Object.values(this.cabinetFires))if(flame.active){
            const g=flame.getComponent(Graphics)!;
            if(this.useArt&&this.art.show(flame,`vfx/fire_${Math.floor(this.activeClock*8)%7}`,58,72))g.clear();
            else this.drawIcon(g,'fire');
            const smoke=flame.getChildByName('smoke')!;
            if(this.useArt)this.art.show(smoke,`vfx/smoke_${Math.floor(this.activeClock*6)%7}`,42,42);
        }
        if(animate){
            for(const [id,e] of Object.entries(this.potEffects)){
                if(this.useArt){
                    const frame=Math.floor(this.activeClock*8)%7;
                    for(const [node,key] of [[e.steam,'steam'],[e.smoke,'smoke'],[e.fire,'fire']] as [Node,string][]){
                        if(node.active&&this.art.show(node,`vfx/${key}_${frame}`,key==='fire'?75:42,key==='fire'?75:42))node.getComponent(Graphics)?.clear();
                    }
                }
                if(e.steam.active)e.steam.setPosition(-11+Math.sin(this.activeClock*3+id.length)*3,38+Math.sin(this.activeClock*4+id.length)*3);
                if(e.smoke.active)e.smoke.setPosition(13+Math.sin(this.activeClock*2.4+id.length)*2,38+Math.sin(this.activeClock*3+id.length)*2);
                if(e.fire.active)e.fire.setScale(.55+Math.sin(this.activeClock*12)*.035,.55+Math.sin(this.activeClock*12+1)*.06,1);
                if(e.ready.active)e.ready.setScale(.85+Math.sin(this.activeClock*12)*.12,.85+Math.sin(this.activeClock*12)*.12,1);
            }
            if(this.jeffThinking?.active)this.jeffThinking.setScale(.92+Math.sin(this.activeClock*5)*.08,.92+Math.sin(this.activeClock*5)*.08,1);
        }
        const sink=this.devices.sink?.node.getChildByName('washing');
        if(sink){const washing=Object.values(k.chefs).some((c:any)=>c.action_kind==='wash'&&c.working);sink.active=washing;
            if(this.useArt&&washing&&this.art.show(sink,`vfx/splash_${Math.floor(this.activeClock*8)%7}`,38,38))sink.getComponent(Graphics)?.clear();
            if(washing&&this.state.phase==='running'&&this.connected&&!this.hidden){sink.setPosition(0,this.workSurfaceY('sink')+Math.sin(this.clock*7)*3);sink.setScale(1+.12*Math.sin(this.clock*5),1,1);}}
        if(running&&(this.manualDirection.x!==0||this.manualDirection.y!==0)&&this.clock-this.lastMoveAt>=.15)this.sendMove(this.manualDirection.x,this.manualDirection.y);
        const time=k.time+(this.state.phase==='running'&&this.connected?(this.clock-this.received)*this.state.speed:0);
        for(const p of k.projectiles||[]){
            const t=Math.max(0,Math.min(1,(time-p.started)/(p.lands_at-p.started))),arc=Math.sin(t*Math.PI)*35;
            const point=[p.from[0]+(p.to[0]-p.from[0])*t,p.from[1]+(p.to[1]-p.from[1])*t];
            // A board/counter landing ends on its work surface, drawn over the cabinet like a resting item.
            const onto=p.onto&&k.map.equipment[p.onto]?p.onto:null,height=arc+(onto?t*this.workSurfaceY(onto):0);
            this.locate(this.flights[p.id],point,height);
            this.flightOrder[p.id]=onto&&t>=.5?Math.max(flightDepth(point[1],height),depthOrder(k.map.equipment[onto].cell[1],'solid')+.02):flightDepth(point[1],height);
        }
        this.sortWorld();
    }
}
