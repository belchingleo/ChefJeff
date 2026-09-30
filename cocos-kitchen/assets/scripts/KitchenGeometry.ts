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
/** The long edge faces the authored service side, independent of cabinet run. */
export function trashView(map:any,id:string):{axis:Axis;mirror:boolean}{
    const e=map.equipment[id],dx=e.access[0]-e.cell[0],dy=e.access[1]-e.cell[1];
    const side=e.facing==='west'||e.facing==='east'||Math.abs(dx)>Math.abs(dy);
    return {axis:side?'vertical':'horizontal',mirror:side&&dx>0};
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
    const axis=v[0]&&!v[1]?0:v[1]&&!v[0]?1:-1;
    if(!limit||axis<0)return null;
    const side=1-axis;
    for(let n=1;n<=Math.round(limit/.01);n++)for(const sign of [-1,1]){
        const shifted=[p[0],p[1]];shifted[side]+=sign*n*.01;
        const ahead=[shifted[0],shifted[1]];ahead[axis]+=v[axis]*.05;
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
    let p=from;const end=[from[0]+v[0]*distance,from[1]+v[1]*distance];
    if(clearWalkLine(map,p,end))p=move(p,end);
    else for(const axis of [0,1]){
        if(!v[axis])continue;
        const c=[p[0],p[1]];c[axis]+=v[axis]*distance;p=move(p,c);
    }
    const remaining=distance*Math.hypot(v[0],v[1])-Math.hypot(p[0]-from[0],p[1]-from[1]);
    if(map.corner_slide&&remaining>1e-9){
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
/** Display order is semantic, independent of the order ingredients reached the plate. */
export function burgerLayers(ingredients:string[]){
    const present=new Set(ingredients);
    return ['bun_bottom','beef','lettuce','tomato','bun_top'].filter(name=>present.has(name.startsWith('bun_')?'bread':name));
}
export function heatCountdown(st:any){
    if(!st.stove||!st.food||st.fire)return null;
    const ready=st.food.stage==='ready',cooking=['chopped','cooking'].includes(st.food.stage);
    if(!ready&&!cooking)return null;
    const seconds=ready?st.burn_in:st.ready_in;
    if(!Number.isFinite(seconds))return null;
    return {seconds:Math.max(0,Math.ceil(seconds)),ready,paused:!st.heating};
}
