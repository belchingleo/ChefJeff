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
/** Local prediction of a held-key walk: straight when clear, otherwise each axis slides
 * up to the blocking edge, as the server does. Never steps deeper into the teammate. */
export function predictWalk(map:any,from:number[],dx:number,dy:number,other?:number[]){
    const n=Math.max(1,Math.ceil(Math.hypot(dx,dy)/.02)),sep=map.chef_separation??.4,sx=dx/n,sy=dy/n;
    const ok=(x:number,y:number,px:number,py:number)=>footWalkable(map,x,y)&&(!other
        ||Math.hypot(x-other[0],y-other[1])>=Math.min(sep,Math.hypot(px-other[0],py-other[1])));
    let x=from[0],y=from[1];
    for(let i=0;i<n;i++){
        if(ok(x+sx,y+sy,x,y)){x+=sx;y+=sy;continue;}
        if(sx&&ok(x+sx,y,x,y))x+=sx;
        if(sy&&ok(x,y+sy,x,y))y+=sy;
    }
    return [x,y];
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
