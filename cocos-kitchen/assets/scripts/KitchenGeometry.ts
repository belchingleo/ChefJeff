/** Pure rendering contract. Simulation positions, reach and collision stay in map data. */
export type Axis = 'horizontal'|'vertical';
export const GRID_ART = {tile:52, originX:276, originY:170, unit:64, counterHeight:0, wallHeight:0, frontWallHeight:0, cabinetSpriteLift:22, northFace:44, floorRepeat:4};
export function stationView(map:any,id:string):{run_axis:Axis;device_axis:Axis} {
    const authored=map.presentation?.station_views?.[id];
    if(authored)return authored;
    // Compatibility for older maps: infer the cabinet run from neighbouring surfaces,
    // never from the chef's access side. Ambiguous isolated pieces default horizontal.
    const p=map.equipment[id]?.cell||[0,0],occupied=new Set<string>(Object.values(map.equipment).reduce<string[]>((all:string[],e:any)=>all.concat((e.cells||[e.cell]).map((c:number[])=>c.join(','))),[]));
    const h=Number(occupied.has(`${p[0]-1},${p[1]}`))+Number(occupied.has(`${p[0]+1},${p[1]}`));
    const v=Number(occupied.has(`${p[0]},${p[1]-1}`))+Number(occupied.has(`${p[0]},${p[1]+1}`));
    const axis:Axis=v>h?'vertical':'horizontal';return {run_axis:axis,device_axis:axis};
}
/** Cabinet module for a station: the trimmed front panel (counter_south) wherever its front shows, that is
 * horizontal runs and any cabinet without a wall or station right below it (the foot of a vertical run, an
 * island); the plain strip (counter_east) only inside a vertical run, where the cabinet below covers it. */
export function cabinetModule(map:any,id:string):'counter_south'|'counter_east'{
    const [x,y]=map.equipment[id].cell,below=`${x},${y+1}`;
    const covered=(map.walls||[]).some((w:number[])=>w.join(',')===below)||Object.values(map.equipment).some((e:any)=>(e.cells||[e.cell]).some((c:number[])=>c.join(',')===below));
    return stationView(map,id).run_axis==='vertical'&&covered?'counter_east':'counter_south';
}
/** The long edge faces the authored service side, independent of cabinet run. */
/** The trash art for a bin. Its lid is always on the wall side, opposite the access: a lid towards the chef is not
 * how a bin is used. The side frame draws the lid east (mirrored when the access is east), the front frame north
 * (flipped top to bottom when the access is north, as level 4's bin2). */
export function trashView(map:any,id:string):{axis:Axis;mirror:boolean;flip:boolean}{
    const e=map.equipment[id],dx=e.access[0]-e.cell[0],dy=e.access[1]-e.cell[1];
    const side=e.facing==='west'||e.facing==='east'||Math.abs(dx)>Math.abs(dy);
    return {axis:side?'vertical':'horizontal',mirror:side&&dx>0,flip:!side&&dy<0};
}
export function wallNeighbours(walls:Set<string>,x:number,y:number){
    return {north:walls.has(`${x},${y-1}`),east:walls.has(`${x+1},${y}`),south:walls.has(`${x},${y+1}`),west:walls.has(`${x-1},${y}`)};
}
/** Cell-aligned cutaway: tabletop and wall bounds share the logical grid.
 * Cabinet artwork has its own ground anchor offset; remove it at placement. */
export function surfaceOffset(){return GRID_ART.counterHeight*GRID_ART.tile/GRID_ART.unit;}
export function wallOffset(){return GRID_ART.wallHeight*GRID_ART.tile/GRID_ART.unit;}
/** Stable painter ordering; larger southward feet/footprints cover northern objects.
 * A solid sorts by its north edge: feet at or behind that edge stay behind it, while
 * feet further south in its row can only stand beside it and draw in front. */
export function depthOrder(y:number,kind:'solid'|'actor'|'item'){return y+(kind==='solid'?-.495:kind==='actor'?0:-.12);}
/** A food or tool lying on the floor at map y. Cabinets (and walls) one row up hang their front panel
 * into its tile, so it draws in front of them (above their contents too); everything from its own row
 * down stays in front of it. It stays under any chef close enough to overlap (a steak at the feet never
 * covers the legs): a chef is at least about a row north before the item can draw over them. Derived
 * from rows only, so it holds for any layout. */
export function floorItemDepth(y:number){return depthOrder(Math.round(y)-1,'solid')+.012;}
/** Station-working chefs stand outside the cabinet footprint; the cabinet must
 * not cover their face. North/back bodies retain ordinary grounded depth. */
export function workingChefDepth(y:number,row:number|undefined,facing:string,working:boolean){
    if(working&&row!==undefined&&(facing==='left'||facing==='right'))return depthOrder(row,'solid')+.015;
    return depthOrder(y,'actor');
}
/** Airborne objects keep ground depth; elevation may clear a cabinet, never move behind it. */
export function flightDepth(groundRow:number,height:number){
    return depthOrder(groundRow,'item')+(height>=GRID_ART.tile*.22?.62:0);
}
/** Mirrors the server's foot test (navigation.walkable_point) using the map's walk boxes. */
export function footWalkable(map:any,x:number,y:number){
    const c=map.walk_clearance??.2,e=1e-9;
    if(!(x>=.5+c-e&&x<=map.width-1.5-c+e&&y>=.5+c-e&&y<=map.height-1.5-c+e))return false;
    return !(map.walk_boxes||[]).some((b:number[])=>b[0]+e<x&&x<b[2]-e&&b[1]+e<y&&y<b[3]-e);
}
const EPS=1e-9;
/** Mirrors navigation.clear_walk_line: a segment may touch walk boxes, never enter one. */
export function clearWalkLine(map:any,a:number[],b:number[]){
    if(!footWalkable(map,a[0],a[1])||!footWalkable(map,b[0],b[1]))return false;
    const x0=Math.min(a[0],b[0]),x1=Math.max(a[0],b[0]),y0=Math.min(a[1],b[1]),y1=Math.max(a[1],b[1]);
    for(const [left,top,right,bottom] of (map.walk_boxes||[]) as number[][]){
        if(left+EPS>=x1||right-EPS<=x0||top+EPS>=y1||bottom-EPS<=y0)continue;
        let low=0,high=1;
        for(const [axis,lower,upper] of [[0,left,right],[1,top,bottom]]){
            const d=b[axis]-a[axis],lo=lower+EPS,hi=upper-EPS;
            if(Math.abs(d)<EPS){if(!(lo<a[axis]&&a[axis]<hi)){low=1;high=0;break;}}
            else{const p=(lo-a[axis])/d,q=(hi-a[axis])/d;low=Math.max(low,Math.min(p,q));high=Math.min(high,Math.max(p,q));}
        }
        if(low<=high)return false;
    }
    return true;
}
/** Mirrors SpatialKitchen._wall_limited: as far along the segment as the walk boxes allow. */
function wallLimited(map:any,a:number[],b:number[]){
    if(clearWalkLine(map,a,b))return b;
    let low=0,high=1;
    for(let i=0;i<16;i++){
        const mid=(low+high)/2;
        if(clearWalkLine(map,a,[a[0]+(b[0]-a[0])*mid,a[1]+(b[1]-a[1])*mid]))low=mid;else high=mid;
    }
    return [a[0]+(b[0]-a[0])*low,a[1]+(b[1]-a[1])*low];
}
/** Mirrors navigation.contact_fraction: how far a step goes before touching a chef's disc. */
function contactFraction(a:number[],b:number[],c:number[],r:number){
    const dx=b[0]-a[0],dy=b[1]-a[1],ox=a[0]-c[0],oy=a[1]-c[1],aa=dx*dx+dy*dy;
    if(aa<EPS*EPS)return 1;
    const bb=ox*dx+oy*dy,cc=ox*ox+oy*oy-r*r;
    if(cc<-EPS)return bb>=-EPS?1:0;
    if(bb>=0)return 1;
    const disc=bb*bb-aa*cc;
    if(disc<=EPS*aa)return 1;
    return Math.max(0,Math.min(1,(-bb-Math.sqrt(disc))/aa));
}
/** Sideways shift (signed cells) and its axis that lets a blocked single-direction step
 * continue: the server's corner_offset, within map.corner_slide. */
export function cornerOffset(map:any,p:number[],v:number[]):[number,number]|null{
    const limit=map.corner_slide;
    if(!limit||(!v[0]&&!v[1]))return null;
    // As the engine's corner_offset: the main axis of the stick, the side it leans to first.
    const axis=Math.abs(v[0])>=Math.abs(v[1])?0:1,side=1-axis,lean=v[side]<0?-1:1;
    for(let n=1;n<=Math.round(limit/.01);n++)for(const sign of [lean,-lean]){
        const shifted=[p[0],p[1]];shifted[side]+=sign*n*.01;
        const ahead=[shifted[0],shifted[1]];ahead[axis]+=Math.sign(v[axis])*.05;
        if(clearWalkLine(map,p,shifted)&&clearWalkLine(map,shifted,ahead))return [sign*n*.01,side];
    }
    return null;
}
/** One server tick of a held-key walk (SpatialKitchen._after_step): straight when the whole
 * line is clear, otherwise each axis in turn up to the blocking edge, then any distance left
 * slides out of a shallow notch. The teammate is a disc the step stops at (the server may also
 * slide or push; the eased server position corrects that). */
function walkTick(map:any,from:number[],v:number[],distance:number,other?:number[]){
    const sep=map.chef_separation??.4;
    const move=(a:number[],b:number[])=>{
        if(other&&Math.hypot(b[0]-a[0],b[1]-a[1])>EPS){
            const f=contactFraction(a,b,other,sep);
            if(f<1-1e-8)b=[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f];
        }
        return wallLimited(map,a,b);
    };
    let p=from;const end=[from[0]+v[0]*distance,from[1]+v[1]*distance],walled=!clearWalkLine(map,p,end);
    if(!walled)p=move(p,end);
    else for(const axis of [0,1]){
        if(!v[axis])continue;
        const c=[p[0],p[1]];c[axis]+=v[axis]*distance;p=move(p,c);
    }
    const remaining=distance*Math.hypot(v[0],v[1])-Math.hypot(p[0]-from[0],p[1]-from[1]);
    // As the engine: corner slides leave counter notches, never step aside from the other chef.
    if(map.corner_slide&&remaining>1e-9&&walled){
        const found=cornerOffset(map,p,v);
        if(found){
            const [offset,side]=found,before=p,target=[p[0],p[1]];
            target[side]+=Math.sign(offset)*Math.min(Math.abs(offset),remaining);
            p=move(p,target);
            const slid=Math.hypot(p[0]-before[0],p[1]-before[1]),left=remaining-slid;
            if(slid>1e-9&&left>1e-9){
                const ahead=[p[0]+v[0]*left,p[1]+v[1]*left];
                if(clearWalkLine(map,p,ahead))p=move(p,ahead);
            }
        }
    }
    return p;
}
/** Local prediction of a held-key walk (dx, dy in cells), computed in the server's own steps:
 * `tick` is the distance one 50 ms game tick covers at the current speed. Same geometry, same
 * step size, so diagonal slides along counters land where the server's do. */
export function predictWalk(map:any,from:number[],dx:number,dy:number,other?:number[],tick=(map.walk_speed??4.5)*.05){
    const total=Math.hypot(dx,dy);
    if(total<1e-12)return [from[0],from[1]];
    const v=[dx/total,dy/total];
    let p=[from[0],from[1]],left=total;
    while(left>1e-12){const d=Math.min(tick,left);p=walkTick(map,p,v,d,other);left-=d;}
    return p;
}
/** Cells a routed chef walks in `ahead` game seconds after a state: walk_speed, plus while that chef's own sprint
 * runs (`sprint` = the state's chefs.<who>.sprint) the engine's eased boost (spatial_kitchen.sprint_extra). */
export function routeWalkDistance(walk:number,sprint:any,ahead:number){
    if(!(ahead>0))return 0;
    const d=+sprint?.duration||0,r0=Math.max(0,+sprint?.active_remaining||0),m=+sprint?.multiplier||1;
    if(d<=0||r0<=0||m<=1)return walk*ahead;
    const wave=(r:number)=>r-d/Math.PI*Math.sin(Math.PI*r/d);
    return walk*(ahead+(m-1)*(wave(Math.min(d,r0))-wave(Math.min(d,Math.max(0,r0-ahead))))/2);
}
/** That chef's speed multiplier `ahead` game seconds after the state (1 once the sprint has run out). */
export function routeSprintFactor(sprint:any,ahead:number){
    const d=+sprint?.duration||0,left=Math.min(d,(+sprint?.active_remaining||0)-Math.max(0,ahead)),m=+sprint?.multiplier||1;
    return d>0&&left>0&&m>1?1+(m-1)*(1-Math.cos(Math.PI*left/d))/2:1;
}
/** Walks the engine ends within half a cell of their floor target (spatial_kitchen._travel_step). */
const STOPS_SHORT=new Set(['pickup','plate_ground','plate_partner']);
/** The point `along` cells down a route (clamped to it) and the route's direction there, in map cells (y down). */
export function routeAt(route:number[][],along:number):{point:number[];dir:number[]|null}{
    const n=route?.length||0;
    if(n<2)return {point:n?[route[0][0],route[0][1]]:[0,0],dir:null};
    let i=0,s=Math.max(0,along),dir:number[]|null=null;
    for(;;i++){
        const a=route[i],b=route[i+1],l=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(l>1e-9)dir=[(b[0]-a[0])/l,(b[1]-a[1])/l];
        if((s<=l&&l>1e-9)||i===n-2){const t=l>1e-9?Math.min(1,s/l):1;return {point:[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],dir};}
        s-=l;
    }
}
/** How far down a path a routed chef is drawn after walking `distance` cells along it, display only: never past where
 * the engine is expected to stop (`stop`: the path's end, half a cell short for a floor pickup, a cell short of a goal
 * the other chef stands on (spatial_kitchen._travel_step), never before `from`, where the engine has the chef now),
 * easing into that stop over its last `ease` cells since the engine may stop early; on a walk into the other chef
 * (`approach`, the "go partner" walk), stopped at the first contact (`separation` apart), as the engine stops. */
export function routeLead(route:number[][],distance:number,o:{ease?:number;kind?:string|null;other?:number[]|null;separation?:number;approach?:boolean;from?:number}={}):{along:number;stop:number}{
    let total=0,last=0;
    for(let i=1;i<(route?.length||0);i++){last=Math.hypot(route[i][0]-route[i-1][0],route[i][1]-route[i-1][1]);total+=last;}
    if(total<1e-9)return {along:0,stop:0};
    const sep=o.separation||0,end=route[route.length-1];
    let stop=total-(o.kind&&STOPS_SHORT.has(o.kind)?Math.min(.5,last):0);
    if(!o.approach&&o.other&&sep>0&&Math.hypot(end[0]-o.other[0],end[1]-o.other[1])<sep)stop=Math.min(stop,total-Math.min(1,last));
    stop=Math.max(0,o.from||0,stop);
    let d=Math.max(0,Math.min(distance,stop));
    const ease=Math.min(o.ease??0,stop-(o.from||0)),knee=stop-ease;
    if(ease>1e-9&&distance>knee)d=knee+ease*(1-Math.exp(-(distance-knee)/ease));
    if(o.approach&&o.other&&sep>0){
        const gap=(s:number)=>{const p=routeAt(route,s).point;return Math.hypot(p[0]-o.other![0],p[1]-o.other![1]);};
        let previous=gap(0);
        for(let s=.02;s<d+.02;s+=.02){
            const g=gap(Math.min(s,d));
            if(g<sep&&g<previous-1e-9){d=Math.max(0,s-.02);break;}
            previous=g;
        }
    }
    return {along:d,stop};
}
export function routeLength(route:number[][]){let t=0;for(let i=1;i<(route?.length||0);i++)t+=Math.hypot(route[i][0]-route[i-1][0],route[i][1]-route[i-1][1]);return t;}
/** The closest point of a route to p: how far along the route it lies and how far p is from it. */
export function routeProject(route:number[][],p:number[]):{along:number;offset:number}{
    const n=route?.length||0;
    if(n<2)return {along:0,offset:n?Math.hypot(p[0]-route[0][0],p[1]-route[0][1]):Infinity};
    let best={along:0,offset:Infinity},s=0;
    for(let i=1;i<n;i++){
        const a=route[i-1],b=route[i],dx=b[0]-a[0],dy=b[1]-a[1],l=Math.hypot(dx,dy);
        const t=l>1e-9?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(l*l))):0;
        const off=Math.hypot(a[0]+dx*t-p[0],a[1]+dy*t-p[1]);
        if(off<best.offset-1e-9)best={along:s+l*t,offset:off};
        s+=l;
    }
    return best;
}
/** The player's chef drawn along a route the engine walks it on (the centring slide before work, or a take the engine
 * walks it to, such as the drying rack's plate taken from the far side of the sink): from the drawn point onto the
 * route, then `step` cells on along it, corner by corner, never straight across a counter to its end. */
export function followRoute(route:number[][],from:number[],step:number):number[]{
    const n=route?.length||0;
    if(!n||!(step>0))return from;
    if(n<2){const end=route[0],gap=Math.hypot(end[0]-from[0],end[1]-from[1]),s=Math.min(gap,step);
        return gap>1e-6?[from[0]+(end[0]-from[0])*s/gap,from[1]+(end[1]-from[1])*s/gap]:from;}
    const on=routeProject(route,from),at=routeAt(route,on.along).point,off=Math.hypot(at[0]-from[0],at[1]-from[1]);
    if(off<=1e-6)return routeAt(route,on.along+step).point;
    // Off the route (the press lean, or a state taken a moment ago): back onto it first, then on along it.
    if(step<off)return [from[0]+(at[0]-from[0])*step/off,from[1]+(at[1]-from[1])*step/off];
    return routeAt(route,on.along+step-off).point;
}
/** The route's corners strictly between `from` and `to` cells along it. */
function routeCorners(route:number[][],from:number,to:number):number[][]{
    const out:number[][]=[];let s=0;
    for(let i=1;i<route.length-1;i++){
        s+=Math.hypot(route[i][0]-route[i-1][0],route[i][1]-route[i-1][1]);
        if(s>from+1e-6&&s<to-1e-6)out.push([route[i][0],route[i][1]]);
    }
    return out;
}
/** Floor at p or within 0.03 cells of it (a drawn point on a walk-box edge may sit a rounding error inside), or null. */
const NEAR=[[.01,0],[-.01,0],[0,.01],[0,-.01],[.03,0],[-.03,0],[0,.03],[0,-.03],[.02,.02],[.02,-.02],[-.02,.02],[-.02,-.02]];
function floorNear(map:any,p:number[]):number[]|null{
    if(!map?.walk_boxes||footWalkable(map,p[0],p[1]))return p;
    for(const [x,y] of NEAR)if(footWalkable(map,p[0]+x,p[1]+y))return [p[0]+x,p[1]+y];
    return null;
}
/** A clear walk through every point of `points` in turn (the first may sit a rounding error inside a walk box). */
function clearThrough(map:any,points:number[][]){
    if(!map?.walk_boxes)return true;
    let a=floorNear(map,points[0]);
    for(let i=1;i<points.length&&a;i++){if(!clearWalkLine(map,a,points[i]))return false;a=points[i];}
    return !!a;
}
/** Sideways steps round the other chef change by at most SLIDE_SLOPE cells per cell walked. */
const SLIDE_SLOPE=1.2,SIDE_KEPT=.12;
/** A point on a walk (direction `dir`) moved sideways so it stays `separation` from the other chef, as the engine
 * slides a chef round the other one: the sidestep is the least that keeps them apart, eased in and out so it never
 * changes faster than SLIDE_SLOPE per cell walked (it starts a little before they would touch). `side` (a direction in
 * map cells) is kept while he steps round, even when his walk turns, so a chef on or crossing the line never makes him
 * jump across; when not given, it is the side the point is on, or the walk's right-hand side on the line (the
 * engine's rule). A side that is not floor is not used; with neither side floor he is `blocked` (the engine holds him at
 * contact). side comes back null once no sidestep is needed. Display only. */
export function aroundChef(map:any,p:number[],dir:number[]|null,other:number[]|null|undefined,separation:number,side:number[]|null=null,shown:number[]|null=null):
        {at:number[];side:number[]|null;blocked:boolean}{
    if(!other||!(separation>0))return {at:p,side:null,blocked:false};
    const ox=p[0]-other[0],oy=p[1]-other[1],gap=Math.hypot(ox,oy);
    if(!dir){
        if(gap>=separation-1e-9)return {at:p,side:null,blocked:false};
        if(gap<=1e-9)return {at:p,side,blocked:true};
        const q=[other[0]+ox/gap*separation,other[1]+oy/gap*separation];
        return !map?.walk_boxes||footWalkable(map,q[0],q[1])?{at:q,side,blocked:false}:{at:p,side,blocked:true};
    }
    const r=[-dir[1],dir[0]],a=ox*dir[0]+oy*dir[1],b=ox*r[0]+oy*r[1];
    if(Math.abs(a)>=separation*(1+1/SLIDE_SLOPE)||gap>=separation*(1+1/SLIDE_SLOPE)+separation)return {at:p,side:null,blocked:false};
    // The side he is drawn on, once he is clearly on one (more than SIDE_KEPT off the line), so he never crosses
    // through the other chef; near the line the side kept, else the side the point is on, or the right-hand side.
    const seen=shown?(shown[0]-other[0])*r[0]+(shown[1]-other[1])*r[1]:0;
    const first=shown&&Math.abs(seen)>SIDE_KEPT?Math.sign(seen):side?(side[0]*r[0]+side[1]*r[1]>=0?1:-1):Math.abs(b)>1e-6?Math.sign(b):1;
    // The least sidestep d with (s*b+d)^2+a'^2 >= separation^2 at every a', eased: max over a' of need(a')-slope*|a-a'|.
    const step=(s:number)=>{let d=0;for(let i=0;i<=20;i++){const x=-separation+i*separation/10;
        d=Math.max(d,Math.sqrt(Math.max(0,separation*separation-x*x))-s*b-SLIDE_SLOPE*Math.abs(a-x));}return d;};
    // A side kept while they touch is never swapped for the other (that would be a jump across the other chef).
    for(const s of side?[first]:[first,-first]){
        const d=step(s);
        if(d<=1e-9)return {at:p,side:s===first&&gap<separation?[r[0]*s,r[1]*s]:null,blocked:false};
        const q=[p[0]+r[0]*s*d,p[1]+r[1]*s*d];
        if(!map?.walk_boxes||footWalkable(map,q[0],q[1]))return {at:q,side:[r[0]*s,r[1]*s],blocked:false};
    }
    // No floor to step round: kept straight out from the other chef where that is floor, else as far round as the floor
    // allows (the engine holds him at contact, see blockedContact).
    const keep=[r[0]*first,r[1]*first];
    if(gap>1e-9&&gap<separation){
        const q=[other[0]+ox/gap*separation,other[1]+oy/gap*separation];
        if(!map?.walk_boxes||footWalkable(map,q[0],q[1]))return {at:q,side:keep,blocked:true};
    }
    let low=0,high=step(first);
    for(let n=0;n<12;n++){const m=(low+high)/2;if(footWalkable(map,p[0]+keep[0]*m,p[1]+keep[1]*m))low=m;else high=m;}
    return {at:[p[0]+keep[0]*low,p[1]+keep[1]*low],side:keep,blocked:true};
}
/** Where along a path, between `from` and `to` cells, he first touches the other chef with no floor to slide round
 * them (a 1-cell corridor), or null: there the engine holds him at contact, and so is he drawn. */
function blockedContact(map:any,path:number[][],from:number,to:number,other:number[]|null|undefined,separation:number,side:number[]|null){
    if(!other||!(separation>0)||to<=from+1e-9)return null;
    const total=routeLength(path),end=Math.min(total,to+separation*2);
    let touch:number|null=null;
    for(let s=from;s<=end+1e-9;s+=.04){
        const at=routeAt(path,Math.min(s,end)),gap=Math.hypot(at.point[0]-other[0],at.point[1]-other[1]);
        if(gap>=separation){if(touch!==null)touch=null;continue;}
        if(touch===null)touch=Math.max(from,s-.04);
        if(aroundChef(map,at.point,at.dir,other,separation,side).blocked)return touch;
    }
    return null;
}
/** How far along a path the walk is clear of walk boxes: a chef pushed off his route keeps its next waypoints, and the
 * line to them may cross a counter he will slide along instead. Infinity when all of it is clear. */
function clearAlong(map:any,path:number[][]){
    if(!map?.walk_boxes)return Infinity;
    let s=0;
    for(let i=1;i<path.length;i++){
        const a=path[i-1],b=path[i],l=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(l>1e-9&&!clearThrough(map,[a,b])){
            let low=0,high=1;
            for(let n=0;n<14;n++){const t=(low+high)/2;if(clearThrough(map,[a,[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]]))low=t;else high=t;}
            return s+l*low;
        }
        s+=l;
    }
    return Infinity;
}
/** Jeff drawn between polls (display only), in game seconds and map cells. LEAD: how long past a state's arrival he is
 * walked on from it: the page passes the longest recent gap between running states plus LEAD_MARGIN, within
 * LEAD_SHORTEST..LEAD_LONGEST, so he walks until the next state is due (LEAD_MOST past the state's snapshot at most).
 * STOP_EASE: eased over the last cells into where the engine should stop. Behind the engine (a state showed a walk
 * that began before it arrived, the engine turned him round, or the player held him up) he walks the engine's own path
 * on at most CATCH_UP times his pace, eased in and out over CATCH_EASE seconds; a knock is followed at KNOCK_FOLLOW cells per second (the engine pushes
 * sprint_push cells in sprint_push_duration). ON_PATH: a drawn point this close to the new state's path is on it, and
 * the small difference closes on a critically damped spring (SETTLE per second); STILL_SETTLE: the same for a chef the
 * engine has standing. No clear walk to where the state has him (straight, or along the last path to a point in clear
 * sight of it), or one longer than SNAP_PATH, is set at once (a resync). */
export const JEFF_DRAW={LEAD_SHORTEST:.25,LEAD_LONGEST:.9,LEAD_MARGIN:.05,LEAD_MOST:1.2,STOP_EASE:.25,CATCH_UP:1.6,KNOCK_FOLLOW:6,
    ON_PATH:.12,ON_PATH_NEAR:.45,NEAR_PLAYER:.35,STILL_SETTLE:.15,SETTLE:18,SNAP_PATH:3.5,LEGS:.3,SLIDE_RATE:10,CATCH_EASE:.1};
/** base: where he is on his path (before sliding round the player); side: the side he slides round the player on. */
export type JeffWalk={serial:number;time:number;path:number[][];prefix:number;routed:boolean;knocked:boolean;sprint:any;
    kind:string|null;approach:boolean;age:number;along:number;err:number[];vel:number[];legs:number;base:number[];side:number[]|null;
    clear:number;shown:number[];slideFrom:number[];engine:number[];trail:number[][];extra:number};
/** The last `length` cells of a polyline (its end kept). */
function lastCells(points:number[][],length:number):number[][]{
    const out:number[][]=[];let left=length;
    for(let i=points.length-1;i>=0;i--){
        const p=points[i];
        if(!out.length){out.unshift(p);continue;}
        const q=out[0],l=Math.hypot(q[0]-p[0],q[1]-p[1]);
        if(l<1e-9)continue;
        if(l>=left){out.unshift([q[0]+(p[0]-q[0])*left/l,q[1]+(p[1]-q[1])*left/l]);break;}
        out.unshift(p);left-=l;
    }
    return out;
}
/** A new state: the path the drawn Jeff walks from where he is on his path to where that state has him and on along
 * its route. */
function jeffRebase(prev:JeffWalk|null,drawn:number[],k:any,now:number|null,serial:number,other?:number[]|null):{walk:JeffWalk;snapped:boolean}{
    const c=k.chefs.jeff,map=k.map,J=JEFF_DRAW,S=[c.position[0],c.position[1]];
    const knocked=!!c.knocked,routed=!knocked&&!c.working&&(c.travel_remaining||0)>0&&(c.route?.length||0)>=2;
    const R:number[][]=routed?c.route.map((p:number[])=>[p[0],p[1]]):[S];
    const base={serial,time:k.time,routed,knocked,sprint:c.sprint,kind:c.action_kind||null,
        approach:c.action_kind==='go'&&typeof c.target==='string'&&c.target.startsWith('floor_'),
        age:now===null?0:Math.max(0,now-k.time),legs:prev?prev.legs:0,base:drawn,side:prev?prev.side:null,
        shown:prev?prev.shown:drawn,slideFrom:prev?prev.slideFrom:drawn,engine:S,extra:prev?prev.extra:0,
        // Where he was drawn walking lately, so a turn round can walk back the way he came.
        trail:prev?lastCells([...prev.trail,routeAt(prev.path,0).point,...routeCorners(prev.path,0,prev.along),drawn],J.SNAP_PATH):[drawn]};
    const walk=(path:number[][],prefix:number,along:number,err:number[]=[0,0],vel:number[]=[0,0]):JeffWalk=>
        ({...base,path,prefix,along,err,vel,clear:Math.max(along,clearAlong(map,path))});
    const via=(points:number[][])=>{const lead=[drawn,...points,S],prefix=routeLength(lead);
        return prefix<=J.SNAP_PATH?{walk:walk([...lead,...R.slice(1)],prefix,0),snapped:false}:null;};
    // Already on the new path (or, standing, close to where he stands): the small difference settles. Beside the player
    // the engine slides him round them, so a wider difference counts as on the path (no walk back and forth).
    const on=routeProject(R,drawn),sep=map.chef_separation??.4;
    const near=!!other&&Math.min(Math.hypot(S[0]-other[0],S[1]-other[1]),Math.hypot(drawn[0]-other[0],drawn[1]-other[1]))<sep+J.NEAR_PLAYER;
    // A point just behind where the new route starts (its projection at the start) walks there instead (below), so a
    // state's arrival never slows his walk (beside the player the engine's slide makes that a sideways settle).
    const behindStart=routed&&!near&&on.along<=1e-6&&on.offset>1e-6;
    if(on.offset<=(routed?(near?J.ON_PATH_NEAR:J.ON_PATH):J.STILL_SETTLE)&&!knocked&&!behindStart){
        const p=routeAt(R,on.along).point;
        return {walk:walk(R,0,on.along,[drawn[0]-p[0],drawn[1]-p[1]],prev?prev.vel:[0,0]),snapped:false};
    }
    const last=prev&&prev.path.length>=2&&!knocked?prev:null;
    if(last){
        // The engine went along the last path to where this state has him: further on, or back (turned round).
        const there=routeProject(last.path,S);
        if(there.offset<=J.ON_PATH){
            const corners=there.along>=last.along-1e-6?routeCorners(last.path,last.along,there.along)
                :routeCorners(last.path,there.along,last.along).reverse();
            // Only where that way is clear: a pushed chef's route can cross a counter he slid along instead.
            const found=clearThrough(map,[drawn,...corners,S])?via(corners):null;
            if(found)return found;
        }
    }
    // Otherwise straight there when the floor between is clear, or along the last path (back first, then on) to the
    // nearest point from which the floor to the state's position is clear: the engine turned him round or off it there.
    if(clearThrough(map,[drawn,S])){const found=via([]);if(found)return found;}
    if(last){
        // Back the way he came (his trail), and on along the last path.
        const came=base.trail,total=routeLength(came),ahead=routeLength(last.path);
        for(let d=.1;d<=J.SNAP_PATH+1e-9;d+=.1){
            if(d<=total){
                const s=total-d,turn=routeAt(came,s).point,corners=routeCorners(came,s,total).reverse();
                if(clearThrough(map,[drawn,...corners,turn,S])){const found=via([...corners,turn]);if(found)return found;}
            }
            const s=last.along+d;
            if(s<=ahead){
                const turn=routeAt(last.path,s).point,corners=routeCorners(last.path,last.along,s);
                if(clearThrough(map,[drawn,...corners,turn,S])){const found=via([...corners,turn]);if(found)return found;}
            }
        }
        // Or by where the last state had him: the engine walked from there to here.
        const was=last.engine,back=routeProject(last.path,was);
        if(back.offset<=J.ON_PATH&&back.along<last.along){
            const corners=routeCorners(last.path,back.along,last.along).reverse();
            if(clearThrough(map,[drawn,...corners,was,S])){const found=via([...corners,was]);if(found)return found;}
        }
        if(clearThrough(map,[drawn,was,S])){const found=via([was]);if(found)return found;}
    }
    // Or round one corner, along the floor's axes.
    for(const corner of [[drawn[0],S[1]],[S[0],drawn[1]]])
        if(clearThrough(map,[drawn,corner,S])){const found=via([corner]);if(found)return found;}
    return {walk:{...walk(R,0,0),base:S,side:null,shown:S,slideFrom:S,trail:[S]},snapped:true};
}
/** One frame of Jeff drawn between polls: `w` from the last frame (null at first), `serial` counts applied states,
 * `now` the estimated game time (null: unknown), `dt` this frame's game seconds, `wall` its real seconds, `drawn` where
 * he is drawn now (used when `w` is null), `other` where the player's chef is drawn, `lead` see JEFF_DRAW. Returns
 * where to draw him, the walking direction while he walks (null when he stands), and whether he was set at once. */
export function jeffDraw(w:JeffWalk|null,o:{serial:number;k:any;now:number|null;dt:number;wall:number;drawn:number[];other?:number[]|null;lead:number}):
        {walk:JeffWalk;at:number[];dir:number[]|null;walking:boolean;snapped:boolean}{
    const k=o.k,map=k.map,J=JEFF_DRAW,walkSpeed=map.walk_speed||4.5,sep=map.chef_separation??.4;
    let snapped=false;
    if(!w||w.serial!==o.serial){const r=jeffRebase(w,w?w.base:o.drawn,k,o.now,o.serial,o.other);w=r.walk;snapped=r.snapped;}
    const since=o.now===null?0:Math.max(0,o.now-w.time);
    let target=w.prefix;
    if(w.routed){
        const ahead=Math.min(since,w.age+Math.max(0,o.lead),J.LEAD_MOST);
        target=routeLead(w.path,w.prefix+routeWalkDistance(walkSpeed,w.sprint,ahead),{ease:J.STOP_EASE,kind:w.kind,other:o.other,
            separation:sep,approach:w.approach,from:w.prefix}).along;
    }
    // A player he cannot slide round (a 1-cell corridor) holds him at contact, as the engine does; so does a counter
    // between a pushed chef and his next waypoint, until a state shows where the engine slid him.
    const held=blockedContact(map,w.path,w.along,target,o.other,sep,w.side);
    if(held!==null)target=Math.min(target,held);
    target=Math.min(target,w.clear);
    // Behind, he walks faster than his pace by at most (CATCH_UP-1) of it, eased in and out over CATCH_EASE s.
    const own=walkSpeed*routeSprintFactor(w.sprint,since),dt=Math.max(0,o.dt),faster=(J.CATCH_UP-1)*own;
    const needed=target-w.along>own*dt+1e-6?faster:0,ease=(J.CATCH_UP-1)*walkSpeed*dt/J.CATCH_EASE;
    w.extra=Math.max(0,Math.min(faster,w.extra+Math.max(-ease,Math.min(ease,needed-w.extra))));
    const pace=w.knocked?J.KNOCK_FOLLOW:own+w.extra;
    const was=w.along;
    // Never back along the path (the player stepping into his way only holds him); behind, he walks on to catch up.
    w.along=Math.min(Math.max(target,was),was+pace*Math.max(0,o.dt));
    const e=Math.exp(-J.SETTLE*Math.max(0,o.wall));
    for(const i of [0,1]){const j=(w.vel[i]+J.SETTLE*w.err[i])*o.wall;w.err[i]=(w.err[i]+j)*e;w.vel[i]=(w.vel[i]-j*J.SETTLE)*e;}
    // Legs walk while he moves at more than LEGS of his walking pace (smoothed over about 0.08 s), never while knocked.
    const rate=o.dt>1e-6?(w.along-was)/(walkSpeed*o.dt):w.legs>J.LEGS?1:0;
    w.legs+=(Math.min(2,rate)-w.legs)*Math.min(1,Math.max(0,o.wall)/.08);
    const here=routeAt(w.path,w.along),walking=!w.knocked&&w.legs>J.LEGS;
    // The settling difference never carries him into a counter: kept on the floor side of the path point.
    let base=[here.point[0]+w.err[0],here.point[1]+w.err[1]];
    if(map?.walk_boxes&&!footWalkable(map,base[0],base[1])&&footWalkable(map,here.point[0],here.point[1])){
        let low=0,high=1;
        for(let n=0;n<12;n++){const m=(low+high)/2;if(footWalkable(map,here.point[0]+w.err[0]*m,here.point[1]+w.err[1]*m))low=m;else high=m;}
        base=[here.point[0]+w.err[0]*low,here.point[1]+w.err[1]*low];
    }
    w.base=base;
    // Walking into the player (go partner) he stops at contact (routeLead) rather than stepping round.
    const round=w.approach?{at:w.base,side:null}:aroundChef(map,w.base,here.dir,o.other,sep,w.side,w.shown);
    // The side is kept while they touch, and chosen afresh once they are apart. The sidestep itself changes at most
    // SLIDE_RATE cells per second, so a player stepping across his way never makes him jump.
    w.side=round.side;
    const want=[round.at[0]-w.base[0],round.at[1]-w.base[1]],off=[w.shown[0]-w.slideFrom[0],w.shown[1]-w.slideFrom[1]];
    const change=[want[0]-off[0],want[1]-off[1]],size=Math.hypot(change[0],change[1]),most=J.SLIDE_RATE*Math.max(0,o.wall);
    const f=snapped||size<=most?1:most/size,at=[w.base[0]+off[0]+change[0]*f,w.base[1]+off[1]+change[1]*f];
    w.shown=at;w.slideFrom=w.base;
    return {walk:w,at,dir:walking?here.dir:null,walking,snapped};
}
/** 0..1: how far a foot at (x, y) stands right behind a cabinet whose top edge is south of
 * it. Full within 0.2 cells of the edge (every north stand point and walk limit), fading out
 * by 0.45 away or 0.35 past the cabinet's side, so walking along a counter never jumps. */
export function behindCounter(map:any,p:number[]){
    let best=0;
    for(const e of Object.values(map.equipment||{}) as any[]){
        for(const c of (e.cells||[e.cell]) as number[][]){
            const d=(c[1]-.5)-p[1];
            if(d<-.02||d>.45)continue;
            const along=d<=.2+1e-9?1:(.45-d)/.25,side=Math.max(0,Math.abs(p[0]-c[0])-.5);
            best=Math.max(best,along*Math.max(0,1-side/.35));
        }
    }
    return best;
}
/** A plate's layers from bottom to top: the dish's plating (server recipe data), keeping the layers
 * whose item is on the plate, independent of the order items reached it. Without a plating the
 * components are stacked as they are. */
export function plateLayers(plating:{layer:string;item:string}[]|undefined,components:string[]){
    const present=new Set(components);
    if(plating?.length)return plating.filter(layer=>present.has(layer.item));
    return Array.from(present).map(item=>({layer:item,item}));
}
export function heatCountdown(st:any){
    if(!st.stove||!st.food||st.fire)return null;
    const ready=st.food.stage==='ready',cooking=['chopped','cooking'].includes(st.food.stage);
    if(!ready&&!cooking)return null;
    const seconds=ready?st.burn_in:st.ready_in;
    if(!Number.isFinite(seconds))return null;
    return {seconds:Math.max(0,Math.ceil(seconds)),ready,paused:!st.heating};
}

/** Level buttons on the cover, for any number of listed levels: one row of up to three, else two
 * balanced rows, inside the band between the cover text and the main buttons (design px, y down;
 * the band stops 10 px above them, room for a pressed-in selected button).
 * Widths fill the band so long names ("… · 当前") keep the 12 px pixel font. */
export function levelButtonLayout(count:number,band={left:309,right:971,top:432,bottom:486},gap=16){
    if(count<=0)return [] as {x:number;y:number;w:number;h:number}[];
    const rows=count<=3?1:2,perRow=Math.ceil(count/rows),h=rows===1?30:24;
    const rowGap=rows===1?0:(band.bottom-band.top-rows*h)/(rows-1);
    const out:{x:number;y:number;w:number;h:number}[]=[];
    for(let i=0;i<count;i++){
        const row=Math.floor(i/perRow),inRow=Math.min(perRow,count-row*perRow),col=i-row*perRow;
        const w=(band.right-band.left-gap*(perRow-1))/perRow,span=inRow*w+gap*(inRow-1),left=(band.left+band.right)/2-span/2;
        const y=rows===1?464:band.top+h/2+row*(h+rowGap);
        out.push({x:left+col*(w+gap)+w/2,y,w,h});
    }
    return out;
}
/** Throw pose for an aim direction in map coordinates (x right, y down), any angle.
 * The knifeless chop frames already paint the throwing arm: frame 0 raised (wind-up),
 * 1 straight forward, 2 forward-down, 3 forward-up. Side views take 120-degree sectors
 * so diagonals lean the arm up or down instead of turning to the back or front. */
export function throwPose(dx:number,dy:number,phase:'windup'|'release'):{view:string;frame:number}{
    const t=((Math.atan2(dy,dx)*180/Math.PI)%360+360)%360;
    const view=t<=60||t>=300?'right':t<120?'down':t<=240?'left':'up';
    if(phase==='windup')return {view,frame:0};
    if(view==='down')return {view,frame:1};
    if(view==='up')return {view,frame:3};
    const r=((t-(view==='right'?0:180))%360+540)%360-180;
    if(Math.abs(r)<=20)return {view,frame:1};
    return {view,frame:(view==='right'?r>0:r<0)?2:3};
}
/** Held item centre in a pose's canvas pixels: just beyond the fist, along the arm. */
export function throwItemPoint(grip:number[],armDeg:number,out=4):[number,number]{
    const a=armDeg*Math.PI/180;
    return [grip[0]+Math.cos(a)*out,grip[1]-Math.sin(a)*out];
}
/** Which way a pan's handle points on a station: toward the operation side, where the chef stands.
 * Uses the station's facing, else the access cell relative to the station cell. */
export function panHandleSide(station:any):string{
    if(!station)return 'east';
    if(['north','south','east','west'].includes(station.facing))return station.facing;
    const cell=station.cell||[0,0],access=station.access||cell,dx=access[0]-cell[0],dy=access[1]-cell[1];
    if(Math.abs(dx)>=Math.abs(dy)&&dx!==0)return dx>0?'east':'west';
    return dy<0?'north':'south';
}
/** The diagonal a throw aims along, when within 22.5 degrees of one: 'down_right', 'down_left',
 * 'up_left' or 'up_right' (map y points down); '' otherwise. Selects painted diagonal throw bodies. */
export function throwDiagonal(dx:number,dy:number):string{
    if(!dx&&!dy)return '';
    const t=((Math.atan2(dy,dx)*180/Math.PI)%360+360)%360;
    const names=['down_right','down_left','up_left','up_right'];
    for(let i=0;i<4;i++){const centre=45+90*i,off=Math.abs(((t-centre)%360+540)%360-180);if(off<22.5)return names[i];}
    return '';
}
/** The facing a held direction turns the chef to: at once, even against a counter, as in Overcooked 2. */
export function steeredFacing(x:number,y:number):string|null{
    if(x===0&&y===0)return null;
    return Math.abs(x)>=Math.abs(y)?(x<0?'left':'right'):(y<0?'up':'down');
}
/** The facing a chef keeps while standing still. The engine's facing wins (it turns a chef for work between
 * polls), except for the player's own steered chef: as in Overcooked, the local chef keeps the page's facing,
 * since the engine's arrives a round trip after the key and would flash the old direction on release. */
export function restingFacing(drawn:string,engine:string|undefined,steered:boolean):string{
    return steered||!engine?drawn:engine;
}
/** Whether a Space press waits: as in Overcooked 2 (ClientPlayerControlsImpl_Default, m_pickupDelay 0.5 s),
 * only a pick-up within 0.5 s of the last one does. With something in hand the press puts it down at once. */
export function pickupWaits(holding:boolean,sincePickup:number):boolean{
    return !holding&&sincePickup<.5;
}
/** Real seconds until the player's take or put lands, from the state a Space reply carries (null when nothing
 * is under way or it is station work). The page asks for the state then instead of waiting for its next poll. */
export function handsLandIn(state:any):number|null{
    const h=state?.kitchen?.chefs?.human,speed=state?.speed||1;
    if(!h?.job_id||h.working)return null;
    const left=((h.travel_remaining||0)+(h.work_remaining||0))/speed;
    return left>0&&left<1?left+.02:null;
}
/** The facing a chef is drawn with this frame.
 *
 * The player's own chef (`own`: the page walks it) turns only with a held direction, as in Overcooked 2,
 * whose chef turns only with the stick (ClientPlayerControlsImpl_Default.Update_Rotation reads the input
 * axes alone). Nothing else that moves the drawn chef turns it: the lean on a Space or E press (its swing
 * back points away from the station), the centring slide before a put or a chop, a dash knock-back, a push
 * from Jeff or a position correction. Only a real walk the engine makes for it (`travelling`, not a slide)
 * turns it with the engine's facing.
 *
 * Any other chef turns along the way it is drawn walking (`walked`, from the engine's positions), except on a
 * centring slide, and otherwise rests on the engine's facing. Working at a station, every chef faces the
 * station as the engine says. */
export function drawnFacing(o:{drawn:string; engine?:string; own:boolean; steer:string|null; steered:boolean;
        walked:number[]|null; slide:boolean; travelling:boolean; working:boolean}):string{
    if(o.working&&o.engine)return o.engine;
    if(o.steer)return o.steer;
    if(o.own){
        if(o.travelling&&!o.slide&&o.engine)return o.engine;
        return restingFacing(o.drawn,o.engine,o.steered);
    }
    if(o.walked&&!o.slide){
        const [dx,dy]=o.walked;
        return Math.abs(dx)>=Math.abs(dy)?(dx<0?'left':'right'):(dy>0?'up':'down');
    }
    return restingFacing(o.drawn,o.engine,false);
}
/** The chef's own cell (engine anchor()): the nearest floor cell, ties to the lower row, then column. */
export function anchorCell(map:any,pos:number[]):number[]|null{
    const key=(x:number,y:number)=>x+','+y,blocked=new Set<string>((map.walls||[]).map((w:number[])=>key(w[0],w[1])));
    for(const e of Object.values(map.equipment||{}) as any[])for(const c of (e.cells||[e.cell]))blocked.add(key(c[0],c[1]));
    let anchor:number[]|null=null,best=Infinity;
    for(let y=0;y<map.height;y++)for(let x=0;x<map.width;x++){
        if(blocked.has(key(x,y)))continue;
        const d=Math.hypot(x-pos[0],y-pos[1]);
        if(d<best-1e-12){best=d;anchor=[x,y];}
    }
    return anchor;
}
/** Shortest distance from a point to a segment (a throw's path; the engine catches along it). */
export function segmentDistance(p:number[],a:number[],b:number[]){
    const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy,t=l<1e-12?0:Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l));
    return Math.hypot(p[0]-a[0]-dx*t,p[1]-a[1]-dy*t);
}
/** What Space acts on, as the engine's facing_candidates ranks it (Overcooked 2's ScanForObject): the picked
 * station and the first loose item on the aimed tile and on the feet tile, nearest first to a point half a
 * cell ahead (the station's at hand height when aiming sideways); ties keep station, aimed tile, feet.
 * Returns a station id, 'item:<food id>' or null. */
/** spatial_kitchen.ITEM_REACH: how far a loose item may lie (to its centre) and still be picked. */
export const ITEM_REACH=1.2;
export function spaceTarget(map:any,pos:number[],aim:number[],ground:any[]):string|null{
    const length=Math.hypot(aim[0],aim[1]),anchor=anchorCell(map,pos);
    if(!length||!anchor)return null;
    const ax=aim[0]/length,ay=aim[1]/length,near=(d:number)=>Math.round(d*1e6)/1e6,ranked:[number,number,string][]=[];
    const station=selectableStations(map,pos,aim)[0];
    if(station){
        const e=map.equipment[station],cells:number[][]=e.cells||[e.cell];
        const cell=cells.reduce((a,b)=>Math.hypot(b[0]-pos[0],b[1]-pos[1])<Math.hypot(a[0]-pos[0],a[1]-pos[1])?b:a);
        ranked.push([near(Math.hypot(pos[0]+ax*.5-cell[0],pos[1]+ay*.5-.35*Math.abs(ax)-cell[1])),0,station]);
    }
    const front=[anchor[0]+(Math.abs(ax)>=.38?Math.sign(ax):0),anchor[1]+(Math.abs(ay)>=.38?Math.sign(ay):0)];
    // As the engine (spatial_kitchen ITEM_REACH, Overcooked 2's 180-degree interact arc): a loose item in the
    // half-disc ahead within reach, or on the chef's own tile; the aimed tile ranks first on a tie, then the feet.
    for(const item of ground){
        if(!item.position)continue;
        const at=(t:number[])=>item.location===`floor_${t[0]}_${t[1]}`,feet=at(anchor);
        const dx=item.position[0]-pos[0],dy=item.position[1]-pos[1];
        if(!feet&&(Math.hypot(dx,dy)>ITEM_REACH||dx*ax+dy*ay<-1e-9))continue;
        ranked.push([near(Math.hypot(pos[0]+ax*.5-item.position[0],pos[1]+ay*.5-item.position[1])),at(front)?1:feet?2:3,'item:'+item.food.id]);
    }
    ranked.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    return ranked.length?ranked[0][2]:null;
}
/** Space's and E's station, picked as the engine does (spatial_kitchen.selectable_stations; Overcooked 2's
 * GetFacingGridOccupant with grid selection): of the stations in the four cells beside the chef's own floor
 * cell (aiming sideways, the cell under the hands), never a diagonal, the one whose offset best matches the aim; up to 135 degrees off still counts when
 * nothing better is there (the counter at the chef's side, with open floor ahead), the cell behind never.
 * Ties go right, left, up, down. An authored corner counter counts from its access cell when ahead. */
export function selectableStations(map:any,pos:number[],aim:number[]):string[]{
    const MIN_DOT=Math.cos(135*Math.PI/180),ORDER=[[1,0],[-1,0],[0,-1],[0,1]];
    const length=Math.hypot(aim[0],aim[1]);if(!length)return [];
    const ax=aim[0]/length,ay=aim[1]/length,anchor=anchorCell(map,pos);
    if(!anchor)return [];
    // Directions from the cell the hands are over (raised when aiming sideways, as the knife is drawn).
    const [cx,cy]=anchor,[hx,hy]=anchorCell(map,[pos[0],pos[1]-.35*Math.abs(ax)])||anchor,round=(v:number)=>Math.round(v*1e6)/1e6;
    const ranked=new Map<string,[number,number]>();
    for(const [id,e] of Object.entries(map.equipment||{}) as [string,any][]){
        let rank:[number,number]|null=null;
        if(e.reach==='corner'){
            if(e.access?.[0]!==cx||e.access?.[1]!==cy)continue;
            const ox=e.cell[0]-cx,oy=e.cell[1]-cy,dot=(ax*ox+ay*oy)/Math.hypot(ox,oy);
            if(dot<=1e-6)continue;
            rank=[-round(dot),ORDER.length];
        }else for(const c of (e.cells||[e.cell]) as number[][]){
            const ox=c[0]-hx,oy=c[1]-hy,order=ORDER.findIndex(([x,y])=>x===ox&&y===oy);
            if(order<0)continue;
            const dot=ax*ox+ay*oy;
            if(dot<MIN_DOT-1e-9)continue;
            const here:[number,number]=[-round(dot),order];
            if(!rank||here[0]<rank[0]||(here[0]===rank[0]&&here[1]<rank[1]))rank=here;
        }
        if(rank)ranked.set(id,rank);
    }
    return Array.from(ranked.entries()).sort((a,b)=>a[1][0]-b[1][0]||a[1][1]-b[1][1]||(a[0]<b[0]?-1:a[0]>b[0]?1:0)).map(([id])=>id);
}
