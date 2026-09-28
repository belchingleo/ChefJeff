"""Deterministic kitchen rules. No AI policy lives in this module."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMES = {"human": "你", "jeff": "Jeff"}
STATES = {"raw": "生肉", "chopped": "切好", "cooking": "加热中", "ready": "熟了", "burnt": "糊了", "extinguisher": "灭火器", "clean_plate": "干净餐盘", "dirty_plate": "脏餐盘", "pot": "锅", "assembled": "待组装菜品"}


def load_config(path=None):
    c = json.loads(Path(path or ROOT / "config.json").read_text())
    for key, value in c.items():
        if key != "model" and (not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
            raise ValueError(f"配置 {key} 必须是正数")
    for key in ("boards", "pots", "order_count", "target_served", "max_bad_reviews", "plate_count", "ai_max_calls"):
        if key not in c:
            continue
        if int(c[key]) != c[key]:
            raise ValueError(f"配置 {key} 必须是整数")
    if c["boards"] > 8 or c["pots"] > 8:
        raise ValueError("文字原型最多支持 8 块案板和 8 口锅")
    if c.get('ai_max_calls',200)>2000:
        raise ValueError('ai_max_calls 不能超过 2000')
    return c


@dataclass
class Food:
    id: str
    stage: str = "raw"
    chopped: float = 0
    heated: float = 0
    plate_id: str | None = None
    washed: float = 0
    contents: Food | None = None
    ingredient: str = "beef"
    components: tuple = ()


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    kind: str
    target: str = ""
    # Bind every displayed/requested action to its actual object and held item.
    expected: tuple = ()


@dataclass
class Job:
    id: int
    action: Action
    travel: float
    work: float
    working: bool = False


@dataclass
class Chef:
    location: str
    hand: Food | None = None
    job: Job | None = None


@dataclass
class Station:
    name: str
    area: str
    food: Food | None = None
    lock: str | None = None
    fire: bool = False
    heating: bool = False
    pot_id: str | None = None
    fire_elapsed: float = 0.0
    scorched: bool = False


@dataclass
class GroundItem:
    food: Food
    location: str
    lock: str | None = None
    offset: tuple = (0.,0.)


TAKE_KINDS = {"fetch", "take_board", "take_tool", "pickup", "take_plate", "take_return", "take_sink", "take_counter", "lift_pot"}


class Kitchen:
    def __init__(self, config=None):
        self.c = config or load_config()
        self.time = 0.0
        self.revision = 0
        self.serial = 0
        self.job_serial = 0
        self.money = 0
        self.time_bonus = 0
        self.reward_seconds = 0
        self.served = 0
        self.bad_reviews = 0
        self.fires = 0
        self.burns = 0
        self.ended = False
        self.aborted = False
        self.failure_reason = None
        self.events = []
        self.ground = {}
        self.pickup_numbers = {}
        self.swap_slots = {}
        self.plate_count = int(self.c.get('plate_count', 2))
        self.wash_seconds = self.c.get('wash_seconds', 4)
        self.dining_seconds = self.c.get('dining_seconds', 8)
        if not 1 <= self.plate_count <= 3:
            raise ValueError('当前练习关提供三个单格柜台，餐盘数量需为1至3')
        self.counters = ['plates', 'counter2', 'counter3']
        self.dining = []
        self.stations = {"fridge": Station("冰箱", "处理区"),
                         "serve": Station("出餐口", "烹饪区"),
                         "bin": Station("垃圾桶", "处理区"),
                         "extinguisher": Station("灭火器架", "烹饪区", Food('E1', 'extinguisher'))}
        self.stations.update({
            'returns': Station('脏盘回收', '烹饪区'),
            'sink': Station('水槽', '处理区'),
        })
        for i, key in enumerate(self.counters, 1):
            self.stations[key] = Station(f'柜台 {i}', '处理区' if key == 'counter3' else '烹饪区',
                                         Food(f'D{i}', 'clean_plate') if i <= self.plate_count else None)
        self.boards = [f"b{i+1}" for i in range(self.c["boards"])]
        self.pots = [f"p{i+1}" for i in range(self.c["pots"])]
        for key in self.boards:
            self.stations[key] = Station(f"案板 {key[1:]}", "处理区")
        for key in self.pots:
            self.stations[key] = Station(f"灶台 {key[1:]}", "烹饪区", pot_id=f'P{key[1:]}')
        self.chefs = {"human": Chef("fridge"), "jeff": Chef(self.pots[0])}
        self.orders = [{"id": f"O{i+1}", "dish": "牛排", "arrival": i*self.c["order_interval"],
                        "deadline": i*self.c["order_interval"]+self.c["order_patience"],
                        "status": "future"} for i in range(self.c["order_count"])]
        self.pot_count=int(self.c.get('pot_count',len(self.pots)))
        self.ingredients={'fridge':'beef'}
        if self.c.get('level') in (2,3):
            self.ingredients.update(lettuce='lettuce',tomato='tomato',bread='bread')
            for key in ('lettuce','tomato','bread'):self.stations[key]=Station({'lettuce':'生菜箱','tomato':'番茄箱','bread':'面包箱'}[key],'处理区')
            menu=['burger']*3 if self.c['level']==2 else ['steak']*2+['burger']*3
            random.Random(self.c['order_seed']).shuffle(menu)
            self.orders=[{'id':f'O{i+1}','dish':dish,'arrival':i*self.c['order_interval'],
                         'patience':self.c['order_patience'] if self.c['level']==2 else (100 if dish=='steak' else 150),
                         'deadline':i*self.c['order_interval']+(self.c['order_patience'] if self.c['level']==2 else (100 if dish=='steak' else 150)),
                         'status':'future','ingredients':['beef'] if dish=='steak' else ['bread','lettuce','tomato','beef']}
                         for i,dish in enumerate(menu)]
        self._arrivals()

    def emit(self, message, **extra):
        self.revision += 1
        self.events.append({"t": round(self.time, 3), "message": message, **extra})

    def _arrivals(self):
        for o in self.orders:
            if o["status"] == "future" and o["arrival"] <= self.time + 1e-8:
                o["status"] = "pending"
                self.emit(f"新订单 {o['id']}：{o['dish']}，截止 {o['deadline']:.0f}s", kind="order")

    def travel_time(self, chef, target):
        if chef.location == target:
            return 0
        same = self.stations[chef.location].area == self.stations[target].area
        return self.c["same_area_walk"] if same else self.c["cross_area_walk"]

    def place(self, key):
        return self.stations[key]

    def _travel(self, who, job, seconds):
        """Optional spatial animation hook; base kitchen uses abstract travel."""
        pass

    def _travel_step(self,who,job,seconds):
        used=min(job.travel,seconds);job.travel-=used
        self._travel(who,job,used)
        return used

    def _after_step(self, seconds):
        pass

    def signature(self, who, target=""):
        hand = self.chefs[who].hand
        s = self.stations.get(target)
        target_item = s.food if s else None
        target_token = target_item.id if target_item else None
        if target_item and target_item.components:target_token += ':'+','.join(target_item.components)
        if target_item and target_item.stage == 'pot':
            target_token += ':'+(target_item.contents.id if target_item.contents else 'empty')
        return (hand.id if hand else None, target_token,
                bool(s and s.fire), hand.contents.id if hand and hand.contents else (','.join(hand.components) if hand and hand.components else None), s.pot_id if s else None)

    def can_share_work(self, who, kind, target):
        # Spatial kitchens supply the actual, distinct service positions.
        return False

    def work_participants(self, target, kind):
        return [who for who,a in self.chefs.items() if a.job and a.job.working
                and a.job.action.target==target and a.job.action.kind==kind]

    def actions(self, who):
        if self.ended:
            return []
        a = self.chefs[who]
        out = []
        def add(key, label, kind, target=""):
            out.append(Action(key, label, kind, target, () if kind == "go" else self.signature(who, target)))
        if a.job:
            out.append(Action("continue", "继续当前动作", "continue", expected=(a.job.id,)))
            out.append(Action("stop", "中断当前动作（切配进度保留；锅继续加热）", "stop", expected=(a.job.id,)))
        else:
            add("wait", "暂时等待", "wait")
        add("fetch", "到冰箱取一份生肉（手中物品自动放到地上）", "fetch", "fridge")
        for source,ingredient in self.ingredients.items():
            if source!='fridge':add('fetch '+source,'取一份'+{'lettuce':'生菜','tomato':'番茄','bread':'面包'}[ingredient]+'（自动换手）','fetch',source)
        if a.hand:
            if a.hand.plate_id and self.dish(a.hand):
                add("serve", "拿已装盘的菜出餐（糊菜或无订单会被差评）", "serve", "serve")
            if a.hand.stage not in ('extinguisher', 'clean_plate', 'dirty_plate', 'pot'):
                add("discard", "去垃圾桶丢弃手中食物（损耗 2 元，无法捡回）", "discard", "bin")
            if a.hand.stage == 'pot' and a.hand.contents:
                add('discard', '倒掉手中锅里的食物（损耗2元，保留空锅）', 'empty_pot', 'bin')
            out.append(Action("drop", f"将手中物品放到{self.place(a.location).name}旁的地上（可捡回，不扣钱）",
                              "drop", a.location, (a.hand.id, a.location)))
        for key in self.counters:
            s = self.stations[key]
            if s.lock not in (None, who):
                continue
            if s.food:
                if self.can_swap_pots(a.hand,s.food):
                    add('swap pot '+key,'与'+s.name+'的锅交换（各自保留锅内食物）','swap_pot',key)
                if self.c.get('level') in (2,3) and a.hand:
                    if self.can_add(s.food,a.hand) or self.can_add(a.hand,s.food):
                        add('assemble '+key,'在'+s.name+'向盘中加入食材','assemble',key)
                if self.c.get('level') in (2,3) and self.can_merge_plates(a.hand,s.food):
                    add('merge '+key,'把'+s.name+'盘中食物合入手中盘（空盘留在原位）','merge_plates',key)
                if self.can_load_pot(a.hand,s.food):
                    add('load '+key,'把切好的牛肉放入'+s.name+'的空锅（离灶不加热）','load_counter',key)
                kind = 'take_plate' if s.food.stage == 'clean_plate' else 'take_counter'
                add(f'take {key}', f'从{s.name}拿起{self.food_name(s.food)}（自动换手）', kind, key)
                if a.hand and a.hand.stage == 'pot' and self.can_add(s.food,a.hand.contents):
                    add(f'plate {key}', f'把手中锅里的菜盛到{s.name}的盘里（空锅留在手中）', 'plate_counter', key)
                if s.food.stage == 'pot' and a.hand and self.can_add(a.hand,s.food.contents):
                    add(f'plate {key}', f'用手中的盘盛出{s.name}锅里的菜', 'plate_from_counter', key)
            elif a.hand:
                add(f'put {key}', f'把手中物品放到{s.name}（每格一件）', 'put_counter', key)
        for key, kind in (('returns', 'take_return'), ('sink', 'take_sink')):
            s = self.stations[key]
            if s.lock not in (None, who):
                if key=='sink' and not a.hand and s.food and s.food.stage=='dirty_plate' and self.can_share_work(who,'wash',key):
                    add('wash','一起洗碗（共享进度）','wash',key)
                continue
            if s.food:
                add(f'take {key}', f'从{s.name}拿起{self.food_name(s.food)}（自动换手）', kind, key)
            if key == 'sink':
                if not s.food and a.hand and a.hand.stage == 'dirty_plate':
                    add('put sink', '把脏餐盘放入水槽', 'put_sink', key)
                if s.food and s.food.stage == 'dirty_plate' and not a.hand:
                    add('wash', f'洗碗（剩 {max(0, self.wash_seconds-s.food.washed):.1f}s；可中断续洗）', 'wash', key)
        rack = self.stations['extinguisher']
        if rack.lock in (None, who):
            if rack.food:
                add('take extinguisher', '去灭火器架拿灭火器（占用手持位）', 'take_tool', 'extinguisher')
            elif a.hand and a.hand.stage == 'extinguisher' and not rack.food:
                add('put extinguisher', '把灭火器放回架子', 'put_tool', 'extinguisher')
        for item_id, item in self.ground.items():
            if item.lock in (None, who):
                if self.can_swap_pots(a.hand,item.food):
                    out.append(Action('swap pot ground '+item_id,'与地上的锅交换（各自保留锅内食物）','swap_ground_pot',item.location,self.ground_swap_signature(who,item_id)))
                out.append(Action(f"pickup {item_id}",
                                  f"去{self.place(item.location).name}捡起 {item_id}（{self.food_name(item.food)}；自动换手）",
                                  "pickup", item.location, (a.hand.id if a.hand else None, item_id, item.location)))
                if self.can_load_ground(who,item_id):
                    out.append(Action('load ground '+item_id,'把切好的牛肉放入地上空锅（离灶不加热）','load_ground',item.location,self.ground_plate_signature(who,item_id)))
                if self.can_plate_ground(who, item_id):
                    out.append(Action(f'plate ground {item_id}', '用手中的干净盘盛出地上锅里的菜（空锅留在原地）',
                                      'plate_ground', item.location, self.ground_plate_signature(who, item_id)))
        for key in self.boards:
            s = self.stations[key]
            if s.lock not in (None, who):
                if not a.hand and s.food and s.food.stage=='raw' and s.food.ingredient!='bread' and self.can_share_work(who,'chop',key):
                    add(f'chop {key}',f'一起切配 {s.food.id}（共享进度）','chop',key)
                continue
            if not s.food and a.hand and a.hand.stage in ("raw", "chopped"):
                add(f"put {key}", f"将手中食材放到{s.name}", "put_board", key)
            if s.food:
                if self.c.get('level') in (2,3) and self.can_add(a.hand,s.food):
                    add('assemble '+key,'用手中餐盘接取'+s.name+'的食材','assemble',key)
                if s.food.stage == "raw" and s.food.ingredient != "bread" and not a.hand:
                    add(f"chop {key}", f"到{s.name}切 {s.food.id}（剩 {max(0,self.c['chop_seconds']-s.food.chopped):.1f}s）", "chop", key)
                add(f"take {key}", f"从{s.name}拿走 {s.food.id}（{self.food_name(s.food)}）", "take_board", key)
        for key in self.pots:
            s = self.stations[key]
            if s.lock not in (None, who):
                continue
            if s.fire:
                if a.hand and a.hand.stage == 'extinguisher':
                    add(f"extinguish {key}", f"拿灭火器到{s.name}灭火（4s；随后仍须清理糊菜）", "extinguish", key)
                continue
            if not s.pot_id:
                if a.hand and a.hand.stage == 'pot':
                    add(f'put pot {key}', f'把手中的锅放回{s.name}（有食物时恢复加热）', 'return_pot', key)
                continue
            add(f'take pot {key}', f'端起{s.name}的锅（离开灶台停止加热，占手持位）', 'lift_pot', key)
            if a.hand and a.hand.stage=='pot':
                add('swap pot '+key,'与'+s.name+'的锅交换（各自保留锅内食物）','swap_pot',key)
            if not s.food and a.hand and a.hand.stage == "chopped" and a.hand.ingredient == "beef" and not a.hand.plate_id:
                add(f"put {key}", f"将半成品放进{s.name}，开始自动加热", "put_pot", key)
            if s.food:
                if a.hand and self.can_add(a.hand,s.food):
                    add(f'plate {key}', f'用手中的干净盘盛出{s.name}的菜', 'plate_pot', key)
                add(f"clear {key}", f"清空{s.name}的食物（损耗 2 元）", "clear", key)
        for target, s in self.stations.items():
            if target != a.location:
                add(f"go {target}", f"走到{s.name}（{s.area}）", "go", target)
        # Continuing a chop/move must not accidentally restart its remaining duration.
        if a.job:
            out = [x for x in out if x.key != a.job.action.key]
        # Burning worktops cannot be used until extinguished. Both chefs see
        # exactly the same legal rescue actions, including empty counters.
        out = [x for x in out if x.kind in ('go', 'extinguish') or not
               (x.target in self.stations and self.stations[x.target].fire)]
        for key in self.boards + self.counters:
            s = self.stations[key]
            if s.fire and s.lock in (None, who) and a.hand and a.hand.stage == 'extinguisher':
                add(f'extinguish {key}', f'拿灭火器到{s.name}灭火（4s）', 'extinguish', key)
        return out

    @staticmethod
    def food_name(food):
        if food.ingredient in ('bread','lettuce','tomato') and not food.plate_id:
            return {'bread':'面包','lettuce':'生菜','tomato':'番茄'}[food.ingredient]+(' · 切好' if food.stage=='chopped' else '')
        if food.components and set(food.components)!={'beef'}:
            return '糊菜' if food.stage=='burnt' else ('汉堡' if Kitchen.dish(food)=='burger' else '待组装菜品')
        return STATES[food.stage]

    @staticmethod
    def dish(food):
        if not food or not food.plate_id:return None
        parts=set(food.components or ('beef',))
        if parts=={'beef'}:return 'steak'
        if parts=={'bread','lettuce','tomato','beef'}:return 'burger'
        return None

    @staticmethod
    def can_add(plate,ingredient):
        if not plate or not ingredient or ingredient.plate_id:return False
        if plate.stage!='clean_plate' and not plate.plate_id:return False
        parts=set(plate.components or (('beef',) if plate.plate_id else ()))
        name=ingredient.ingredient
        valid=(name=='beef' and ingredient.stage in ('ready','burnt') or
               name in ('lettuce','tomato') and ingredient.stage=='chopped' or name=='bread' and ingredient.stage in ('raw','chopped'))
        return valid and name not in parts

    @staticmethod
    def merge_plate(plate,ingredient):
        assert Kitchen.can_add(plate,ingredient)
        parts=set(plate.components or (('beef',) if plate.plate_id else ()))|{ingredient.ingredient}
        stage='burnt' if 'burnt' in (plate.stage,ingredient.stage) else ('ready' if parts in ({'beef'},{'beef','bread','lettuce','tomato'}) else 'assembled')
        return Food(ingredient.id if not plate.plate_id else plate.id,stage,chopped=max(plate.chopped,ingredient.chopped),heated=max(plate.heated,ingredient.heated),plate_id=plate.plate_id or plate.id,
                    ingredient='dish',components=tuple(sorted(parts)))

    @staticmethod
    def can_merge_plates(destination, source):
        if not source or not source.plate_id or source.stage not in ('ready','burnt','assembled'):
            return False
        if not destination or destination.stage not in ('clean_plate','ready','burnt','assembled'):
            return False
        if destination.stage!='clean_plate' and not destination.plate_id:return False
        dest_id=destination.plate_id or destination.id
        if dest_id==source.plate_id:return False
        parts=set(destination.components or (('beef',) if destination.plate_id else ()))
        incoming=set(source.components or ('beef',))
        return not parts.intersection(incoming) and parts|incoming <= {'beef','bread','lettuce','tomato'}

    @staticmethod
    def merge_plates(destination, source):
        """Return combined destination and the original, clean source plate."""
        assert Kitchen.can_merge_plates(destination,source)
        parts=set(destination.components or (('beef',) if destination.plate_id else ()))|set(source.components or ('beef',))
        stage='burnt' if 'burnt' in (destination.stage,source.stage) else ('ready' if parts in ({'beef'},{'beef','bread','lettuce','tomato'}) else 'assembled')
        combined=Food(destination.id,stage,chopped=max(destination.chopped,source.chopped),
                      heated=max(destination.heated,source.heated),plate_id=destination.plate_id or destination.id,
                      ingredient='dish',components=tuple(sorted(parts)))
        return combined,Food(source.plate_id,'clean_plate')

    def ground_plate_signature(self, who, item_id):
        hand = self.chefs[who].hand
        item = self.ground.get(item_id)
        return (hand.id if hand else None, item_id, item.location if item else None,
                item.food.contents.id if item and item.food.contents else None)

    @staticmethod
    def can_swap_pots(hand,other):
        return bool(hand and other and hand.stage==other.stage=='pot' and hand.id!=other.id)

    def ground_swap_signature(self,who,item_id):
        hand=self.chefs[who].hand
        return self.ground_plate_signature(who,item_id)+(hand.contents.id if hand and hand.contents else None,)

    @staticmethod
    def heat_stove(station):
        station.heating=station.food is not None
        if station.food and station.food.stage=='chopped':
            station.food.stage='cooking'

    @staticmethod
    def can_load_pot(hand,pot):
        return bool(hand and hand.stage=='chopped' and hand.ingredient=='beef' and not hand.plate_id
                    and pot and pot.stage=='pot' and pot.contents is None)

    def can_load_ground(self,who,item_id):
        item=self.ground.get(item_id)
        return bool(item and item.lock in (None,who) and self.can_load_pot(self.chefs[who].hand,item.food))

    def can_plate_ground(self, who, item_id):
        hand, item = self.chefs[who].hand, self.ground.get(item_id)
        return bool(hand and item and self.can_add(hand,item.food.contents) and item.lock in (None, who)
                    and item.food.stage == 'pot' and item.food.contents
                    and item.food.contents.stage in ('ready', 'burnt') and not item.food.contents.plate_id)

    def stop(self, who):
        a = self.chefs[who]
        if a.job:
            self.swap_slots.pop(a.job.id, None)
            self.emit(f"{NAMES[who]}中断：{a.job.action.label}", kind="interrupted", actor=who)
            for s in self.stations.values():
                if s.lock == who:
                    s.lock = next((other for other,b in self.chefs.items() if other!=who and b.job and b.job.working
                                   and s is self.place(b.job.action.target) and b.job.action.kind in ('chop','wash')),None)
            for item in self.ground.values():
                if item.lock == who:
                    item.lock = None
            a.job = None

    def start(self, who, action):
        current = next((x for x in self.actions(who) if x.key == action.key and x.expected == action.expected), None)
        if not current:
            return False, "状态已变化，该动作已失效；请重新查看选项"
        if action.kind == "continue":
            return True, "继续"
        if action.kind == "wait":
            return True, "等待"
        self.stop(who)
        if action.kind == "stop":
            return True, "已中断"
        a = self.chefs[who]
        s = self.place(action.target)
        work = {"chop": self.c["chop_seconds"]-(s.food.chopped if s.food else 0),
                "wash": self.wash_seconds-(s.food.washed if s.food else 0),
                "extinguish": 4, "clear": 2, "go": 0}.get(action.kind, self.c.get('handling_seconds', .15))
        self.job_serial += 1
        a.job = Job(self.job_serial, action, self.travel_time(a, action.target), work)
        self.emit(f"{NAMES[who]}开始：{action.label}（路程 {a.job.travel:.0f}s + 操作 {work:.1f}s）", kind="action_start", actor=who, action=action.key)
        return True, "开始"

    def command(self, who, key):
        action = next((x for x in self.actions(who) if x.key == key), None)
        return self.start(who, action) if action else (False, "当前无法执行；输入 m 查看可用动作")

    def menu_numbers(self):
        # Stable for the whole round: an asynchronous refresh never repurposes a number.
        keys = ["wait", "continue", "stop", "fetch", "serve", "discard"]
        for key in self.boards:
            keys.extend([f"put {key}", f"chop {key}", f"take {key}"])
        for key in self.pots:
            keys.extend([f"put {key}", f"extinguish {key}", f"clear {key}"])
        keys.extend(f"go {key}" for key in self.stations)
        keys.append('drop')
        keys.extend(['take extinguisher', 'put extinguisher'])
        keys.extend(['take returns', 'put sink', 'wash', 'take sink'])
        for key in self.counters:
            keys.extend([f'take {key}', f'put {key}', f'plate {key}'])
        keys.extend(f'extinguish {key}' for key in self.boards + self.counters)
        for key in self.pots:
            keys.extend([f'take pot {key}', f'put pot {key}'])
        keys.extend(f'plate {key}' for key in self.pots)
        numbers = {key: i for i, key in enumerate(keys, 1)}
        for item_id in self.ground:
            if item_id not in self.pickup_numbers:
                self.pickup_numbers[item_id] = 100 + len(self.pickup_numbers)
        numbers.update({f'pickup {key}': value for key, value in self.pickup_numbers.items()})
        return numbers

    def _reserve_hand_swap(self, who, job):
        if self.chefs[who].hand and job.action.kind in TAKE_KINDS:
            self.swap_slots[job.id] = job.action.target
        return True

    def _begin_work(self, who, job):
        a = self.chefs[who]
        s = self.place(job.action.target)
        a.location = job.action.target
        # Recheck at arrival; another chef can use a station while we walk there.
        if job.action.kind in ('drop', 'pickup', 'plate_ground', 'load_ground','swap_ground_pot'):
            if job.action.kind == 'drop':
                valid = a.hand is not None and (a.hand.id, a.location) == job.action.expected
            elif job.action.kind=='swap_ground_pot':
                item=self.ground.get(job.action.expected[1])
                valid=bool(item and item.lock in (None,who) and self.can_swap_pots(a.hand,item.food)
                           and self.ground_swap_signature(who,item.food.id)==job.action.expected)
                if valid:item.lock=who
            elif job.action.kind in ('plate_ground','load_ground'):
                item_id = job.action.expected[1]
                valid = ((self.can_plate_ground(who,item_id) if job.action.kind=='plate_ground' else self.can_load_ground(who,item_id))
                         and self.ground_plate_signature(who, item_id) == job.action.expected)
                if valid:
                    self.ground[item_id].lock = who
            else:
                item = self.ground.get(job.action.expected[1])
                valid = ((a.hand.id if a.hand else None) == job.action.expected[0] and item is not None and item.location == a.location
                         and item.lock in (None, who))
                if valid:
                    item.lock = who
            if not valid:
                self.emit(f"{NAMES[who]}到达后发现地上物品已变化或被捡走，动作取消", kind='arrival_conflict', actor=who)
                a.job = None
                return False
            if not self._reserve_hand_swap(who, job):
                self.stop(who)
                return False
            job.working = True
            return True
        if job.action.kind == 'chop' and (a.hand or not s.food or s.food.stage != 'raw' or s.food.ingredient=='bread'):
            self.emit(f'{NAMES[who]}到达后发现食材已不需要切配，动作取消', kind='arrival_conflict', actor=who)
            self.stop(who)
            return False
        if job.action.kind == 'chop':
            job.work = max(0, self.c['chop_seconds']-s.food.chopped)
        if job.action.kind=='wash':
            if a.hand or not s.food or s.food.stage!='dirty_plate':
                self.stop(who);return False
            job.work=max(0,self.wash_seconds-s.food.washed)
        sharing=s.lock not in (None,who) and self.can_share_work(who,job.action.kind,job.action.target)
        if job.action.kind != "go" and (self.signature(who, job.action.target) != job.action.expected or (s.lock not in (None, who) and not sharing)):
            self.emit(f"{NAMES[who]}到达后发现目标已变化或被占用，动作取消", kind="arrival_conflict", actor=who)
            a.job = None
            return False
        if not self._reserve_hand_swap(who, job):
            self.stop(who)
            return False
        if job.action.kind != "go" and not sharing:
            s.lock = who
        job.working = True
        return True

    def _finish(self, who, job):
        a = self.chefs[who]
        s = self.place(job.action.target)
        k = job.action.kind
        partners=[p for p in self.work_participants(job.action.target,k) if p!=who] if k in ('chop','wash') else []
        displaced = a.hand if k in TAKE_KINDS else None
        if k == "fetch":
            self.serial += 1
            a.hand = Food(f"F{self.serial}",ingredient=self.ingredients[job.action.target])
        elif k in ('take_plate', 'take_return', 'take_sink', 'take_counter'):
            a.hand, s.food = s.food, None
        elif k == 'put_counter':
            s.food, a.hand = a.hand, None
        elif k == 'put_sink':
            s.food, a.hand = a.hand, None
        elif k == 'wash':
            s.food.stage = 'clean_plate'
            s.food.washed = self.wash_seconds
            self.emit(f'{NAMES[who]}洗好了 {s.food.id}，可取走盛菜或放到空柜台', kind='washed', actor=who)
        elif k == 'lift_pot':
            a.hand = Food(s.pot_id, 'pot', contents=s.food)
            s.pot_id, s.food, s.heating = None, None, False
        elif k == 'return_pot':
            s.pot_id, s.food = a.hand.id, a.hand.contents
            a.hand = None
            self.heat_stove(s)
        elif k == 'swap_pot':
            if self.signature(who,job.action.target)!=job.action.expected or s.fire:
                self.stop(who);return
            if job.action.target in self.pots:
                incoming=a.hand
                a.hand=Food(s.pot_id,'pot',contents=s.food)
                s.pot_id,s.food=incoming.id,incoming.contents
                self.heat_stove(s)
            else:
                a.hand,s.food=s.food,a.hand
        elif k == 'swap_ground_pot':
            item_id=job.action.expected[1];item=self.ground.get(item_id)
            if (not item or item.lock not in (None,who) or not self.can_swap_pots(a.hand,item.food)
                    or self.ground_swap_signature(who,item_id)!=job.action.expected):
                self.stop(who);return
            incoming=a.hand
            a.hand=item.food
            del self.ground[item_id]
            self.ground[incoming.id]=GroundItem(incoming,item.location)
        elif k == 'empty_pot':
            a.hand.contents = None
            self.money -= 2
        elif k == 'assemble':
            if self.can_add(s.food,a.hand):
                s.food=self.merge_plate(s.food,a.hand);a.hand=None
            elif self.can_add(a.hand,s.food):
                a.hand=self.merge_plate(a.hand,s.food);s.food=None
        elif k == 'merge_plates':
            a.hand,s.food=self.merge_plates(a.hand,s.food)
        elif k == 'plate_counter':
            s.food=self.merge_plate(s.food,a.hand.contents);a.hand.contents=None
        elif k == 'plate_from_counter':
            a.hand=self.merge_plate(a.hand,s.food.contents);s.food.contents=None
        elif k == 'plate_pot':
            a.hand=self.merge_plate(a.hand,s.food);s.food=None;s.heating=False
        elif k == 'load_counter':
            s.food.contents,a.hand=a.hand,None
        elif k == 'load_ground':
            item_id=job.action.expected[1]
            if not self.can_load_ground(who,item_id) or self.ground_plate_signature(who,item_id)!=job.action.expected:
                self.emit('地上锅或手中食材已变化，入锅取消',kind='arrival_conflict',actor=who)
                self.stop(who);return
            item=self.ground[item_id]
            item.food.contents,a.hand=a.hand,None
            item.lock=None
        elif k == 'plate_ground':
            item_id = job.action.expected[1]
            if (not self.can_plate_ground(who, item_id)
                    or self.ground_plate_signature(who, item_id) != job.action.expected):
                self.emit('地上锅或手中餐盘已变化，装盘取消', kind='arrival_conflict', actor=who)
                self.stop(who)
                return
            item = self.ground[item_id]
            a.hand=self.merge_plate(a.hand,item.food.contents);item.food.contents=None
            item.lock=None
        elif k == 'drop':
            item_id = a.hand.id
            self.ground[item_id] = GroundItem(a.hand, a.location)
            a.hand = None
            self.emit(f"{NAMES[who]}把 {item_id} 放在{s.name}旁的地上，双方都可以捡", kind='dropped', actor=who, item=item_id)
        elif k == 'pickup':
            item = self.ground.pop(job.action.expected[1])
            a.hand = item.food
            self.emit(f"{NAMES[who]}从{s.name}旁的地上捡起 {a.hand.id}", kind='picked_up', actor=who, item=a.hand.id)
        elif k == 'take_tool':
            a.hand, s.food = s.food, None
        elif k == 'put_tool':
            s.food, a.hand = a.hand, None
        elif k == "put_board":
            s.food, a.hand = a.hand, None
        elif k == "take_board":
            a.hand, s.food = s.food, None
        elif k == "put_pot":
            s.food, a.hand = a.hand, None
            s.food.stage = "cooking"
            s.heating = True
        elif k == "chop":
            s.food.chopped = self.c["chop_seconds"]
            s.food.stage = "chopped"
        elif k == "extinguish":
            s.fire = False
            s.fire_elapsed = 0
            s.heating = False
        elif k == "clear":
            s.food = None
            s.heating = False
            self.money -= 2
        elif k == "discard":
            a.hand = Food(a.hand.plate_id, 'dirty_plate') if a.hand.plate_id else None
            self.money -= 2
        elif k == "serve":
            self.dining.append({'plate': Food(a.hand.plate_id, 'dirty_plate'), 'returns_at': self.time+self.dining_seconds})
            pending = [o for o in self.orders if o["status"] == "pending" and (self.c.get("level") not in (2,3) or o["dish"]==self.dish(a.hand))]
            o = min(pending, key=lambda x: x["deadline"]) if pending else None
            good = a.hand.stage == "ready" and o and self.time <= o["deadline"]+1e-8
            if good:
                o["status"] = "served"
                self.served += 1
                price=60 if o['dish']=='burger' else 30
                self.money += price
                self.emit(f"{NAMES[who]}完成 {o['id']}，顾客好评，收入 +{price} 元", kind="served", actor=who,dish=o['dish'])
            else:
                if o:
                    o["status"] = "rejected"
                self.bad_reviews += 1
                self.money -= 15
                reason = STATES[a.hand.stage] if a.hand.stage != "ready" else "没有有效订单"
                self.emit(f"顾客差评：{reason}；扣 15 元" + (f"，{o['id']}失败" if o else ""), kind="bad_service", actor=who)
            a.hand = None
        location = self.swap_slots.pop(job.id, None)
        if displaced:
            assert location is not None
            self.ground[displaced.id] = GroundItem(displaced, location)
            self.emit(f"{NAMES[who]}换手：把 {displaced.id} 留在{self.place(location).name}的地上，可捡回",
                      kind='swapped', actor=who, item=displaced.id, taken=a.hand.id)
        if s.lock == who:
            s.lock = None
        a.job = None
        self.emit(f"{NAMES[who]}完成动作：{job.action.label}", kind="action_done", actor=who, action=job.action.key)
        for partner in partners:
            other=self.chefs[partner];other_job=other.job
            other.job=None
            if s.lock==partner:s.lock=None
            getattr(self,'routes',{}).pop(partner,None)
            self.emit(f'{NAMES[partner]}共同完成：{other_job.action.label}',kind='action_done',actor=partner,action=other_job.action.key)

    def _return_plates(self):
        tray = self.stations['returns']
        if not tray.food and not tray.lock:
            ready = next((entry for entry in self.dining if entry['returns_at'] <= self.time+1e-8), None)
            if ready:
                tray.food = ready['plate']
                self.dining.remove(ready)
                self.emit(f'{tray.food.id} 已回到脏盘回收点，洗净后可复用', kind='plate_returned')

    def fire_neighbors(self, key):
        # Spatial kitchens override this; nonspatial environments have no
        # invented adjacency between workstations.
        return []

    def ignite(self, key, source=None):
        s = self.stations[key]
        if s.fire:
            return
        s.fire, s.fire_elapsed, s.heating, s.scorched = True, 0., False, True
        if key in self.pots and s.food and s.food.stage != 'burnt':
            s.food.stage = 'burnt'
            self.burns += 1
        self.fires += 1
        self.money -= 5
        for who,a in list(self.chefs.items()):
            if a.job and a.job.working and a.job.action.target==key:self.stop(who)
        self.emit(f'{s.name}着火！损失 5 元；必须先灭火再使用',
                  kind='fire_spread' if source else 'fire', station=key, source=source)

    def _advance_fire(self, dt):
        interval = self.c.get('fire_spread_seconds', 8)
        burning = [key for key,s in self.stations.items() if s.fire]
        for key in burning:
            s = self.stations[key]
            s.fire_elapsed += dt
            if s.fire_elapsed + 1e-8 < interval:
                continue
            s.fire_elapsed = 0.
            target = next((n for n in self.fire_neighbors(key) if not self.stations[n].fire), None)
            if target:
                self.ignite(target, source=key)
        if sum(s.fire for s in self.stations.values()) >= self.c.get('fire_loss_threshold', 5):
            self.failure_reason = 'fire_spread'
            for who in self.chefs:
                self.stop(who)
            self.emit('火势失控，本局结束', kind='fire_loss')
            self._end()

    def advance(self, seconds):
        if seconds < 0 or not math.isfinite(seconds):
            raise ValueError("时间增量无效")
        # Small deterministic substeps preserve thermal transitions and action order.
        while seconds > 1e-9 and not self.ended:
            if self.won():
                self._end()
                break
            dt = min(seconds, .05, self.c["round_seconds"]-self.time)
            if dt <= 1e-9:
                self._end()
                break
            self.time += dt
            seconds -= dt
            self._arrivals()
            self._return_plates()
            for key in self.pots:
                s = self.stations[key]
                if not s.food or s.fire or not s.heating:
                    continue
                f = s.food
                f.heated += dt
                ready = self.c["cook_seconds"]
                burn = ready + self.c["burn_after_ready"]
                fire = burn + self.c["fire_after_burn"]
                if f.stage == "cooking" and f.heated >= ready-1e-8:
                    f.stage = "ready"
                    self.emit(f"{s.name}的 {f.id} 熟了！{self.c['burn_after_ready']}s 后糊锅", kind="ready")
                if f.stage == "ready" and f.heated >= burn-1e-8:
                    f.stage = "burnt"
                    self.burns += 1
                    self.emit(f"{s.name}糊锅！{self.c['fire_after_burn']}s 后着火；糊菜上桌会被差评", kind="burn")
                if f.stage == "burnt" and f.heated >= fire-1e-8:
                    self.ignite(key)
            self._advance_fire(dt)
            if self.ended:
                break
            for who, a in self.chefs.items():
                job = a.job
                if not job:
                    continue
                remaining = dt
                if not job.working:
                    used = self._travel_step(who,job,remaining)
                    remaining -= used
                    if job.travel > 1e-8:
                        continue
                    if not self._begin_work(who, job):
                        continue
                if job.action.kind in ('chop','wash'):
                    food=self.stations[job.action.target].food
                    job.work=max(0,(self.c['chop_seconds']-food.chopped) if job.action.kind=='chop' else (self.wash_seconds-food.washed))
                used = min(job.work, remaining)
                job.work -= used
                if job.action.kind == "chop":
                    self.stations[job.action.target].food.chopped += used
                elif job.action.kind == 'wash':
                    self.stations[job.action.target].food.washed += used
                if job.action.kind in ('chop','wash'):
                    for participant in self.work_participants(job.action.target,job.action.kind):
                        self.chefs[participant].job.work=job.work
                if job.work <= 1e-8:
                    self._finish(who, job)
                    # Settle at the winning delivery, before another action or
                    # unneeded order can change an already completed mission.
                    if self.won():
                        self._end()
                        break
            if self.ended:
                break
            self._after_step(dt)
            # Complete an on-time delivery before expiring the same deadline.
            for o in self.orders:
                if o["status"] == "pending" and self.time >= o["deadline"]-1e-8:
                    o["status"] = "expired"
                    self.money -= 10
                    self.bad_reviews += 1
                    self.emit(f"{o['id']}超时，顾客离开并差评，扣 10 元", kind="expired")
            if self.time >= self.c["round_seconds"]-1e-8 or all(o["status"] not in ("future", "pending") for o in self.orders):
                self._end()

    def _end(self):
        if not self.ended:
            self.ended = True
            self.reward_seconds = math.floor(max(0, self.c['round_seconds']-self.time)+1e-8)
            if self.won() and not self.aborted:
                self.time_bonus = round(self.reward_seconds*self.c.get('time_bonus_per_second', 1), 2)
            self.emit(self.result(), kind="round_end")

    def won(self):
        return not self.failure_reason and self.served >= self.c["target_served"] and self.money >= self.c["target_money"] and self.bad_reviews <= self.c["max_bad_reviews"]

    def result(self):
        label = '火势失控' if self.failure_reason == 'fire_spread' else ("提前退出（未结算通关）" if self.aborted else ("任务成功" if self.won() else "任务未达成"))
        return f"{label}：出餐 {self.served}/{self.c['target_served']}；净收入 {self.money}/{self.c['target_money']} 元；差评 {self.bad_reviews}（最多 {self.c['max_bad_reviews']}）；糊锅 {self.burns}，着火 {self.fires}；时间奖励 {self.time_bonus:g} 元（剩余 {self.reward_seconds} 整秒）；合计 {self.money+self.time_bonus:g} 元"

    def snapshot(self):
        def food(f):
            if not f:
                return None
            if f.stage == 'extinguisher':
                return {'id': f.id, 'stage': f.stage, 'meaning': STATES[f.stage], 'tool': True}
            if f.stage == 'pot':
                return {'id': f.id, 'stage': 'pot', 'meaning': '空锅' if not f.contents else '锅 · '+STATES[f.contents.stage],
                        'contents': food(f.contents)}
            if f.stage in ('clean_plate', 'dirty_plate'):
                return {'id': f.id, 'stage': f.stage, 'meaning': STATES[f.stage],
                        'wash_remaining': 0 if f.stage == 'clean_plate' else round(max(0, self.wash_seconds-f.washed), 2)}
            return {"id": f.id, "stage": f.stage, "meaning": self.food_name(f),
                    'plate_id': f.plate_id,
                    "ingredient": f.ingredient, "components": list(f.components), "dish": self.dish(f),
                    "missing": sorted({'bread','lettuce','tomato','beef'}-set(f.components)) if f.plate_id and self.c.get('level') in (2,3) else [],
                    "chop_remaining": 0 if f.ingredient=='bread' else round(max(0, self.c["chop_seconds"]-f.chopped), 2),
                    "heat_elapsed": round(f.heated, 2)}
        chefs = {}
        for who, a in self.chefs.items():
            j = a.job
            chefs[who] = {"location": a.location, "area": self.place(a.location).area,
                          "holding": food(a.hand), "job_id": j.id if j else None,
                          "task": j.action.label if j else "idle", "target": j.action.target if j else None,
                          'action_kind': j.action.kind if j else None, 'working': bool(j and j.working),
                          "travel_remaining": round(j.travel,2) if j else 0,
                          "work_remaining": round(j.work,2) if j else 0}
        stations = {}
        for key, s in self.stations.items():
            record = {"name": s.name, "area": s.area, "food": food(s.food), "used_by": s.lock, "fire": s.fire, "heating": s.heating,
                      'pot_id': s.pot_id, 'counter': key in self.counters, 'stove': key in self.pots}
            record['fire_spread_in'] = round(max(0,self.c.get('fire_spread_seconds',8)-s.fire_elapsed),2) if s.fire else None
            record['fire_neighbors'] = self.fire_neighbors(key)
            record['workers']=self.work_participants(key,'chop')+self.work_participants(key,'wash')
            record['scorched'] = s.scorched
            if key in self.pots and s.food:
                h = s.food.heated
                record.update({"ready_in": round(max(0,self.c["cook_seconds"]-h),2),
                               "burn_in": round(max(0,self.c["cook_seconds"]+self.c["burn_after_ready"]-h),2),
                               "fire_in": round(max(0,self.c["cook_seconds"]+self.c["burn_after_ready"]+self.c["fire_after_burn"]-h),2)})
            stations[key] = record
        return {"level": self.c.get("level",1), "order_seed":self.c.get("order_seed"), "time": round(self.time,2), "round_remaining": round(self.c["round_seconds"]-self.time,2),
                'tableware': {'total': self.plate_count, 'wash_seconds': self.wash_seconds,
                    'dining_seconds': self.dining_seconds, 'return_capacity': 1,
                    'counters': self.counters,
                    'customers': [{'plate_id': d['plate'].id, 'returns_in': round(max(0, d['returns_at']-self.time), 2),
                                   'waiting_for_space': d['returns_at'] <= self.time} for d in self.dining]},
                "chefs": chefs, "stations": stations,
                "ground": [{"location": item.location, "near": self.place(item.location).name,
                            "area": self.place(item.location).area, "food": food(item.food),
                            "used_by": item.lock} for item in self.ground.values()],
                "orders": [{**o, "remaining": round(o["deadline"]-self.time,2)} for o in self.orders if o["status"] != "future"],
                "future_orders": sum(o["status"] == "future" for o in self.orders),
                "money": self.money, "served": self.served, "bad_reviews": self.bad_reviews,
                'fire_safety': {'burning_count': sum(s.fire for s in self.stations.values()),
                                'loss_threshold': self.c.get('fire_loss_threshold',5),
                                'spread_seconds': self.c.get('fire_spread_seconds',8)},
                'failure_reason': self.failure_reason,
                "settlement": {"remaining_seconds": self.reward_seconds,
                               "time_bonus": self.time_bonus,
                               "total_income": round(self.money+self.time_bonus, 2)} if self.ended else None,
                "goals": {k:self.c[k] for k in ("target_served","target_money","max_bad_reviews")}}

    def assert_invariants(self):
        foods = ([s.food for s in self.stations.values() if s.food]
                 + [a.hand for a in self.chefs.values() if a.hand]
                 + [item.food for item in self.ground.values()])
        assert len({f.id for f in foods}) == len(foods), "物品重复"
        for item_id, item in self.ground.items():
            assert item_id == item.food.id and self.place(item.location)
            if item.lock:
                j = self.chefs[item.lock].job
                assert j and j.working and j.action.kind in ('pickup', 'plate_ground', 'load_ground','swap_ground_pot') and j.action.expected[1] == item_id
        for key, s in self.stations.items():
            if key in self.counters:
                pass  # Each counter has exactly one physical item slot.
            elif key == 'extinguisher':
                assert s.food is None or s.food.stage == 'extinguisher'
            elif key in ('returns', 'sink'):
                allowed = ('dirty_plate',) if key == 'returns' else ('clean_plate', 'dirty_plate')
                assert s.food is None or s.food.stage in allowed
            elif key not in self.boards + self.pots:
                assert s.food is None, "禁止将食材存入出餐口或虚构窗口"
            if s.lock:
                j = self.chefs[s.lock].job
                assert j and j.working and j.action.target == key
            if s.fire:
                assert key in self.pots + self.boards + self.counters
            if key in self.pots and not s.pot_id:
                assert s.food is None and not s.heating
        all_items = foods + [d['plate'] for d in self.dining]
        all_items += [p['food'] for p in getattr(self, 'projectiles', {}).values()]
        # In flight counts too: a passed extinguisher is neither in a hand nor on the rack.
        assert sum(f.stage == 'extinguisher' for f in all_items) == 1, '灭火器丢失或重复'
        all_items += [f.contents for f in all_items if f.stage == 'pot' and f.contents]
        assert len({f.id for f in all_items}) == len(all_items), '容器内外物品重复'
        pots = [s.pot_id for s in self.stations.values() if s.pot_id] + [f.id for f in all_items if f.stage == 'pot']
        assert len(pots) == self.pot_count and set(pots) == {f'P{i+1}' for i in range(self.pot_count)}, '锅丢失或重复'
        plates = [f.id for f in all_items if f.stage in ('clean_plate', 'dirty_plate')]
        plates += [f.plate_id for f in all_items if f.plate_id]
        assert len(plates) == self.plate_count and set(plates) == {f'D{i}' for i in range(1, self.plate_count+1)}, '餐盘丢失或重复'
