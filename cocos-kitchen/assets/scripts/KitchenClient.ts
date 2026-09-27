import { _decorator, Component, Node, UITransform, Graphics, Color, Label, Layers,
    view, ResolutionPolicy, sys, game, Game, profiler, Mask, Vec2 } from 'cc';
import { LevelOneArt } from './LevelOneArt';
import { GRID_ART, stationView, trashView, wallNeighbours, surfaceOffset, wallOffset, depthOrder, workingChefDepth, flightDepth, burgerLayers, heatCountdown } from './KitchenGeometry';
const { ccclass } = _decorator;
type Action = { key: string; label: string; kind: string; target: string; expected: unknown[] };
type KitchenState = { game_id: string; phase: string; speed: number; kitchen: any; actions: Action[]; limits?:any; release?:any; interaction?:Action; interaction_hint?:string; interaction_focus?:string; interaction_cell?:number[];
    events: {t:number; message:string; kind?:string}[]; ai: {thinking:boolean; error:string|null}; won:boolean; aborted?:boolean; rules?:Record<string,number>; connection?:any; memory?:any; communication?:any };
type ChefMotion = {body:Node; leftLeg:Node; rightLeg:Node; leftArm:Node; rightArm:Node; knife:Node; facing:string; step:number};
type PotEffects = {steam:Node; smoke:Node; fire:Node; ready:Node};
// Warm timber, enamel and order slips. Shapes use a shared 2–4 px pixel grid.
const COLORS = { ink:'#382f29', muted:'#786b59', bg:'#e7d7b8', paper:'#fff5dc', line:'#c2a67d',
    human:'#4c7661', jeff:'#567fa4', hot:'#b64032', counter:'#8baab7', counterEdge:'#587582', counterLight:'#c6d9de', wall:'#ae8055', wood:'#795539', light:'#f6e8ca',
    // Text variants keep ≥4.5:1 on paper/background; the fills above stay for art.
    humanText:'#3d6250', jeffText:'#3e6690', hint:'#5f5446', alert:'#9c3226' };
// Result events reach the player; AI decision notes have their own status line.
const RESULT_ANNOUNCE=new Set(['order','served','bad_service','expired','ready','burn','fire','fire_spread','fire_loss']);
const TAB_ORDER=['level1','level2','level3','main','reset','cover-connection','help','resume','pause','end'];
type ButtonView = {node:Node;label:Label;callback:()=>void;enabled:boolean;width:number;height:number;tone:string;hover:boolean};
const STAGES: Record<string,string> = {raw:'生肉',chopped:'半成品',cooking:'加热中',ready:'熟牛排',burnt:'糊菜',extinguisher:'灭火器',clean_plate:'干净餐盘',dirty_plate:'脏餐盘',plated_ready:'已装盘牛排',plated_burnt:'已装盘糊菜',pot:'空锅',pot_cooking:'锅 · 未熟',pot_chopped:'锅 · 未熟',pot_ready:'锅 · 熟牛排',pot_burnt:'锅 · 糊菜'};
const FOOD_COLORS: Record<string,string> = {raw:'#d68f8c',chopped:'#dcaa86',cooking:'#b58359',ready:'#846144',burnt:'#3e3733',extinguisher:'#c65138'};
const TILE=GRID_ART.tile, MAPX=GRID_ART.originX, MAPY=GRID_ART.originY;
const color=(hex:string)=>new Color().fromHEX(hex);

@ccclass('KitchenClient')
export class KitchenClient extends Component {
    private state: KitchenState|null=null;
    private art=new LevelOneArt();
    private artLoaded=false;
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
    private throwReady=false;
    private spacePressedAt:number|null=null;
    private spaceHold=false;
    private qaNoMotion=!sys.isNative&&new URLSearchParams(location.search).get('qaMotion')==='off';
    // Isolated visual pilot; not enabled at the fixed gameplay entry.
    private prepSample=!sys.isNative&&new URLSearchParams(location.search).get('prepSample')==='1';
    private prepPoses:Record<string,Node>={};
    // Knife-only comparison: same normal scene and actor in both variants.
    private knifeSample=!sys.isNative&&new URLSearchParams(location.search).get('knifeSample')==='1';
    private knifeProbe:Node|null=null;
    private cutProbe:Node|null=null;
    private pairedKnives:Record<string,Node>={};
    private pairedFacing:Record<string,string>={};
    private pairedImpacts:Record<string,Node>={};
    private received=0;
    private focusMarker:Node|null=null;
    private selection={kind:'none',id:''};
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
    private lastDirectionTap={key:"",time:-10};
    // Native debug builds use USB forwarding: adb reverse tcp:8769 tcp:8769.
    // Production releases replace this with the operator's HTTPS game backend, never a Jev API key.
    private endpoint=sys.isNative?'http://127.0.0.1:8769':'';

    start(){
        if(!sys.isNative)document.getElementById('kitchen-loading')?.remove();
        if(!sys.isNative&&new URLSearchParams(location.search).has('qaPerf'))profiler.showStats();else profiler.hideStats();
        view.setDesignResolutionSize(1280,720,ResolutionPolicy.SHOW_ALL);
        this.node.getComponent(UITransform)!.setContentSize(1280,720);
        this.box(this.node,'background',640,360,1280,720,COLORS.bg);
        this.box(this.node,'header',640,35,1280,70,COLORS.paper);
        this.icon(this.node,'brand-icon',45,35,'pot',1.1);
        this.text('brand','ChefJeff',80,30,170,36,27).isBold=true;
        this.text('edition','和AI一起经营餐馆',81,53,290,20,11).color=color(COLORS.muted);
        for(const [i,id,title] of [[0,'served','完成订单'],[1,'money','营业收入'],[2,'reviews','顾客差评']] as [number,string,string][]){
            const x=690+i*130;
            this.text(id+'-title',title,x,19,120,20,12).color=color(COLORS.muted);
            this.text(id,'—',x,46,120,32,24).isBold=true;
        }
        this.text('clock','准备开店',470,34,220,28,20).fontFamily='monospace';
        this.box(this.node,'order-rail',640,81,812,8,COLORS.wood);
        for(let i=0;i<5;i++){
            const x=234+i*164,n=this.make('ticket-'+i,x+78,112,156,67);this.tickets.push(n);
            this.text('order-id-'+i,'',x+12,96,145,18,12);
            this.text('order-name-'+i,'',x+12,111,87,21,16).isBold=true;
            this.text('order-time-'+i,'',x+103,111,45,22,14).fontFamily='monospace';
        }
        // Map geometry has a shared projection; the exterior remains plain.
        this.text('sprint-status','',1070,63,190,16,11).horizontalAlign=Label.HorizontalAlign.RIGHT;
        this.text('fire-status','',1060,112,205,25,14).color=color(COLORS.alert);
        // End sits apart from pause/resume; both destructive actions ask first.
        this.button('pause','Ⅱ',1100,34,44,36,()=>this.post('/api/pause'));
        this.button('resume','▶',1152,34,44,36,()=>this.post('/api/resume'),this.node,'primary');
        this.button('end','■',1226,34,44,36,()=>this.confirm('end'),this.node,'danger');
        for(const id of ['pause','resume','end'])this.buttons[id].label.fontSize=22;
        this.text('hand','',234,691,235,22,14).color=color(COLORS.ink);
        this.text('interaction','',470,691,575,22,14).color=color(COLORS.ink);
        this.text('event','',234,709,500,18,13).color=color(COLORS.ink);
        this.text('ai-status','',744,709,302,18,13).horizontalAlign=Label.HorizontalAlign.RIGHT;
        this.cover=this.make('cover',640,360,1280,720);
        this.cover.on(Node.EventType.TOUCH_END,(e:any)=>{e.propagationStopped=true;});
        const shade=this.cover.addComponent(Graphics);shade.fillColor=new Color(40,32,25,160);shade.rect(-640,-360,1280,720);shade.fill();
        // A cafe awning frames the start/pause board; the kitchen stays visible behind it.
        this.box(this.cover,'welcome-shadow',646,367,736,464,COLORS.ink);
        this.box(this.cover,'welcome-board',640,358,736,464,COLORS.paper);
        for(let i=0;i<16;i++)this.box(this.cover,'awning',295+i*46,145,46,38,i%2?COLORS.light:COLORS.human);
        this.text('welcome-kicker','和AI一起经营餐馆',340,193,600,25,13,this.cover).horizontalAlign=Label.HorizontalAlign.CENTER;
        this.text('coverTitle','ChefJeff',316,257,648,64,46,this.cover).isBold=true;
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
        this.button('level1','第一关 · 牛排',414,464,210,28,()=>this.post('/api/level',{level:1}),this.cover);
        this.button('level2','第二关 · 汉堡',640,464,210,28,()=>this.post('/api/level',{level:2}),this.cover);
        this.button('level3','第三关 · 牛-堡',866,464,210,28,()=>this.post('/api/level',{level:3}),this.cover);
        this.text('welcome-tip','先看操作说明，准备好了就开店。',333,577,614,19,11,this.cover).horizontalAlign=Label.HorizontalAlign.CENTER;
        if(!sys.isNative){
            // Screen-reader proxies for every canvas button. Canvas focus moves DOM
            // focus to the matching proxy so assistive technology follows it.
            this.controlAccess=document.createElement('div');
            this.controlAccess.style.cssText='position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);';
            for(const id of TAB_ORDER){
                const b=document.createElement('button');b.dataset.control=id;b.tabIndex=-1;
                b.onclick=()=>{if(this.buttons[id].enabled)this.buttons[id].callback();};
                this.controlAccess.appendChild(b);
            }
            document.body.appendChild(this.controlAccess);
            const canvas=document.getElementById('GameCanvas');
            canvas?.setAttribute('role','img');canvas?.setAttribute('aria-label','ChefJeff 厨房画面');
        }
        game.on(Game.EVENT_HIDE,this.onHide,this);game.on(Game.EVENT_SHOW,this.onShow,this);
        if(!sys.isNative){window.addEventListener('kitchen-language-changed',this.onLanguage);window.addEventListener('kitchen-confirmed',this.onConfirmed);window.addEventListener('keydown',this.onKey,true);window.addEventListener('keyup',this.onKeyUp,true);window.addEventListener('mousedown',this.onMouseDown,true);window.addEventListener('mouseup',this.onMouseUp,true);window.addEventListener('blur',this.onBlur);document.addEventListener('visibilitychange',this.onVisibility);document.addEventListener('contextmenu',this.onContextMenu);}
        // Idle screens need neither gameplay frame rate nor five snapshots a second.
        game.frameRate=15;
        this.art.load().then(()=>{this.artLoaded=true;if(this.isValid)this.poll();});this.schedule(this.scheduledPoll,.2);
    }
    onDestroy(){this.controlAccess?.remove();this.clearInput();game.off(Game.EVENT_HIDE,this.onHide,this);game.off(Game.EVENT_SHOW,this.onShow,this);if(!sys.isNative){window.removeEventListener('kitchen-language-changed',this.onLanguage);window.removeEventListener('kitchen-confirmed',this.onConfirmed);window.removeEventListener('keydown',this.onKey,true);window.removeEventListener('keyup',this.onKeyUp,true);window.removeEventListener('mousedown',this.onMouseDown,true);window.removeEventListener('mouseup',this.onMouseUp,true);window.removeEventListener('blur',this.onBlur);document.removeEventListener('visibilitychange',this.onVisibility);document.removeEventListener('contextmenu',this.onContextMenu);}}
    private onHide(){this.hidden=true;this.clearInput();if(this.state?.phase==='running')this.post('/api/pause',{reason:'hidden'});}
    private onShow(){this.hidden=false;this.poll();}
    private onBlur=()=>this.clearInput();
    private onVisibility=()=>{if(document.hidden)this.clearInput();};
    private onContextMenu=(e:MouseEvent)=>{if((e.target as HTMLElement)?.closest('canvas'))e.preventDefault();};
    private onMouseDown=(e:MouseEvent)=>{if(e.button===2&&(e.target as HTMLElement)?.closest('canvas')){e.preventDefault();e.stopImmediatePropagation();this.onRightClick();}};
    private onMouseUp=(e:MouseEvent)=>{if(e.button===2&&(e.target as HTMLElement)?.closest('canvas')){e.preventDefault();e.stopImmediatePropagation();}};
    private openHelp(){this.clearInput();if(!sys.isNative)window.dispatchEvent(new Event('kitchen-open-help'));}
    private openConnection(){this.clearInput();if(!sys.isNative)window.dispatchEvent(new Event('kitchen-open-connection'));}
    private onKey=(e:KeyboardEvent)=>{
        // The communication dock keeps native Tab/Enter/Space; Esc hands the keyboard back.
        const dock=!sys.isNative?(document.activeElement as HTMLElement)?.closest('#kitchen-communication') as HTMLElement|null:null;
        if(e.key==='Escape'){
            if(dock){(document.activeElement as HTMLElement).blur();return;}
            if(e.repeat||(!sys.isNative&&document.querySelector('dialog[open]')))return;
            if(this.state?.phase==='running'){e.preventDefault();this.clearInput();this.post('/api/pause');}
            else if(this.state?.phase==='paused'&&this.connected){e.preventDefault();this.post('/api/resume');}
            return;
        }
        if(e.isComposing||e.keyCode===229)return;
        if(!sys.isNative&&(document.querySelector('dialog[open]')||(document.activeElement as HTMLElement)?.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]')))return;
        if(dock&&(e.key==='Enter'||e.code==='Space'||e.key==='Tab'))return;
        if(e.key==='Shift'&&this.state?.phase==='running'){
            e.preventDefault();e.stopImmediatePropagation();
            if(!e.repeat&&!e.ctrlKey&&!e.altKey&&!e.metaKey)this.bookmark();
            return;
        }
        if(this.state?.phase==='running'&&this.connected){
            if(e.code==='Space'){
                e.preventDefault();
                if(!e.repeat&&this.spacePressedAt===null){this.spacePressedAt=this.clock;this.spaceHold=false;this.throwReady=false;this.updateThrowCue();}
                return;
            }
            const key=e.key.toLowerCase();if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright'].includes(key)){e.preventDefault();
                const fresh=!e.repeat&&!this.heldKeys.has(key);
                const dash=fresh&&this.lastDirectionTap.key===key&&this.clock-this.lastDirectionTap.time<=.3;
                if(fresh)this.lastDirectionTap={key,time:dash?-10:this.clock};
                this.heldKeys.add(key);this.refreshMovement(dash);return;}
        }
        if(e.key==='Tab'){
            e.preventDefault();const ids=TAB_ORDER.filter(id=>this.buttons[id].enabled&&this.buttons[id].node.activeInHierarchy);
            if(!ids.length)return;const at=ids.indexOf(this.focusId);
            this.setFocus(ids[(at+(e.shiftKey?-1:1)+ids.length)%ids.length]);
        }else if(e.key==='Enter'&&this.focusId){const b=this.buttons[this.focusId];if(b?.enabled&&b.node.activeInHierarchy){e.preventDefault();b.callback();}}
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
        if(e.code==='Space'&&this.spacePressedAt!==null){
            e.preventDefault();const held=this.spaceHold||this.clock-this.spacePressedAt>=.3;
            this.spacePressedAt=null;this.spaceHold=false;this.throwReady=false;this.updateThrowCue();
            if(!held&&this.state?.phase==='running'&&this.connected&&!this.hidden)
                this.post('/api/interact',{expected_item:this.state.kitchen.chefs.human.holding?.id||null});
            return;
        }
        const key=e.key.toLowerCase();if(this.heldKeys.delete(key))this.refreshMovement();
    };
    private updateSpaceGesture(){
        if(this.connected&&!this.hidden&&this.state?.phase==='running'&&this.spacePressedAt!==null
                &&!this.spaceHold&&this.clock-this.spacePressedAt>=.3){
            this.spaceHold=true;if(!this.throwReady)this.toggleThrow();
        }
    }
    private toggleThrow(){const hand=this.state?.kitchen.chefs.human.holding;if(!this.throwReady&&(!hand||!['raw','chopped'].includes(hand.stage)||!!hand.plate_id)){this.set('event','只能抛生食材或切好的原料；餐盘、带盘菜、锅和工具请放下或搬运。');return;}this.throwReady=!this.throwReady;this.updateThrowCue();}
    private updateThrowCue(){this.set('interaction',this.throwReady?(this.spaceHold?'按住空格 · 左键选落点':'抛掷已准备 · 左键选落点'):'');if(!sys.isNative){const canvas=document.querySelector('canvas') as HTMLCanvasElement|null;if(canvas)canvas.style.cursor=this.throwReady?'crosshair':'';}}
    private async sendMove(dx:number,dy:number,sprint=false){if(!this.state||this.state.phase!=='running'||!this.connected)return;const seq=++this.moveSeq;this.lastMoveAt=this.clock;try{await this.request('/api/move',{game_id:this.state.game_id,dx,dy,seq,sprint});}catch(e){this.set('event',(e as Error).message);}}
    private refreshMovement(sprint=false){
        const x=(this.heldKeys.has('d')||this.heldKeys.has('arrowright')?1:0)-(this.heldKeys.has('a')||this.heldKeys.has('arrowleft')?1:0);
        const y=(this.heldKeys.has('s')||this.heldKeys.has('arrowdown')?1:0)-(this.heldKeys.has('w')||this.heldKeys.has('arrowup')?1:0),mag=Math.hypot(x,y);
        const dx=mag?x/mag:0,dy=mag?y/mag:0;if(!sprint&&dx===this.manualDirection.x&&dy===this.manualDirection.y)return;
        this.manualDirection={x:dx,y:dy};this.sendMove(dx,dy,sprint);
    }
    private clearInput(){this.lastDirectionTap={key:"",time:-10};this.heldKeys.clear();this.spacePressedAt=null;this.spaceHold=false;const wasMoving=this.manualDirection.x!==0||this.manualDirection.y!==0;this.manualDirection={x:0,y:0};this.throwReady=false;this.updateThrowCue();if(wasMoving)this.sendMove(0,0);}
    private cancelManualMovement(){this.heldKeys.clear();if(this.manualDirection.x!==0||this.manualDirection.y!==0){this.manualDirection={x:0,y:0};this.sendMove(0,0);}}
    private onRightClick(){if(this.state?.phase==='running'&&this.connected)this.toggleThrow();}
    private mapTarget(x:number,y:number){if(this.throwReady){this.throwTo([x,y]);return true;}return false;}
    private async throwTo(target:number[]){
        if(!this.state)return;const held=this.state.kitchen.chefs.human.holding,gameId=this.state.game_id;
        this.throwReady=false;this.updateThrowCue();this.cancelManualMovement();if(!held)return;
        try{await this.request('/api/throw',{game_id:gameId,target,expected_item:held.id,request_id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)});}
        catch(e){this.set('event',(e as Error).message);}finally{this.poll();}
    }
    private make(name:string,x:number,y:number,w:number,h:number,parent=this.node){
        const n=new Node(name);n.layer=Layers.Enum.UI_2D;parent.addChild(n);
        n.addComponent(UITransform).setContentSize(w,h);n.setPosition(x-640,360-y);return n;
    }
    private child(parent:Node,name:string,w:number,h:number,x=0,y=0){
        const n=new Node(name);n.layer=Layers.Enum.UI_2D;parent.addChild(n);n.addComponent(UITransform).setContentSize(w,h);n.setPosition(x,y);return n;
    }
    private rect(g:Graphics,x:number,y:number,w:number,h:number,fill:string){g.fillColor=color(fill);g.rect(x,y,w,h);g.fill();}
    // Selected target: ink edge for contrast on any floor or counter, green for the player.
    private focusFrame(g:Graphics,x:number,y:number,w:number,h:number){
        g.lineWidth=2;g.strokeColor=color(COLORS.ink);g.rect(x+1,y+1,w-2,h-2);g.stroke();
        g.lineWidth=3;g.strokeColor=color(COLORS.human);g.rect(x+3.5,y+3.5,w-7,h-7);g.stroke();
    }
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
        const l=labelNode.addComponent(Label);this.writeLabel(l,title);l.fontSize=17;l.lineHeight=22;l.isBold=true;l.overflow=Label.Overflow.SHRINK;l.verticalAlign=Label.VerticalAlign.CENTER;
        this.buttons[id]={node:n,label:l,callback,enabled:true,width:w,height:h,tone,hover:false};this.styleButton(id);
        n.on(Node.EventType.MOUSE_ENTER,()=>{const b=this.buttons[id];if(b){b.hover=true;this.styleButton(id);}});
        n.on(Node.EventType.MOUSE_LEAVE,()=>{const b=this.buttons[id];if(b){b.hover=false;this.styleButton(id);}});
        n.on(Node.EventType.TOUCH_END,()=>{const b=this.buttons[id];if(b?.enabled)b.callback();});return n;
    }
    private styleButton(id:string){
        const b=this.buttons[id];if(!b)return;
        const fill=!b.enabled?'#d9cbb1':b.tone==='primary'?(b.hover?'#3d6551':COLORS.human):b.hover?'#ffe4a5':COLORS.paper;
        const g=this.paintBox(b.node,b.width,b.height,fill);
        g.strokeColor=color(b.tone==='primary'?COLORS.human:COLORS.line);g.lineWidth=2;
        g.rect(-b.width/2+1,-b.height/2+1,b.width-2,b.height-2);g.stroke();
        // Keyboard focus: an ink ring outside the button (and its shadow) with a gap,
        // readable on paper, background and the green primary button alike.
        if(this.focusId===id){g.strokeColor=color(COLORS.ink);g.lineWidth=3;g.rect(-b.width/2-5,-b.height/2-8,b.width+10,b.height+13);g.stroke();}
        b.label.color=color(!b.enabled?'#82755f':b.tone==='primary'?COLORS.paper:b.tone==='danger'?COLORS.hot:COLORS.ink);
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
        if(type.startsWith('pot_')){
            this.drawIcon(g,'pot');r(-10,-4,20,13,FOOD_COLORS[type.slice(4)]||'#b58359');
        }else if(type==='stove'){
            r(-23,-19,46,35,COLORS.wood);r(-20,-15,40,28,'#a3aaa0');r(-12,-6,24,16,COLORS.ink);r(-8,-3,16,10,'#6e746b');
        }else if(type==='continuous_counter'){
            // Continuous worktop is painted once in the map layer.
        }else if(/^(lettuce|tomato|bread)_/.test(type)){
            const kind=type.split('_')[0],chopped=type.endsWith('chopped');
            const c=kind==='lettuce'?'#639650':kind==='tomato'?'#c45643':'#d1a362';
            r(-18,-12,36,24,c);r(-12,12,24,5,c);
            if(kind==='tomato')r(-4,14,8,5,'#639650');
            if(chopped){r(-2,-12,3,27,COLORS.paper);r(-18,-1,36,3,COLORS.paper);}
            if(kind==='bread'){r(-13,9,3,3,COLORS.paper);r(5,5,3,3,COLORS.paper);}
        }else if(type.startsWith('assembly:')){
            this.drawIcon(g,'clean_plate');
            const parts=type.slice(9).split(',');let y=-8;
            for(const name of ['bread','beef','lettuce','tomato'])if(parts.includes(name)){
                r(-13,y,26,5,name==='bread'?'#d1a362':name==='beef'?'#846144':name==='lettuce'?'#639650':'#c45643');y+=5;
            }
            if(parts.length===4)r(-12,y,24,4,'#d1a362');
        }else if(type==='counter'){
            r(-24,-19,48,36,COLORS.wood);r(-20,-14,40,26,'#b48b5e');r(-24,12,48,8,'#dfbd88');r(-2,-10,3,20,COLORS.wood);
        }else if(type.startsWith('plated_')){
            r(-23,-17,46,7,'#829fac');r(-21,-14,42,30,COLORS.paper);
            r(-17,-11,34,24,'#c4dce0');r(-15,-9,30,20,COLORS.paper);
            const c=type==='plated_ready'?'#846144':'#3e3733';r(-12,-5,24,15,c);r(-7,3,4,3,'#d6af74');
        }else if(type==='clean_plate'||type==='dirty_plate'||type==='plates'||type==='returns'){
            r(-22,-15,44,28,'#8ca7ac');r(-19,-12,38,24,COLORS.paper);r(-14,-8,28,16,'#dbe7df');
            if(type==='dirty_plate'||type==='returns'){r(-11,-5,12,5,'#917451');r(5,2,6,4,'#917451');}
            if(type==='plates'){r(-22,-20,44,3,COLORS.paper);r(-22,-24,44,3,'#8ca7ac');}
        }else if(type==='sink'){
            r(-23,-18,46,36,'#718f95');r(-19,-13,38,26,'#bbd6d6');r(-15,-8,30,16,'#729ca8');
            r(8,13,5,14,COLORS.ink);r(-4,23,16,5,COLORS.ink);r(-5,14,5,10,'#b9d6dc');
        }else if(type==='pot'){
            r(-18,-13,36,27,COLORS.ink);r(-14,-10,28,21,'#747e75');r(-21,7,42,5,COLORS.ink);r(-24,1,7,7,COLORS.ink);r(17,1,7,7,COLORS.ink);r(-9,15,18,4,'#aab7a4');r(-3,19,6,4,COLORS.ink);
        }else if(type==='fridge'){
            r(-18,-24,36,48,COLORS.ink);r(-15,-20,30,41,'#a4c1b5');r(-13,6,26,13,'#cee0c8');r(-13,-17,26,20,'#cee0c8');r(6,10,3,6,COLORS.ink);r(6,-5,3,8,COLORS.ink);
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
            r(-19,-13,38,26,COLORS.paper);r(-14,-10,28,20,COLORS.ink);r(-13,-6,26,15,c);r(-9,9,18,3,c);r(-6,-2,4,4,type==='raw'?'#efd3ae':'#d6af74');r(3,3,6,3,type==='raw'?'#efd3ae':'#d6af74');
        }
    }
    private artIcon(node:Node,type:string):boolean {
        for(const child of node.children)if(child.name==='assembly-parts'||child.name==='supply-symbol'||child.name==='pot-contents')child.active=false;
        if(this.useModularArt){
            if(type==='bin'){this.art.hide(node);return true;}
            const tops:Record<string,string>={board:'top_board',sink:'top_sink',stove:'top_stove',returns:'top_returns',serve:'serving_window',bin:'bin'};
            if(type==='extinguisher_rack')return this.art.show(node,'objects/extinguisher',32,40,0,18);
            if(type==='serve'){
                const facing=this.state?.kitchen.map.equipment.serve?.facing;
                return this.art.tile(node,facing==='east'?'serving_east':'serving_west',TILE);
            }
            if(tops[type]&&this.art.tile(node,tops[type],TILE))return true;
            if(type==='fridge'||type.startsWith('source_')){
                this.art.hide(node);
                let symbol=node.getChildByName('supply-symbol');
                if(!symbol){symbol=this.child(node,'supply-symbol',40,32,0,22*TILE/64);symbol.addComponent(Graphics);}
                symbol.active=true;const g=symbol.getComponent(Graphics)!;g.clear();
                const sourceKey='modular/source_'+(type==='fridge'?'beef':type.slice(7));
                if(!this.art.centered(symbol,sourceKey,28,28)){
                    const fallback=symbol.getChildByName('fallback')||this.child(symbol,'fallback',28,28);
                    const fg=fallback.getComponent(Graphics)||fallback.addComponent(Graphics);fallback.setScale(.6,.6,1);this.drawIcon(fg,type.slice(7)+'_raw');
                }
                return true;
            }
        }
        if(['lettuce_chopped','tomato_chopped'].includes(type)&&this.art.has('feedback/'+type.split('_')[0]))
            return this.art.centered(node,'feedback/'+type.split('_')[0],30,30);
        if(/^(lettuce|tomato|bread)_/.test(type)&&this.art.has('food/'+type))return this.art.centered(node,'food/'+type,30,30);
        if(type.startsWith('assembly:')&&this.art.has('food/burger_ready')){
            this.art.centered(node,'objects/clean_plate',TILE*.76,TILE*.76);
            let parts=node.getChildByName('assembly-parts');
            if(!parts)parts=this.child(node,'assembly-parts',44,44);
            parts.active=true;for(const child of parts.children)child.active=false;
            const layers=burgerLayers(type.slice(9).split(','));
            layers.forEach((name,i)=>{
                const item=parts!.getChildByName(name)||this.child(parts!,name,36,24);
                item.active=true;item.setPosition(0,-3+i*4);item.setSiblingIndex(parts!.children.length-1);
                this.art.centered(item,'feedback/'+name,34,22);
            });
            return true;
        }
        const keys:Record<string,string>={board:'workstations/board',stove:'workstations/stove',
            sink:'workstations/sink',serve:'workstations/serve',returns:'workstations/returns',
            fridge:'workstations/fridge',bin:'workstations/bin',extinguisher_rack:'workstations/extinguisher_rack',extinguisher:'objects/extinguisher',
            pot:'objects/pot',clean_plate:'objects/clean_plate',dirty_plate:'objects/dirty_plate',
            raw:'ingredients/beef/raw',processing:'ingredients/beef/processing',chopped:'ingredients/beef/prepared',
            cooking:'ingredients/beef/cooking',ready:'ingredients/beef/ready',burnt:'ingredients/beef/burnt',
            plated_ready:'dishes/steak/ready',plated_burnt:'dishes/steak/burnt',fire:'vfx/fire_0'};
        if(type==='continuous_counter'){this.art.hide(node);return true;}
        if(type.startsWith('pot_')){
            if(!this.drawPot(node))return false;
            let contents=node.getChildByName('pot-contents');
            if(!contents)contents=this.child(node,'pot-contents',22,22,0,4);
            contents.active=true;
            this.art.centered(contents,'ingredients/beef/'+(type.slice(4)==='chopped'?'prepared':type.slice(4)),20,20);
            return true;
        }
        const contents=node.getChildByName('pot-contents');if(contents)contents.active=false;
        if(type==='pot')return this.drawPot(node);
        const key=keys[type];if(!key)return false;
        const size=key.startsWith('workstations/')?49:key.startsWith('ingredients/')?29:TILE*.76;
        return this.art.centered(node,key,size,size);
    }
    private drawPot(node:Node){
        const station=node.parent?.name.startsWith('station-')?node.parent.name.slice(8):'';
        const holder=node.parent?.name==='body'?node.parent.parent?.name:'';
        const facing=holder?this.state?.kitchen.chefs[holder]?.facing:'';
        const axis=station?stationView(this.state!.kitchen.map,station).device_axis:(facing==='up'||facing==='down'?'vertical':'horizontal');
        return this.art.centered(node,this.art.has('modular/pot_'+axis)?'modular/pot_'+axis:'objects/pot',TILE*(axis==='vertical'?.62:.76),TILE*.76);
    }
    private itemName(f:any){
        if(!f)return '空手';
        if(f.plate_id&&f.components?.length&&f.components.some((x:string)=>x!=='beef'))return f.stage==='burnt'?'糊菜':f.dish==='burger'?'汉堡':'待组装 · '+f.components.map((x:string)=>({bread:'面包',lettuce:'生菜',tomato:'番茄',beef:'熟牛肉'}[x])).join('+');
        if(['bread','lettuce','tomato'].includes(f.ingredient))return ({bread:'面包',lettuce:'生菜',tomato:'番茄'}[f.ingredient])+(f.stage==='chopped'?' · 切好':'');
        return STAGES[this.itemStage(f)]||f.meaning||f.stage;
    }
    private itemStage(f:any){
        if(f?.plate_id&&f.components?.some((x:string)=>x!=='beef')&&f.stage!=='burnt')return 'assembly:'+f.components.join(',');
        if(['bread','lettuce','tomato'].includes(f?.ingredient)&&!f?.plate_id)return f.ingredient+'_'+f.stage;
        if(this.useArt&&f?.stage==='raw'&&f?.ingredient==='beef'&&f.chop_remaining<(this.state?.rules?.chop_seconds||6))return 'processing';
        return f?.stage==='pot'?(f.contents?'pot_'+f.contents.stage:'pot'):f?.plate_id?'plated_'+f.stage:f?.stage;}
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
            const next:KitchenState=await this.request('/api/state');
            // A live old round may keep its backend until the player approves
            // restarting it. Do not pair new Space controls with old rules.
            if(!/^level-[123]-[1-9][0-9]*$/.test(next.kitchen?.map?.layout_version||'')||next.release?.version!=='0.5.9-alpha'){
                this.connected=false;this.clearInput();this.cover.active=true;
                this.set('coverTitle','等待厨房更新');
                this.set('coverText','新版页面已就绪，厨房服务仍在保留旧对局。\n服务更新后会自动连接，请先完成更新确认。');
                for(const id of ['main','reset','cover-connection'])this.enable(id,false);
                return;
            }
            this.enable('cover-connection',true);
            if(this.mounted&&this.mountedLayout!==next.kitchen.map.layout_version){
                for(const n of [...this.mapNodes,...Object.values(this.ground),...Object.values(this.flights)])n.destroy();
                this.devices={};this.people={};this.motions={};this.potEffects={};this.cabinetFires={};this.ground={};this.flights={};this.groundStages={};this.mounted=false;
            }
            if(next.game_id!==this.state?.game_id||!this.connected){this.selection={kind:'none',id:''};this.menuSignature='';this.foodStages={};this.readyUntil={};this.activeClock=0;
                if(this.mounted)for(const who of ['human','jeff'])this.locate(this.people[who],next.kitchen.chefs[who].position);}
            if(next.phase!=='running'||next.game_id!==this.state?.game_id)this.clearInput();
            if(next.game_id!==this.state?.game_id)this.moveSeq=Date.now()*1000;
            this.state=next;this.connected=true;this.received=this.clock;
            const frameRate=next.phase==='running'?60:15;
            if(game.frameRate!==frameRate)game.frameRate=frameRate;
            if(!sys.isNative)window.dispatchEvent(new CustomEvent('kitchen-state',{detail:{game_id:next.game_id,phase:next.phase,connection:next.connection,memory:next.memory,limits:next.limits,release:next.release,communication:next.communication}}));
            if(!this.mounted)this.mountMap();this.processEvents();this.render();
        }catch(e){game.frameRate=15;this.clearInput();this.connected=false;if(this.jeffThinking)this.jeffThinking.active=false;this.set('event',String((e as Error).message)+'，厨房会自动暂停。');this.cover.active=true;this.set('coverTitle','连接厨房');this.set('coverText','暂时连接不上厨房，请稍后重试。\n连接中断时，游戏会自动暂停。');this.writeLabel(this.buttons.main.label,'重新连接');this.buttons.reset.node.active=false;this.labels['welcome-tip'].node.active=true;
        }finally{this.polling=false;}
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
        if(path==='/api/action'||path==='/api/select'||path==='/api/interact'||path==='/api/pause'||path==='/api/end'||path==='/api/reset'||path==='/api/restart')this.clearInput();
        if((this.pending&&path!=='/api/pause')||!this.state)return;this.pending=true;this.render();
        try{await this.request(path,{game_id:this.state.game_id,request_id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2),...extra});}
        catch(e){this.set('event',(e as Error).message);}
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
        for(const name of ['supply-symbol','assembly-parts','pot-contents']){const child=n.getChildByName(name);if(child)child.active=false;}
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
        if(['fridge','bread','lettuce','tomato'].includes(id)){
            this.art.centered(n,'modular/source_'+(id==='fridge'?'beef':id),TILE*.6,TILE*.6);return;
        }
        if(id==='extinguisher')this.art.centered(n,'objects/extinguisher',TILE*.5,TILE*.68);
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
                if(!cells.has(`${x},${y}`))n.on(Node.EventType.TOUCH_END,()=>{if(!this.mapTarget(x,y)){this.cancelManualMovement();this.post('/api/select',{target:`floor_${x}_${y}`});}});
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
            if(wall)n.on(Node.EventType.TOUCH_END,()=>{if(!this.mapTarget(x,y))this.cancelManualMovement();});
        }
        this.focusMarker=this.child(this.node,'focus-cell',TILE,TILE);
        this.focusFrame(this.focusMarker.addComponent(Graphics),-TILE/2+1,-TILE/2+1,TILE-2,TILE-2);
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
            this.drawIcon(art.addComponent(Graphics),this.state!.kitchen.stations[id].counter?'continuous_counter':this.state!.kitchen.stations[id].stove?'pot':id.startsWith('bin')?'bin':/^b[0-9]/.test(id)?'board':['lettuce','tomato','bread'].includes(id)?(this.useModularArt?'source_'+id:id+'_raw'):this.useArt&&id==='extinguisher'?'extinguisher_rack':id);
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
            for(const cell of (e.cells||[]).filter((c:number[])=>c[0]!==e.cell[0]||c[1]!==e.cell[1])){
                const hit=this.make('station-extension-'+id,MAPX+(cell[0]+.5)*TILE,MAPY+(cell[1]+.5)*TILE,TILE,TILE);
                hit.on(Node.EventType.TOUCH_END,()=>{if(this.mapTarget(cell[0],cell[1]))return;this.cancelManualMovement();this.selection={kind:'station',id};this.post('/api/select',{target:id});this.render();});
            }
            if(this.useModularArt)n.getComponent(UITransform)!.setAnchorPoint(.5,.5-this.workSurfaceY(id)/TILE);
            n.on(Node.EventType.TOUCH_END,()=>{if(this.mapTarget(e.cell[0],e.cell[1]))return;this.cancelManualMovement();this.selection={kind:'station',id};this.post('/api/select',{target:id});this.render();});
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
                this.rect(rg,-35,-11,70,22,'#e4a43b');this.rect(rg,-32,-8,64,16,COLORS.paper);
                const cue=this.child(ready,'cue',70,22).addComponent(Label);this.writeLabel(cue,'熟了！');cue.fontSize=14;cue.lineHeight=18;cue.isBold=true;cue.color=color(COLORS.ink);cue.horizontalAlign=Label.HorizontalAlign.CENTER;cue.verticalAlign=Label.VerticalAlign.CENTER;
                steam.active=false;smoke.active=false;fire.active=false;ready.active=false;
                this.potEffects[id]={steam,smoke,fire,ready};
            }
            overlay.setSiblingIndex(n.children.length-1);
        }
        for(const who of ['human','jeff']){
            const n=this.chef(this.world!,who,0,0,who,this.useModularArt?.8:.65);
            const dust=this.child(n,'sprint-dust',55,28,-18,-24);dust.addComponent(Graphics);dust.active=false;dust.setSiblingIndex(0);
            this.locate(n,this.state!.kitchen.chefs[who].position);
            this.registerDepth(n,()=>{const c=this.state!.kitchen.chefs[who],e=this.state!.kitchen.map.equipment[c.target];return workingChefDepth((360-MAPY-n.position.y)/TILE-.5,e?.cell[1],c.facing,!!c.working&&!!e);});
            n.on(Node.EventType.TOUCH_END,()=>{
                const p=this.state?.kitchen.chefs[who].position;if(this.mapTarget(p[0],p[1]))return;
                if(who==='jeff'){this.set('event','靠近 Jeff，按空格给他手中的干净盘装菜。');}
            });
            // Name tag: a solid pixel plate in the identity colour, sized to the text in drawNameTag.
            const ln=this.child(n,'name',155,25,0,this.useModularArt?-12:-39);this.child(ln,'tag',40,18).addComponent(Graphics);
            const l=this.child(ln,'text',40,18).addComponent(Label);l.fontSize=13;l.lineHeight=17;l.isBold=true;l.color=color(COLORS.paper);
            l.overflow=Label.Overflow.NONE;this.labels['person-'+who]=l;
            const body=n.getChildByName('body')!,held=this.child(body,'held',25,25,22,0);held.setScale(.9,.9,1);held.addComponent(Graphics);this.people[who]=n;
            if(this.prepSample){
                const pose=this.child(this.world!,'prep-pose-'+who,68,88);pose.active=false;this.prepPoses[who]=pose;
                this.registerDepth(pose,()=>{const c=this.state!.kitchen.chefs[who],e=this.state!.kitchen.map.equipment[c.target];return depthOrder(e?.cell[1]??c.position[1],'solid')+.02;});
            }
            this.motions[who]={body,leftLeg:body.getChildByName('left-leg')!,rightLeg:body.getChildByName('right-leg')!,
                leftArm:body.getChildByName('left-arm')!,rightArm:body.getChildByName('right-arm')!,knife:body.getChildByName('right-arm')!.getChildByName('knife')!,facing:'down',step:0};
        }
        const marker=(name:string,fill:string)=>{const n=this.child(this.people.jeff,name,30,18,0,65),g=n.addComponent(Graphics);
            g.fillColor=color(COLORS.paper);g.circle(0,0,8);g.fill();for(const x of [-5,0,5])this.rect(g,x-1,-1,2,3,fill);return n;};
        this.jeffThinking=marker('jeff-thinking','#567fa4');
        const error=this.child(this.people.jeff,'jeff-api-error',24,23,0,66),eg=error.addComponent(Graphics);
        this.rect(eg,-9,-9,18,18,COLORS.hot);this.rect(eg,-2,-6,4,8,COLORS.paper);this.rect(eg,-2,4,4,3,COLORS.paper);this.jeffError=error;
        this.jeffThinking.active=false;this.jeffError.active=false;
        this.mapNodes=this.node.children.filter(n=>!previous.has(n));this.mountedLayout=map.layout_version;
        this.sortWorld();this.refreshArtCharacters();
        this.drawIcon(this.cover.getChildByName('welcome-food')!.getComponent(Graphics)!,'plated_ready');
        this.cover.setSiblingIndex(this.node.children.length-1);
        for(const id of ['pause','resume','end'])this.buttons[id].node.setSiblingIndex(this.node.children.length-1);this.mounted=true;
    }
    private characterArt(body:Node,who:string,facing:string,walking=false,working=false){
        const kind=who==='human'?'player':'jeff',chef=this.state?.kitchen.chefs[who];
        const station=this.state?.kitchen.map.equipment[chef?.target];
        const inWorld=!!body.parent&&['human','jeff'].includes(body.parent.name);
        const chopping=!!working&&inWorld&&chef?.action_kind==='chop'&&!!station;
        const sampleFrame=this.prepSample?Number(new URLSearchParams(location.search).get('prepFrame')??-1):-1;
        const knifePilot=this.knifeSample&&chopping&&who==='jeff'&&facing==='down'&&this.state!.kitchen.level===2&&chef.target==='b1';
        const pairedPilot=chopping&&this.art.has('knife/reference');
        const phase=knifePilot||pairedPilot?1:Number.isInteger(sampleFrame)&&sampleFrame>=0&&sampleFrame<4?sampleFrame:Math.floor(this.activeClock*8)%4;
        const actionKey=`characters/${kind}/${facing}/chop_${phase}`;
        const hasAction=chopping&&this.art.has(actionKey);
        const pilot=hasAction&&who==='jeff'&&facing==='down'&&this.prepSampleBoard(chef.target)&&this.art.has('prep/jeff/down/contact-body');
        const frame=walking?`walk_${Math.floor(this.activeClock*12)%8}`:'idle_0';
        // All poses share the actor's floor anchor and depth. An upper-body slice
        // is not a tool: painting it above the station puts the chef on the board.
        const key=pilot?'prep/jeff/down/contact-body':hasAction?actionKey:`characters/${kind}/${facing}/${frame}`;
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
        for(const child of body.children)if(!['held','reviewed-art'].includes(child.name))child.active=!shown;
        if(inWorld)this.pairedKnifeSample(body,who,pairedPilot,actionKey,facing);
        if(shown){
            body.setScale(1,1,1);body.angle=0;body.setPosition(0,0);
            if(inWorld&&this.useModularArt){
                body.parent!.getChildByName('contact-shadow')?.setPosition(0,0);
                body.parent!.getChildByName('name')?.setPosition(0,-12);
            }
            const held=body.getChildByName('held');
            if(held){held.setPosition(facing==='left'?-24:facing==='right'?24:0,(inWorld&&this.useModularArt?29:0)+(facing==='up'?8:-5));held.setSiblingIndex(facing==='up'?0:body.children.length-1);}
        }else{
            this.art.hide(body);
            for(const name of ['profile','back'])body.getChildByName(name)!.active=false;
            body.getChildByName('right-arm')!.getChildByName('knife')!.active=false;
        }
        return shown;
    }
    private pairedKnifeSample(body:Node,who:string,active:boolean,key:string,facing:string){
        const previous=this.pairedKnives[who];
        if(previous?.isValid)previous.active=active;
        const oldImpact=this.pairedImpacts[who];if(oldImpact?.isValid)oldImpact.active=false;
        if(!active)return;
        const player=who==='human',side=facing==='right'||facing==='left',back=facing==='up';
        if(this.pairedFacing[who]!==facing){
            for(const name of ['knife-body-mask','knife-cloth-repair']){
                const n=body.getChildByName(name);if(n){n.removeFromParent();n.destroy();}
            }
            const n=this.pairedKnives[who];if(n?.isValid){this.depthEntries=this.depthEntries.filter(e=>e.node!==n);n.destroy();}
            delete this.pairedKnives[who];this.pairedFacing[who]=facing;
        }
        const mirror=(points:number[][])=>points.map(([x,y])=>[facing==='left'?68-x:x,y]);
        const blade=back?[]:side?mirror(player?
            [[50,50],[66,40],[68,40],[68,51],[56,62],[50,59]]:
            [[49,61],[63,51],[67,51],[67,61],[53,70],[49,69]]):
            player?[[28,61],[31,61],[41,74],[33,74],[28,68]]:[[30,61],[34,63],[45,73],[36,74],[30,69]];
        const grip=mirror([back?(player?[50,60]:[52,60]):side?(player?[52,56]:[51,65]):player?[26,62]:[28,62]])[0];
        const hand=back?[]:side?mirror(player?[[45,53],[51,52],[54,55],[53,61],[48,64],[45,61]]:
            [[46,61],[51,61],[54,64],[52,69],[47,69],[45,66]]):
            player?[[20,58],[25,58],[28,61],[26,66],[21,66],[18,63]]:[[23,59],[28,59],[30,61],[29,65],[24,65],[22,62]];
        let mask=body.getChildByName('knife-body-mask');
        if(!mask){
            mask=this.child(body,'knife-body-mask',68,88);
            if(blade.length){
                const m=mask.addComponent(Mask);m.type=Mask.Type.GRAPHICS_STENCIL;m.inverted=true;
                const g=mask.getComponent(Graphics)!;g.clear();
                blade.forEach(([x,y],i)=>i?g.lineTo(x-34,82-y):g.moveTo(x-34,82-y));g.close();g.fill();
            }
            const cloth=this.child(body,'knife-cloth-repair',68,88),cg=cloth.addComponent(Graphics);
            if(!side&&!back){
                cg.fillColor=color(player?'#254c79':'#e5e0d6');
                blade.forEach(([x,y],i)=>i?cg.lineTo(x-34,82-y):cg.moveTo(x-34,82-y));cg.close();cg.fill();
            }
            cloth.setSiblingIndex(mask.getSiblingIndex());this.art.show(mask,key,68,88);
        }
        mask.active=true;body.getChildByName('knife-cloth-repair')!.active=true;this.art.hide(body);
        let root=this.pairedKnives[who];
        if(!root?.isValid){
            root=this.child(this.world!,'reference-knife-'+who,68,88);this.pairedKnives[who]=root;
            const knife=this.child(root,'knife',24,52);this.art.show(knife,'knife/reference',24,52);
            knife.setPosition(grip[0]-34,82-grip[1]);if(facing==='left')knife.setScale(-1,1,1);
            if(hand.length){
                const fingers=this.child(root,'fingers',68,88);fingers.addComponent(Mask).type=Mask.Type.GRAPHICS_STENCIL;
                const g=fingers.getComponent(Graphics)!;g.clear();
                hand.forEach(([x,y],i)=>i?g.lineTo(x-34,82-y):g.moveTo(x-34,82-y));g.close();g.fill();this.art.show(fingers,key,68,88);
            }
            this.registerDepth(root,()=>{const c=this.state!.kitchen.chefs[who];return depthOrder(this.state!.kitchen.map.equipment[c.target]?.cell[1]??c.position[1],'solid')+.02;});
        }
        root.active=true;const actor=this.people[who];root.setPosition(actor.position);root.setScale(actor.scale);
        const params=new URLSearchParams(sys.isNative?'':location.search),knife=root.getChildByName('knife')!;
        if(params.get('knifeMotion')==='off'){knife.angle=0;return;}
        // Wrist-pivot swing: no actor, hand, cabinet or food translation, no blade stretching.
        const clock=params.has('knifeTime')?Number(params.get('knifeTime'))||0:this.activeClock;
        const t=((clock/(.32)+(player?0:.27))%1+1)%1;
        let angle:number;
        if(t<.36){const q=t/.36;angle=-42-108*(q*q*(3-2*q));} // lift
        else if(t<.52){const q=(t-.36)/.16;angle=-150+132*q*q;} // quick downstroke
        else if(t<.60){const q=(t-.52)/.08;angle=-18-12*Math.sin(q*Math.PI);} // recoil
        else {const q=(t-.60)/.40;angle=-18-24*q;} // recover
        knife.angle=side?(facing==='left'?-1:1)*(40-(angle+18)*.55):back?180+(angle+18)*.65:angle;
        let impact=this.pairedImpacts[who];
        if(!impact?.isValid){
            impact=this.child(this.world!,'knife-impact-'+who,52,52);impact.addComponent(Graphics);this.pairedImpacts[who]=impact;
            this.registerDepth(impact,()=>{const c=this.state!.kitchen.chefs[who];return depthOrder(this.state!.kitchen.map.equipment[c.target]?.cell[1]??c.position[1],'solid')+.04;});
        }
        // Impact appears only during the strike, disappears before the next lift.
        impact.active=t>=.50&&t<.64;
        const g=impact.getComponent(Graphics)!;g.clear();if(!impact.active)return;
        const target=this.state!.kitchen.chefs[who].target;
        this.locate(impact,this.state!.kitchen.map.equipment[target].cell);
        const p=(t-.50)/.14;
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
    private foodNode(id:string,stage:string,click?:()=>void,airborne=false){
        const n=this.make('food-'+id,0,0,44,40,this.world||this.node);n.setScale(.9,.9,1);
        this.registerDepth(n,()=>airborne?(this.flightOrder[id]??0):depthOrder((360-MAPY-n.position.y)/TILE-.5,'item')); this.drawIcon(n.addComponent(Graphics),stage);
        const child=new Node('id');child.layer=Layers.Enum.UI_2D;n.addChild(child);child.addComponent(UITransform).setContentSize(64,19);child.setPosition(0,-23);
        const l=child.addComponent(Label);this.writeLabel(l,STAGES[stage]||id);l.fontSize=13;l.lineHeight=16;l.color=color(COLORS.ink);
        child.active=!this.useModularArt;
        if(click)n.on(Node.EventType.TOUCH_END,click);return n;
    }
    private statColor(id:string){
        const f=this.flashes[id],k=this.state!.kitchen;if(f&&f.until>this.clock)return f.fill;
        return id==='reviews'&&k.bad_reviews>k.goals.max_bad_reviews?COLORS.hot:COLORS.ink;
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
        if(e.kind==='served'){this.pop(at(serve),'+¥'+amount,COLORS.humanText);this.flash(['served','money'],COLORS.humanText);}
        else if(e.kind==='bad_service'){this.pop(at(serve),`差评 −¥${amount}`,COLORS.alert);this.flash(['reviews','money'],COLORS.alert);}
        else if(e.kind==='expired'){this.pop([312,180],`${/^(\S+?)超时/.exec(e.message)?.[1]||''} 超时 −¥${amount}`,COLORS.alert);this.flash(['reviews','money'],COLORS.alert);}
        else if(e.kind==='fire'||e.kind==='fire_spread')this.flash(['money'],COLORS.alert);
        if(e.kind&&RESULT_ANNOUNCE.has(e.kind))this.announce(e.message);
    }
    private flash(ids:string[],fill:string){for(const id of ids){this.flashes[id]={until:this.clock+1.2,fill};this.labels[id].color=color(fill);}}
    private pop(p:number[],text:string,fill:string){
        const n=this.make('result-pop',p[0],p[1],220,28),l=n.addComponent(Label);
        this.writeLabel(l,text);l.fontSize=20;l.lineHeight=24;l.isBold=true;l.horizontalAlign=Label.HorizontalAlign.CENTER;
        l.enableShadow=true;l.shadowColor=color(COLORS.ink);l.shadowOffset=new Vec2(2,-2);l.shadowBlur=0;l.color=color(fill); // hard pixel shadow
        this.pops.push({node:n,label:l,born:this.clock,y:n.position.y,fill:color(fill)});
    }
    private drawOrders(){
        const s=this.state!,k=s.kitchen,orders=k.orders.filter((o:any)=>o.status==='pending');
        this.set('served',`${k.served} / ${k.goals.target_served}`);this.set('money',`¥ ${k.money}`);this.set('reviews',`${k.bad_reviews} / ${k.goals.max_bad_reviews}`);
        for(const id of ['served','money','reviews'])this.labels[id].color=color(this.statColor(id));
        for(let i=0;i<5;i++){
            const o=orders[i],n=this.tickets[i],g=n.getComponent(Graphics)||n.addComponent(Graphics),urgent=o&&o.remaining<=15;g.clear();
            this.rect(g,-78,-34,156,67,COLORS.paper);
            g.strokeColor=color(COLORS.line);g.lineWidth=1;g.rect(-77.5,-33.5,155,66);g.stroke();
            this.rect(g,-10,26,20,8,COLORS.wood);
            this.rect(g,-66,-26,132,4,'#d6c5a2');
            if(o){this.rect(g,-66,-26,132*Math.max(0,Math.min(1,o.remaining/(o.patience||s.rules?.order_patience||90))),4,urgent?COLORS.hot:COLORS.human);}
            const signature=o?JSON.stringify(o.ingredients||['beef']):'';
            if(this.orderArt[i]!==signature){this.orderArt[i]=signature;
            const prev=n.getChildByName('ingredients');if(prev)prev.destroy();
            if(o){const row=this.child(n,'ingredients',150,16,0,-16);const ingredients=o.ingredients||['beef'];
                ingredients.forEach((name:string,j:number)=>{const item=this.child(row,'ingredient-'+j,30,14,-51+j*34,0);item.setScale(this.useArt?.5:.32,this.useArt?.5:.32,1);this.drawIcon(item.addComponent(Graphics),name==='beef'?'ready':name+'_raw');});}}
            this.set('order-id-'+i,o?`${o.id}  /  ${urgent?'快超时了':'待出餐'}`:i===0?'订单夹':'');
            this.set('order-name-'+i,o?(o.dish==='burger'?'汉堡':'香煎牛排'):i===0?(k.future_orders?'等待新订单':'订单已结清'):'');
            this.set('order-time-'+i,o?`${Math.max(0,Math.ceil(o.remaining))}s`:'');this.labels['order-time-'+i].color=color(urgent?COLORS.hot:COLORS.muted);
        }
    }
    private tagText:Record<string,string>={};
    private drawNameTag(who:string){
        const l=this.labels['person-'+who];if(this.tagText[who]===l.string)return;this.tagText[who]=l.string;
        l.updateRenderData(true);const w=Math.ceil(l.node.getComponent(UITransform)!.width)+10,h=18;
        const g=l.node.parent!.getChildByName('tag')!.getComponent(Graphics)!;g.clear();
        // 1px ink border with a 2px hard ink shadow below, like the game's buttons.
        this.rect(g,-w/2-1,-h/2-3,w+2,h+4,COLORS.ink);this.rect(g,-w/2,-h/2,w,h,who==='human'?COLORS.human:COLORS.jeffText);
    }
    private locate(n:Node,p:number[],height=0){n.setPosition(MAPX+(p[0]+.5)*TILE-640,360-MAPY-(p[1]+.5)*TILE+height);}
    private render(){
        if(!this.state||!this.mounted)return;const s=this.state,k=s.kitchen,active=s.phase==='running'&&!this.pending&&this.connected;
        const remaining=s.phase==='ended'&&k.settlement?k.settlement.remaining_seconds:Math.max(0,Math.ceil(k.round_remaining));
        this.set('clock',`${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}  ${s.phase==='running'?'营业中':s.phase==='ended'?'已结算':'休息中'}`);
        const sprint=k.chefs.human.sprint;this.set('sprint-status',!sprint?'':sprint.active_remaining>0?'冲刺中':sprint.cooldown_remaining>0?'冲刺冷却 '+Math.ceil(sprint.cooldown_remaining)+'s':'双击方向键 · 冲刺');
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
            if(s.interaction_focus===id){
                if(this.useModularArt)this.focusFrame(g,-TILE/2,this.workSurfaceY(id)-TILE/2,TILE,TILE);
                else this.focusFrame(g,-27,-27,54,54);
            }
            this.writeLabel(dev.label,st.fire?'着火了！':st.food?(this.itemName(st.food)+(st.food.stage==='cooking'?` ${Math.ceil(st.ready_in)}s`:st.food.stage==='ready'&&st.heating&&st.burn_in!==undefined?` ${Math.ceil(st.burn_in)}s 后糊`:'')):id==='fridge'&&this.useModularArt?'牛肉柜':st.name);
            const countdown=heatCountdown(st);
            let timer=dev.node.getChildByName('heat-countdown');
            if(countdown&&!timer){
                timer=this.child(dev.node,'heat-countdown',48,15,0,this.workSurfaceY(id)+TILE/2-5);
                timer.addComponent(Graphics);
                const text=this.child(timer,'time',48,15).addComponent(Label);
                text.fontSize=10;text.lineHeight=13;text.isBold=true;text.overflow=Label.Overflow.SHRINK;
            }
            if(timer){
                timer.active=!!countdown;
                if(countdown){
                    timer.setSiblingIndex(dev.node.children.length-1);
                    const tg=timer.getComponent(Graphics)!;tg.clear();
                    this.rect(tg,-24,-7.5,48,15,countdown.paused?COLORS.muted:countdown.ready?COLORS.hot:COLORS.human);
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
                else this.drawIcon(dev.node.getChildByName('equipment')!.getComponent(Graphics)!,this.useArt?'stove':st.pot_id?'pot':'stove');
                if(this.useArt){
                    let pot=dev.node.getChildByName('stove-pot');
                    if(!pot){pot=this.child(dev.node,'stove-pot',34,34,0,this.useModularArt?this.workSurfaceY(id):10);pot.setSiblingIndex(dev.node.getChildByName('equipment')!.getSiblingIndex()+1);}
                    pot.active=!!st.pot_id;if(pot.active){const axis=stationView(k.map,id).device_axis;this.art.centered(pot,this.art.has('modular/pot_'+axis)?'modular/pot_'+axis:'objects/pot',TILE*(axis==='vertical'?.6:.73),TILE*.73);}
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
                this.rect(g,-22,py,44,4,COLORS.line);this.rect(g,-22,py,44*progress,4,st.fire?COLORS.hot:COLORS.human);
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
            if(!this.ground[id]){this.ground[id]=this.foodNode(id,stage,()=>{if(this.mapTarget(item.position[0],item.position[1]))return;this.cancelManualMovement();this.selection={kind:'food',id};this.post('/api/select',{target:'item:'+id});});this.groundStages[id]=stage;}
            if(this.groundStages[id]!==stage){this.drawIcon(this.ground[id].getComponent(Graphics)!,stage);this.groundStages[id]=stage;this.writeLabel(this.ground[id].getChildByName('id')!.getComponent(Label)!,STAGES[stage]||id);}
            this.writeLabel(this.ground[id].getChildByName('id')!.getComponent(Label)!,this.itemName(item.food));
            this.locate(this.ground[id],item.position);
        }
        for(const who of ['human','jeff']){
            const c=k.chefs[who];
            this.set('person-'+who,(who==='human'?'你':'Jeff')+(c.sprint?.active_remaining>0?' »':''));this.drawNameTag(who);
            const held=this.motions[who].body.getChildByName('held')!;held.active=!!c.holding;
            if(c.holding)this.drawIcon(held.getComponent(Graphics)!,this.itemStage(c.holding));
        }
        const apiConfigured=!!s.connection?.configured&&s.phase!=='ready'&&s.phase!=='ended';
        if(this.jeffThinking)this.jeffThinking.active=this.connected&&apiConfigured&&!!s.ai.thinking&&!s.ai.error;
        if(this.jeffError)this.jeffError.active=apiConfigured&&!!s.ai.error;
        const flightIds=new Set((k.projectiles||[]).map((p:any)=>p.id));
        for(const [id,n]of Object.entries(this.flights))if(!flightIds.has(id)){n.destroy();delete this.flights[id];delete this.flightOrder[id];}
        for(const p of k.projectiles||[])if(!this.flights[p.id])this.flights[p.id]=this.foodNode(p.id,this.itemStage(p),undefined,true);
        this.enable('pause',active);
        this.enable('resume',s.phase==='paused'&&!this.pending&&this.connected);
        this.enable('end',['running','paused'].includes(s.phase)&&!this.pending&&this.connected);
        for(const id of ['pause','resume','end'])this.buttons[id].node.active=true;
        if(this.focusMarker){const cell=s.interaction_cell;this.focusMarker.active=!!cell&&!k.map.equipment[s.interaction_focus||'']&&cell[0]>=0&&cell[1]>=0&&cell[0]<k.map.width&&cell[1]<k.map.height&&!k.map.walls.some((p:number[])=>p[0]===cell[0]&&p[1]===cell[1]);if(this.focusMarker.active)this.locate(this.focusMarker,cell!);}
        const held=k.chefs.human.holding;this.set('hand','手中：'+(held?this.itemName(held):'空手'));
        if(held?.stage==='assembled')this.set('hand','缺少：'+held.missing.map((x:string)=>({beef:'熟牛肉',bread:'面包',lettuce:'生菜',tomato:'番茄'}[x])).join('+'));
        if(!this.throwReady)this.set('interaction',s.interaction?'空格 · '+s.interaction.label.split('（')[0]:(s.interaction_hint||'靠近工位或物品，再按空格'));
        // Game results keep the event line; Jeff's decisions and errors use their own status.
        const results=s.events.filter(e=>!this.isAiNote(e));
        this.set('event',results.length?results[results.length-1].message:'');
        this.set('ai-status',this.aiStatus(s));
        this.labels['ai-status'].color=color(s.ai.error||(s.limits?.reached&&s.phase==='running')?COLORS.alert:COLORS.hint);
        for(const n of [1,2,3]){this.buttons['level'+n].node.active=s.phase==='ready'||s.phase==='ended';this.enable('level'+n,!this.pending&&k.level!==n);}
        this.cover.active=s.phase!=='running';this.buttons.reset.node.active=true;
        this.enable('main',!this.pending);this.buttons.main.node.active=true;
        this.enable('reset',!this.pending&&s.phase!=='ready');
        this.writeLabel(this.buttons.main.label,s.phase==='ready'?'开始经营':s.phase==='paused'?'继续经营':'准备下一局');
        if(s.phase==='ready'&&s.connection&&!s.connection.configured)this.writeLabel(this.buttons.main.label,'先连接搭档');
        this.labels['welcome-tip'].node.active=s.phase==='ready';
        this.set('coverTitle',s.phase==='ready'?'ChefJeff':s.phase==='paused'?'歇一小会儿':k.failure_reason==='fire_spread'?'火势失控':s.aborted?'本局已结束':s.won?'今天，配合得不错！':'明天再接再厉');
        const settlement=k.settlement;
        this.set('coverText',s.phase==='ready'?`你和 AI 搭档，一起照顾这间小厨房。\n本局目标：出餐 ${k.goals.target_served} 单 · 收入 ¥${k.goals.target_money} · 差评不超过 ${k.goals.max_bad_reviews} 次`:s.phase==='paused'?'锅火和订单都按下了暂停。\n准备好了，就和 Jeff 接着做菜。':`出餐 ${k.served} 单 · 营业收入 ¥${k.money} · 差评 ${k.bad_reviews} 次`+(settlement?`\n剩余 ${settlement.remaining_seconds} 整秒 · 时间奖励 +¥${settlement.time_bonus} · 合计 ¥${settlement.total_income}`:''));
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
        for(const id of TAB_ORDER){
            const b=this.buttons[id],proxy=this.controlAccess.querySelector(`[data-control="${id}"]`) as HTMLButtonElement|null;if(!proxy)continue;
            const text=icons[id]||this.labelSources.get(b.label)||id;
            if(proxy.dataset.source!==text){proxy.dataset.source=text;proxy.textContent=text;}
            proxy.disabled=!b.enabled;proxy.hidden=!b.node.activeInHierarchy;
        }
    }
    update(dt:number){
        this.clock+=dt;if(!this.state||!this.mounted)return;const k=this.state.kitchen;
        // Result pops rise and fade over 1.4s (no rise with reduced motion); header numbers pulse.
        this.pops=this.pops.filter(p=>{
            const age=(this.clock-p.born)/1.4;if(age>=1||!p.node.isValid){p.node.destroy();return false;}
            if(!this.reduceMotion)p.node.setPosition(p.node.position.x,p.y+34*(1-(1-age)*(1-age)));
            const a=Math.round(255*(age<.6?1:1-(age-.6)/.4));
            p.label.color=new Color(p.fill.r,p.fill.g,p.fill.b,a);p.label.shadowColor=new Color(56,47,41,a);return true;
        });
        for(const [id,f] of Object.entries(this.flashes)){
            const left=f.until-this.clock,n=this.labels[id].node;
            if(left<=0){delete this.flashes[id];n.setScale(1,1,1);this.labels[id].color=color(this.statColor(id));continue;}
            const s=this.reduceMotion?1:1+.18*Math.max(0,left-.9)/.3;n.setScale(s,s,1);
        }
        const running=this.connected&&!this.hidden&&this.state.phase==='running';
        this.updateSpaceGesture();
        const animate=running&&!this.qaNoMotion;
        if(animate)this.activeClock+=dt;
        for(const who of ['human','jeff']){
            const c=k.chefs[who],p=c.position,n=this.people[who],motion=this.motions[who];
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
                const x=MAPX+(p[0]+.5)*TILE-640,y=360-MAPY-(p[1]+.5)*TILE,t=Math.min(1,dt*16);
                const oldX=n.position.x,oldY=n.position.y;
                n.setPosition(oldX+(x-oldX)*t,oldY+(y-oldY)*t);
                const dx=n.position.x-oldX,dy=n.position.y-oldY,moved=Math.hypot(dx,dy)>.08&&((c.travel_remaining||0)>0||Math.hypot(x-n.position.x,y-n.position.y)>1);
                if(moved){
                if(c.manual_moving&&who==='human'&&(this.manualDirection.x!==0||this.manualDirection.y!==0)){
                    if(Math.abs(this.manualDirection.x)>=Math.abs(this.manualDirection.y))motion.facing=this.manualDirection.x<0?'left':'right';
                    else motion.facing=this.manualDirection.y<0?'up':'down';
                }else if(Math.abs(dx)>=Math.abs(dy))motion.facing=dx<0?'left':'right';
                else motion.facing=dy>0?'up':'down';
                }
                // Authoritative orientation survives short actions between polls.
                if(!moved&&c.facing)motion.facing=c.facing;
                if(c.working&&c.facing)motion.facing=c.facing;
                const walkIntent=!!c.manual_moving||(!c.working&&(c.travel_remaining||0)>0);
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
            const t=Math.max(0,Math.min(1,(time-p.started)/(p.lands_at-p.started))),height=Math.sin(t*Math.PI)*35;
            const point=[p.from[0]+(p.to[0]-p.from[0])*t,p.from[1]+(p.to[1]-p.from[1])*t];
            this.locate(this.flights[p.id],point,height);this.flightOrder[p.id]=flightDepth(point[1],height);
        }
        this.sortWorld();
    }
}
