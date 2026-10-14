import { JsonAsset, Layers, Node, Rect, Size, resources, Sprite, SpriteFrame, Texture2D, UITransform } from 'cc';

type Frame = { rect:number[]; anchor?:number[]; canvasSize?:number[]; groundAnchor?:number[]; workSurfaceAnchor?:number[]; alpha_bbox?:number[]; [field:string]:unknown };
type Manifest = { frames:Record<string,Frame> };

/** Reviewed, local sprites only. Rendering never changes kitchen observations or rules. */
export class LevelOneArt {
    private frames:Record<string,SpriteFrame>={};
    private definitions:Record<string,Frame>={};
    private slices:Record<string,SpriteFrame>={};
    ready=false;
    modular=false;
    private async loadAtlas(path:string,prefix='') {
        const [manifest,texture]=await Promise.all([
            new Promise<JsonAsset>((resolve,reject)=>resources.load(path+'/manifest',JsonAsset,(e,a)=>e?reject(e):resolve(a))),
            new Promise<Texture2D>((resolve,reject)=>resources.load(path+'/atlas/texture',Texture2D,(e,a)=>e?reject(e):resolve(a)))
        ]);
        texture.setFilters(Texture2D.Filter.NEAREST,Texture2D.Filter.NEAREST);
        for(const [key,value] of Object.entries((manifest.json as Manifest).frames)){
            const [x,y,w,h]=value.rect;
            if(w<=0||h<=0||x<0||y<0||x+w>texture.width||y+h>texture.height)throw new Error('Invalid art frame '+key);
        }
        // Download concurrently, but apply in source order: newer atlases override
        // older frames regardless of which network response finishes first.
        return ()=>{
        for(const [key,value] of Object.entries((manifest.json as Manifest).frames)){
            const [x,y,w,h]=value.rect;
            const frame=new SpriteFrame();frame.texture=texture;frame.rect=new Rect(x,y,w,h);frame.originalSize=new Size(w,h);
            this.frames[prefix+key]=frame;this.definitions[prefix+key]=value;
        }
        };
    }
    async load():Promise<void>{
        try {
            const atlases:[string,string,boolean][]=[
                ['art/level1','',true],['art/level1-modular','modular/',false],
                ['art/kitchen-modules-v2','modular/',false],['art/serving-side-v1','modular/',false],
                ['art/burger-food','food/',false],['art/grid-foundation-v1','',true],
                ['art/action-feedback-v1','',true],['art/chefs-v2','',false],
                ['art/knife-v1','',true],['art/knife-arc-v1','',false],
                ['art/trash-directions-v1','',true],['art/ingredient-pack-v1','',false],
            ];
            if(typeof location!=='undefined'&&new URLSearchParams(location.search).get('prepSample')==='1')
                atlases.push(['art/prep-pose-v3','',true]);
            const apply=await Promise.all(atlases.map(async([path,prefix])=>{
                try{return await this.loadAtlas(path,prefix);}
                catch(error){console.warn('Kitchen art unavailable: '+path+'; retaining readable fallback.',error);return null;}
            }));
            for(const install of apply)install?.();
            this.modular=!!apply[1];
            this.ready=atlases.every(([, ,required],i)=>!required||!!apply[i]);
        } catch(error) { console.warn('ChefJeff level 1 art unavailable; retaining readable fallback.',error); }
    }
    has(key:string){return !!this.frames[key];}
    /** Manifest entry of a frame (grip, pivot, edge points), or undefined. */
    meta(key:string):any{return this.definitions[key];}
    /** Let the browser HUD crop the same loaded atlas used by the kitchen. */
    spriteInfo(key:string){
        const frame=this.frames[key],definition=this.definitions[key],texture=frame?.texture,url=texture?.image?.nativeUrl;
        if(!definition||!texture||!url)return null;
        const [x,y,width,height]=definition.rect;
        return {url,x,y,width,height,atlasWidth:texture.width,atlasHeight:texture.height,alphaBBox:definition.alpha_bbox||[0,0,width,height]};
    }
    /** Natural pixel proportions, one 64 px art unit per gameplay cell. */
    tile(parent:Node,key:string,cellSize:number,x=0,y=0):boolean {
        const name='modular/'+key,definition=this.definitions[name];
        if(!definition)return false;
        const [, ,w,h]=definition.rect;
        return this.show(parent,name,w*cellSize/64,h*cellSize/64,x,y);
    }
    /** Align the working surface, independently of transparent canvas and floor anchor. */
    surface(parent:Node,key:string,cellSize:number,x:number,y:number,depth=1):boolean {
        const name='modular/'+key,d=this.definitions[name];
        if(!d?.workSurfaceAnchor||!d.groundAnchor)return false;
        const scale=cellSize/64,[,,w,h]=d.rect;
        return this.show(parent,name,w*scale,h*scale*depth,
            x-(d.workSurfaceAnchor[0]-d.groundAnchor[0])*scale,
            y-(d.groundAnchor[1]-d.workSurfaceAnchor[1])*scale*depth);
    }
    /** Decorations use a centre anchor independent of floor-based sprite anchors. */
    centered(parent:Node,key:string,w:number,h:number):boolean {
        const d=this.definitions[key];if(!d)return false;
        const [,,cw,ch]=d.rect,[left,top,right,bottom]=d.alpha_bbox||[0,0,cw,ch];
        const scale=Math.min(w/(right-left),h/(bottom-top));
        if(!this.show(parent,key,cw*scale,ch*scale,(cw/2-(left+right)/2)*scale,((top+bottom)/2-ch/2)*scale))return false;
        parent.getChildByName('reviewed-art')!.getComponent(UITransform)!.setAnchorPoint(.5,.5);
        return true;
    }
    hide(parent:Node){const n=parent.getChildByName('reviewed-art');if(n)n.active=false;}
    /** Repeatable material crop, retaining the source's pixel density. */
    region(parent:Node,key:string,x:number,y:number,w:number,h:number,displayW:number,displayH:number){
        const base=this.frames[key];if(!base)return false;
        const cache=[key,x,y,w,h].join(':');
        if(!this.slices[cache]){const f=new SpriteFrame();f.texture=base.texture;
            f.rect=new Rect(base.rect.x+x,base.rect.y+y,w,h);f.originalSize=new Size(w,h);this.slices[cache]=f;}
        this.show(parent,key,displayW,displayH);
        const n=parent.getChildByName('reviewed-art')!;n.getComponent(Sprite)!.spriteFrame=this.slices[cache];
        n.getComponent(UITransform)!.setAnchorPoint(.5,.5);return true;
    }
    show(parent:Node,key:string,w:number,h:number,x=0,y=0):boolean {
        const frame=this.frames[key];
        if(!frame){this.hide(parent);return false;}
        let n=parent.getChildByName('reviewed-art');
        if(!n){n=new Node('reviewed-art');n.layer=Layers.Enum.UI_2D;parent.addChild(n);n.addComponent(UITransform);n.addComponent(Sprite);}
        n.active=true;n.setPosition(x,y);
        const transform=n.getComponent(UITransform)!;
        const anchor=this.definitions[key].anchor||[.5,.5];transform.setAnchorPoint(anchor[0],anchor[1]);
        const sprite=n.getComponent(Sprite)!;sprite.sizeMode=Sprite.SizeMode.CUSTOM;sprite.trim=false;
        if(sprite.spriteFrame!==frame)sprite.spriteFrame=frame;
        transform.setContentSize(w,h);return true;
    }
}
