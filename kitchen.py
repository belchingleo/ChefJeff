"""Deterministic kitchen rules. No AI policy lives in this module.

Every station, recipe, duration, rate and penalty comes from one frozen
resolved configuration (see ``config_contract`` and ``rules``); the engine has
no per-level branches.
"""
from __future__ import annotations
from dataclasses import dataclass
import functools
import json
import math
from pathlib import Path

from provenance import Provenance
from rules import Rules, runtime_config

ROOT = Path(__file__).resolve().parent
NAMES = {"human": "你", "jeff": "Jeff"}
STATES = {"raw": "生肉", "chopped": "切好", "cooking": "加热中", "ready": "熟了", "burnt": "糊了", "extinguisher": "灭火器", "clean_plate": "干净餐盘", "dirty_plate": "脏餐盘", "pot": "锅", "assembled": "待组装菜品"}


def load_config(path=None):
    c = json.loads(Path(path or ROOT / "config.json").read_text())
    for key, value in c.items():
        if key != "model" and (not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
            raise ValueError(f"配置 {key} 必须是正数")
    for key in ("boards", "pots", "plate_count", "ai_max_calls"):
        if key not in c:
            continue
        if int(c[key]) != c[key]:
            raise ValueError(f"配置 {key} 必须是整数")
    if c.get("boards", 0) > 8 or c.get("pots", 0) > 8:
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


def engine_input(method):
    """Record an outermost external call so the engine can be replayed from its inputs."""
    @functools.wraps(method)
    def wrapper(self, *args):
        outer = self._api_depth == 0
        started = self.time
        self._api_depth += 1
        try:
            result = method(self, *args)
        finally:
            self._api_depth -= 1
        if outer:
            record = {'n': len(self.inputs), 'call': method.__name__, 'game_time_ms': round(started*1000)}
            if method.__name__ == 'advance':
                record['seconds'] = args[0]
            elif args:
                record['actor'] = args[0]
            if method.__name__ == 'start':
                action = args[1]
                record['action'] = {'key': action.key, 'label': action.label, 'kind': action.kind,
                                    'target': action.target, 'expected': action.expected}
                record['accepted'] = bool(result[0])
            elif method.__name__ == 'set_manual':
                record['vector'] = [args[1], args[2]]
            elif method.__name__ == 'sprint':
                record['accepted'] = bool(result)
            self.inputs.append(record)
        return result
    return wrapper


def _tupled(value):
    return tuple(_tupled(v) for v in value) if isinstance(value, list) else value


def replay(factory, resolved, inputs):
    """Rebuild a kitchen from a frozen configuration and its recorded engine inputs."""
    k = factory(resolved)
    for record in inputs:
        call = record['call']
        if call == 'advance':
            k.advance(record['seconds'])
        elif call == 'start':
            a = record['action']
            k.start(record['actor'], Action(a['key'], a['label'], a['kind'], a['target'], _tupled(a['expected'])))
        elif call == 'stop':
            k.stop(record['actor'])
        elif call == 'set_manual':
            k.set_manual(record['actor'], *record['vector'])
        elif call == 'sprint':
            k.sprint(record['actor'])
        elif call == 'abort':
            k.abort()
        else:
            raise ValueError(f'unknown engine input {call!r}')
    return k


TAKE_KINDS = {"fetch", "take_board", "take_tool", "pickup", "take_plate", "take_return", "take_sink", "take_counter", "lift_pot"}


class Kitchen:
    def __init__(self, config=None, rng=None):
        self.resolved, self.c = runtime_config(config, rng)
        self.rules = r = Rules(self.resolved)
        self.config_hash = self.resolved['config_hash']
        self.time = 0.0
        self.event_seq = 0
        self.inputs = []
        self._api_depth = 0
        self.shared_overlap = {}
        self.revision = 0
        self.serial = 0
        # Read-only record of which completed actions touched which items (provenance.py).
        self.provenance = Provenance()
        self.job_serial = 0
        self.money = 0
        self.served = 0
        self.fires = 0
        self.burns = 0
        self.ended = False
        self.aborted = False
        self.failure_reason = None
        self.events = []
        self.ground = {}
        self.pickup_numbers = {}
        self.swap_slots = {}
        self.plate_count = r.plate_count
        self.pot_count = r.pot_count
        # Work units at rate 1; kept as attributes for existing observers.
        self.wash_seconds = r.wash_work
        self.dining_seconds = r.dining
        self.dining = []
        areas = self.resolved['map']['areas']
        self.stations, self.counters, self.boards, self.pots = {}, [], [], []
        groups = {'counter': self.counters, 'board': self.boards, 'stove': self.pots}
        for st in self.resolved['stations']:
            self.stations[st['id']] = Station(st['name'], areas[st['area']]['name'])
            groups.get(st['type'], []).append(st['id'])
        self.ingredients = dict(r.sources)
        self.serves = r.of_type('serving_window')
        self.bins = r.of_type('bin')
        self.rack = r.of_type('tool_rack')[0]
        self.returns = r.of_type('plate_return')[0]
        self.sink = r.of_type('sink')[0]
        self._place_inventory()
        self.chefs = {"human": Chef(next(iter(self.ingredients))), "jeff": Chef(self.pots[0])}
        sec = lambda ms: ms // 1000 if ms % 1000 == 0 else ms / 1000
        parts = {k: [c['item'] for c in v['components']] for k, v in r.recipes.items()}
        self.orders = [{'id': o['order_id'], 'dish': o['recipe_ref'], 'arrival': sec(o['arrival_game_ms']),
                        'patience': sec(o['patience_game_ms']), 'deadline': sec(o['deadline_game_ms']),
                        'status': 'future', 'ingredients': list(parts[o['recipe_ref']])}
                       for o in self.resolved['order_plan']['orders']]
        self._arrivals()

    def _place_inventory(self):
        for entry in self.rules.inventory:
            station = self.stations[entry['at']]
            if entry['object'] == 'pot' and self.rules.station_types[entry['at']] == 'stove':
                station.pot_id = entry['id']
            elif entry['object'] == 'pot':
                station.food = Food(entry['id'], 'pot')
            elif entry['object'] == 'plate':
                station.food = Food(entry['id'], 'clean_plate' if entry.get('state', 'clean') == 'clean' else 'dirty_plate')
            else:
                station.food = Food(entry['id'], 'extinguisher')

    def state_label(self, item, stage):
        definition = self.rules.items[item]
        return definition.get('state_names', {}).get(stage, definition['name'])

    def food_label(self, food):
        return self.rules.item_names.get(food.ingredient, food.ingredient)

    def assemble_label(self, place_name, placed, held):
        """Say which way the ingredient moves: onto the plate that is there, or onto the held plate."""
        if self.can_add(placed, held):
            return f'把手中的{self.food_label(held)}放进{place_name}的盘里'
        return f'把{place_name}的{self.food_label(placed)}加进手中的盘'

    def recipe_name(self, dish):
        return self.rules.recipe_names.get(dish, dish)

    def emit(self, message, **extra):
        self.revision += 1
        self.event_seq += 1
        self.events.append({"t": round(self.time, 3), "message": message, **extra,
                            "seq": self.event_seq, "game_time_ms": round(self.time*1000)})

    def _arrivals(self):
        for o in self.orders:
            if o["status"] == "future" and o["arrival"] <= self.time + 1e-8:
                o["status"] = "pending"
                self.emit(f"新订单 {o['id']}：{self.recipe_name(o['dish'])}，截止 {o['deadline']:.0f}s", kind="order", order_id=o['id'])

    def travel_time(self, chef, target):
        if chef.location == target:
            return 0
        same = self.stations[chef.location].area == self.stations[target].area
        return self.rules.same_area if same else self.rules.cross_area

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
        loss = -self.rules.penalty['discard']
        for i, (source, ingredient) in enumerate(self.ingredients.items()):
            name = self.state_label(ingredient, self.rules.items[ingredient]['initial_state'])
            if i == 0:
                add("fetch", f"到{self.stations[source].name}取一份{name}（手中物品自动放到地上）", "fetch", source)
            else:
                add('fetch '+source, '取一份'+name+'（自动换手）', 'fetch', source)
        if a.hand:
            if a.hand.plate_id and self.dish(a.hand):
                for i, key in enumerate(self.serves):
                    add("serve" if i == 0 else f"serve {key}", "拿已装盘的菜出餐（没有订单在等这道菜会扣钱，糊太久会被拒收）", "serve", key)
            if a.hand.stage not in ('extinguisher', 'clean_plate', 'dirty_plate', 'pot'):
                add("discard", f"去垃圾桶丢弃手中食物（损耗 {loss} 元，无法捡回）", "discard", self.bins[0])
            if a.hand.stage == 'pot' and a.hand.contents:
                add('discard', f'倒掉手中锅里的食物（损耗{loss}元，保留空锅）', 'empty_pot', self.bins[0])
            out.append(Action("drop", f"将手中物品放到{self.place(a.location).name}旁的地上（可捡回，不扣钱）",
                              "drop", a.location, (a.hand.id, a.location)))
        for key in self.counters:
            s = self.stations[key]
            if s.lock not in (None, who):
                continue
            if s.food:
                if self.can_swap_pots(a.hand,s.food):
                    add('swap pot '+key,'与'+s.name+'的锅交换（各自保留锅内食物）','swap_pot',key)
                if self.rules.multi_component and a.hand:
                    if self.can_add(s.food,a.hand) or self.can_add(a.hand,s.food):
                        add('assemble '+key,self.assemble_label(s.name,s.food,a.hand),'assemble',key)
                if self.rules.multi_component and self.can_merge_plates(a.hand,s.food):
                    add('merge '+key,'把'+s.name+'盘中食物合入手中盘（空盘留在原位）','merge_plates',key)
                if self.can_load_pot(a.hand,s.food):
                    add('load '+key,f'把切好的{self.food_label(a.hand)}放入'+s.name+'的空锅（离灶不加热）','load_counter',key)
                kind = 'take_plate' if s.food.stage == 'clean_plate' else 'take_counter'
                add(f'take {key}', f'从{s.name}拿起{self.food_name(s.food)}（自动换手）', kind, key)
                if a.hand and a.hand.stage == 'pot' and self.can_add(s.food,a.hand.contents):
                    add(f'plate {key}', f'把手中锅里的菜盛到{s.name}的盘里（空锅留在手中）', 'plate_counter', key)
                if s.food.stage == 'pot' and a.hand and self.can_add(a.hand,s.food.contents):
                    add(f'plate {key}', f'用手中的盘盛出{s.name}锅里的菜', 'plate_from_counter', key)
            elif a.hand:
                add(f'put {key}', f'把手中物品放到{s.name}（每格一件）', 'put_counter', key)
        for key, kind in ((self.returns, 'take_return'), (self.sink, 'take_sink')):
            s = self.stations[key]
            if s.lock not in (None, who):
                if key==self.sink and not a.hand and s.food and s.food.stage=='dirty_plate' and self.can_share_work(who,'wash',key):
                    add('wash','一起洗碗（共享进度）','wash',key)
                continue
            if s.food:
                add(f'take {key}', f'从{s.name}拿起{self.food_name(s.food)}（自动换手）', kind, key)
            if key == self.sink:
                if not s.food and a.hand and a.hand.stage == 'dirty_plate':
                    add(f'put {key}', f'把脏餐盘放入{s.name}', 'put_sink', key)
                if s.food and s.food.stage == 'dirty_plate' and not a.hand:
                    add('wash', f'洗碗（剩 {max(0, self.wash_seconds-s.food.washed):.1f}s；可中断续洗）', 'wash', key)
        rack = self.stations[self.rack]
        if rack.lock in (None, who):
            if rack.food:
                add(f'take {self.rack}', f'去{rack.name}拿灭火器（占用手持位）', 'take_tool', self.rack)
            elif a.hand and a.hand.stage == 'extinguisher' and not rack.food:
                add(f'put {self.rack}', '把灭火器放回架子', 'put_tool', self.rack)
        for item_id, item in self.ground.items():
            if item.lock in (None, who):
                if self.can_swap_pots(a.hand,item.food):
                    out.append(Action('swap pot ground '+item_id,'与地上的锅交换（各自保留锅内食物）','swap_ground_pot',item.location,self.ground_swap_signature(who,item_id)))
                out.append(Action(f"pickup {item_id}",
                                  f"去{self.place(item.location).name}捡起 {item_id}（{self.food_name(item.food)}；自动换手）",
                                  "pickup", item.location, (a.hand.id if a.hand else None, item_id, item.location)))
                if self.can_load_ground(who,item_id):
                    out.append(Action('load ground '+item_id,f'把切好的{self.food_label(a.hand)}放入地上空锅（离灶不加热）','load_ground',item.location,self.ground_plate_signature(who,item_id)))
                if self.can_assemble_ground(who,item_id):
                    out.append(Action('assemble ground '+item_id,self.assemble_label(self.place(item.location).name,item.food,a.hand),'assemble_ground',
                                      item.location,self.ground_assembly_signature(who,item_id)))
                if self.can_plate_ground(who, item_id):
                    out.append(Action(f'plate ground {item_id}', '用手中的干净盘盛出地上锅里的菜（空锅留在原地）',
                                      'plate_ground', item.location, self.ground_plate_signature(who, item_id)))
        for key in self.boards:
            s = self.stations[key]
            if s.lock not in (None, who):
                if not a.hand and s.food and self.rules.choppable(s.food) and self.can_share_work(who,'chop',key):
                    add(f'chop {key}',f'一起切配 {s.food.id}（共享进度）','chop',key)
                continue
            if not s.food and a.hand and a.hand.stage in ("raw", "chopped"):
                add(f"put {key}", f"将手中食材放到{s.name}", "put_board", key)
            if s.food:
                if self.rules.multi_component and self.can_add(a.hand,s.food):
                    add('assemble '+key,'用手中餐盘接取'+s.name+'的食材','assemble',key)
                if self.rules.choppable(s.food) and not a.hand:
                    add(f"chop {key}", f"到{s.name}切 {s.food.id}（剩 {max(0,self.rules.chop_work(s.food.ingredient)-s.food.chopped):.1f}s）", "chop", key)
                add(f"take {key}", f"从{s.name}拿走 {s.food.id}（{self.food_name(s.food)}）", "take_board", key)
        for key in self.pots:
            s = self.stations[key]
            if s.lock not in (None, who):
                continue
            if s.fire:
                if a.hand and a.hand.stage == 'extinguisher':
                    add(f"extinguish {key}", f"拿灭火器到{s.name}灭火（{self.rules.extinguish:g}s；随后仍须清理糊菜）", "extinguish", key)
                continue
            if not s.pot_id:
                if a.hand and a.hand.stage == 'pot':
                    add(f'put pot {key}', f'把手中的锅放回{s.name}（有食物时恢复加热）', 'return_pot', key)
                continue
            add(f'take pot {key}', f'端起{s.name}的锅（离开灶台停止加热，占手持位）', 'lift_pot', key)
            if a.hand and a.hand.stage=='pot':
                add('swap pot '+key,'与'+s.name+'的锅交换（各自保留锅内食物）','swap_pot',key)
            if not s.food and a.hand and self.rules.potable(a.hand):
                add(f"put {key}", f"将半成品放进{s.name}，开始自动加热", "put_pot", key)
            if s.food:
                if a.hand and self.can_add(a.hand,s.food):
                    add(f'plate {key}', f'用手中的干净盘盛出{s.name}的菜', 'plate_pot', key)
                add(f"clear {key}", f"清空{s.name}的食物（损耗 {loss} 元）", "clear", key)
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
                add(f'extinguish {key}', f'拿灭火器到{s.name}灭火（{self.rules.extinguish:g}s）', 'extinguish', key)
        return out

    def food_name(self, food):
        item = self.rules.items.get(food.ingredient)
        if item and not food.plate_id and 'state_names' not in item:
            return item['name']+(' · 切好' if food.stage=='chopped' else '')
        parts = set(food.components)
        if parts and not (len(parts) == 1 and 'state_names' in self.rules.items.get(next(iter(parts)), {})):
            dish = self.dish(food)
            return '糊菜' if food.stage=='burnt' else (self.recipe_name(dish) if dish else '待组装菜品')
        if item and not food.plate_id and food.stage in item['states']:
            return self.state_label(food.ingredient, food.stage)
        return STATES[food.stage]

    @staticmethod
    def parts(food):
        """Components on a plate; a plated item without a component list is that single item."""
        return set(food.components or ((food.ingredient,) if food.plate_id else ()))

    def dish(self, food):
        if not food or not food.plate_id:return None
        return self.rules.dish(food.components or (food.ingredient,))

    def can_add(self,plate,ingredient):
        if not plate or not ingredient or ingredient.plate_id:return False
        if plate.stage!='clean_plate' and not plate.plate_id:return False
        name=ingredient.ingredient
        return self.rules.platable(name,ingredient.stage) and name not in self.parts(plate)

    def _dish_stage(self, parts, *stages):
        return 'burnt' if 'burnt' in stages else ('ready' if self.rules.dish(parts) else 'assembled')

    def merge_plate(self,plate,ingredient):
        assert self.can_add(plate,ingredient)
        parts=self.parts(plate)|{ingredient.ingredient}
        stage=self._dish_stage(parts,plate.stage,ingredient.stage)
        return Food(ingredient.id if not plate.plate_id else plate.id,stage,chopped=max(plate.chopped,ingredient.chopped),heated=max(plate.heated,ingredient.heated),plate_id=plate.plate_id or plate.id,
                    ingredient='dish',components=tuple(sorted(parts)))

    def can_merge_plates(self, destination, source):
        if not source or not source.plate_id or source.stage not in ('ready','burnt','assembled'):
            return False
        if not destination or destination.stage not in ('clean_plate','ready','burnt','assembled'):
            return False
        if destination.stage!='clean_plate' and not destination.plate_id:return False
        dest_id=destination.plate_id or destination.id
        if dest_id==source.plate_id:return False
        parts=self.parts(destination)
        incoming=self.parts(source)
        return not parts.intersection(incoming) and parts|incoming <= self.rules.all_parts

    def merge_plates(self, destination, source):
        """Return combined destination and the original, clean source plate."""
        assert self.can_merge_plates(destination,source)
        parts=self.parts(destination)|self.parts(source)
        stage=self._dish_stage(parts,destination.stage,source.stage)
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

    def can_load_pot(self,hand,pot):
        return bool(hand and self.rules.potable(hand)
                    and pot and pot.stage=='pot' and pot.contents is None)

    def can_load_ground(self,who,item_id):
        item=self.ground.get(item_id)
        return bool(item and item.lock in (None,who) and self.can_load_pot(self.chefs[who].hand,item.food))

    def can_assemble_ground(self,who,item_id):
        """Counter-style assembly with a floor plate or floor ingredient (ruleset opt-in)."""
        hand,item=self.chefs[who].hand,self.ground.get(item_id)
        return bool(self.rules.ground_assembly and self.rules.multi_component and hand and item and item.lock in (None,who)
                    and (self.can_add(item.food,hand) or self.can_add(hand,item.food)))

    def ground_assembly_signature(self,who,item_id):
        hand,item=self.chefs[who].hand,self.ground.get(item_id)
        contents=lambda food:','.join(sorted(self.parts(food))) if food else None
        return (hand.id if hand else None,item_id,item.location if item else None,
                contents(hand),contents(item.food if item else None))

    def can_plate_ground(self, who, item_id):
        hand, item = self.chefs[who].hand, self.ground.get(item_id)
        return bool(hand and item and self.can_add(hand,item.food.contents) and item.lock in (None, who)
                    and item.food.stage == 'pot' and item.food.contents
                    and item.food.contents.stage in ('ready', 'burnt') and not item.food.contents.plate_id)

    @engine_input
    def stop(self, who):
        a = self.chefs[who]
        if a.job:
            self.swap_slots.pop(a.job.id, None)
            self.emit(f"{NAMES[who]}中断：{a.job.action.label}", kind="interrupted", actor=who, action_id=a.job.id)
            job = a.job
            if job.working and job.action.kind in ('chop', 'wash'):
                remaining = [p for p in self.work_participants(job.action.target, job.action.kind) if p != who]
                if remaining:
                    self.emit(f"{NAMES[who]}离开{self.place(job.action.target).name}的共同操作，进度保留", kind='shared_work_leave',
                              actor=who, action_id=job.id, station=job.action.target, workers=len(remaining))
            for s in self.stations.values():
                if s.lock == who:
                    s.lock = next((other for other,b in self.chefs.items() if other!=who and b.job and b.job.working
                                   and s is self.place(b.job.action.target) and b.job.action.kind in ('chop','wash')),None)
            for item in self.ground.values():
                if item.lock == who:
                    item.lock = None
            a.job = None

    @engine_input
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
        work = {"chop": (self.rules.chop_work(s.food.ingredient)-s.food.chopped) if s.food else 0,
                "wash": self.wash_seconds-(s.food.washed if s.food else 0),
                "extinguish": self.rules.extinguish, "clear": self.rules.clear, "go": 0}.get(action.kind, self.rules.handling)
        self.job_serial += 1
        a.job = Job(self.job_serial, action, self.travel_time(a, action.target), work)
        self.emit(f"{NAMES[who]}开始：{action.label}（路程 {a.job.travel:.0f}s + 操作 {work:.1f}s）", kind="action_start", actor=who, action=action.key, action_id=a.job.id)
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
        keys.extend([f'take {self.rack}', f'put {self.rack}'])
        keys.extend([f'take {self.returns}', f'put {self.sink}', 'wash', f'take {self.sink}'])
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
        if job.action.kind in ('drop', 'pickup', 'plate_ground', 'load_ground','swap_ground_pot','assemble_ground'):
            if job.action.kind == 'drop':
                valid = a.hand is not None and (a.hand.id, a.location) == job.action.expected
            elif job.action.kind=='swap_ground_pot':
                item=self.ground.get(job.action.expected[1])
                valid=bool(item and item.lock in (None,who) and self.can_swap_pots(a.hand,item.food)
                           and self.ground_swap_signature(who,item.food.id)==job.action.expected)
                if valid:item.lock=who
            elif job.action.kind=='assemble_ground':
                item_id=job.action.expected[1]
                valid=self.can_assemble_ground(who,item_id) and self.ground_assembly_signature(who,item_id)==job.action.expected
                if valid:self.ground[item_id].lock=who
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
                self.emit(f"{NAMES[who]}到达后发现地上物品已变化或被捡走，动作取消", kind='arrival_conflict', actor=who, action_id=job.id)
                a.job = None
                return False
            if not self._reserve_hand_swap(who, job):
                self.stop(who)
                return False
            job.working = True
            return True
        if job.action.kind == 'chop' and (a.hand or not s.food or not self.rules.choppable(s.food)):
            self.emit(f'{NAMES[who]}到达后发现食材已不需要切配，动作取消', kind='arrival_conflict', actor=who, action_id=job.id)
            self.stop(who)
            return False
        if job.action.kind == 'chop':
            job.work = max(0, self.rules.chop_work(s.food.ingredient)-s.food.chopped)
        if job.action.kind=='wash':
            if a.hand or not s.food or s.food.stage!='dirty_plate':
                self.stop(who);return False
            job.work=max(0,self.wash_seconds-s.food.washed)
        sharing=s.lock not in (None,who) and self.can_share_work(who,job.action.kind,job.action.target)
        if job.action.kind != "go" and (self.signature(who, job.action.target) != job.action.expected or (s.lock not in (None, who) and not sharing)):
            self.emit(f"{NAMES[who]}到达后发现目标已变化或被占用，动作取消", kind="arrival_conflict", actor=who, action_id=job.id)
            a.job = None
            return False
        if not self._reserve_hand_swap(who, job):
            self.stop(who)
            return False
        if job.action.kind != "go" and not sharing:
            s.lock = who
        job.working = True
        if job.action.kind in ('chop', 'wash'):
            workers = self.work_participants(job.action.target, job.action.kind)
            if len(workers) >= 2:
                self.emit(f"{NAMES[who]}加入{s.name}的共同操作（{len(workers)}人）", kind='shared_work_join', actor=who,
                          action_id=job.id, station=job.action.target, workers=len(workers))
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
            self.money += self.rules.penalty['discard']
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
        elif k == 'assemble_ground':
            item_id=job.action.expected[1]
            if not self.can_assemble_ground(who,item_id) or self.ground_assembly_signature(who,item_id)!=job.action.expected:
                self.emit('地上物品或手中物品已变化，加入盘中取消',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who);return
            item=self.ground.pop(item_id)
            if self.can_add(item.food,a.hand):
                # The plate stays on its floor cell; a clean plate takes the ingredient's id.
                plate=self.merge_plate(item.food,a.hand);a.hand=None
                self.ground[plate.id]=GroundItem(plate,item.location)
            else:
                a.hand=self.merge_plate(a.hand,item.food)
        elif k == 'load_ground':
            item_id=job.action.expected[1]
            if not self.can_load_ground(who,item_id) or self.ground_plate_signature(who,item_id)!=job.action.expected:
                self.emit('地上锅或手中食材已变化，入锅取消',kind='arrival_conflict',actor=who,action_id=job.id)
                self.stop(who);return
            item=self.ground[item_id]
            item.food.contents,a.hand=a.hand,None
            item.lock=None
        elif k == 'plate_ground':
            item_id = job.action.expected[1]
            if (not self.can_plate_ground(who, item_id)
                    or self.ground_plate_signature(who, item_id) != job.action.expected):
                self.emit('地上锅或手中餐盘已变化，装盘取消', kind='arrival_conflict', actor=who, action_id=job.id)
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
            s.food.chopped = self.rules.chop_work(s.food.ingredient)
            s.food.stage = self.rules.chop[s.food.ingredient]['to']
        elif k == "extinguish":
            s.fire = False
            s.fire_elapsed = 0
            s.heating = False
        elif k == "clear":
            s.food = None
            s.heating = False
            self.money += self.rules.penalty['discard']
        elif k == "discard":
            a.hand = Food(a.hand.plate_id, 'dirty_plate') if a.hand.plate_id else None
            self.money += self.rules.penalty['discard']
        elif k == "serve":
            self.dining.append({'plate': Food(a.hand.plate_id, 'dirty_plate'), 'returns_at': self.time+self.dining_seconds})
            pending = [o for o in self.orders if o["status"] == "pending" and o["dish"]==self.dish(a.hand)]
            self._serve(who, job, a.hand, min(pending, key=lambda x: x["deadline"]) if pending else None)
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
        self.emit(f"{NAMES[who]}完成动作：{job.action.label}", kind="action_done", actor=who, action=job.action.key, action_id=job.id)
        for partner in partners:
            other=self.chefs[partner];other_job=other.job
            other.job=None
            if s.lock==partner:s.lock=None
            getattr(self,'routes',{}).pop(partner,None)
            self.emit(f'{NAMES[partner]}共同完成：{other_job.action.label}',kind='action_done',actor=partner,action=other_job.action.key,action_id=other_job.id)

    def _serve(self, who, job, food, order):
        """Match the waiting order of this dish with the earliest deadline.

        Serving at the deadline itself still counts. A dish burnt past the last
        accepted tier is refused and the order keeps waiting.
        """
        dish = self.dish(food)
        if order is None:
            penalty = self.rules.penalty['wrong_dish']
            self.money += penalty
            self.emit(f"没有等待{self.recipe_name(dish)}的订单；扣 {-penalty} 元", kind='wrong_dish', actor=who,
                      action_id=job.id, dish=dish)
            return
        overcook = self.rules.overcook(food, self.parts(food))
        tier = self.rules.burnt_tier(overcook) if food.stage == 'burnt' else None
        if tier and tier['outcome'] == 'rejected':
            self.emit(f"{order['id']}的顾客拒收糊菜，订单继续等待", kind='dish_rejected', actor=who, action_id=job.id,
                      order_id=order['id'], dish=dish, overcook_game_ms=None if overcook == float('inf') else round(overcook*1000))
            return
        price, adjustment = self.rules.prices[order['dish']], tier['adjustment'] if tier else 0
        order['status'] = 'served'
        self.served += 1
        self.money += price+adjustment
        note = f"（菜品糊了，扣 {-adjustment} 元）" if adjustment else ''
        self.emit(f"{NAMES[who]}完成 {order['id']}，收入 +{price+adjustment} 元{note}", kind='served', actor=who, dish=order['dish'],
                  order_id=order['id'], action_id=job.id, price=price, adjustment=adjustment)

    def _return_plates(self):
        tray = self.stations[self.returns]
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
        penalty = self.rules.penalty['new_fire']
        self.money += penalty
        for who,a in list(self.chefs.items()):
            if a.job and a.job.working and a.job.action.target==key:self.stop(who)
        self.emit(f'{s.name}着火！损失 {-penalty} 元；必须先灭火再使用',
                  kind='fire_spread' if source else 'fire', station=key, source=source)

    def _advance_fire(self, dt):
        interval = self.rules.fire_spread
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
        if sum(s.fire for s in self.stations.values()) >= self.rules.fire_loss:
            self.failure_reason = 'fire_spread'
            for who in self.chefs:
                self.stop(who)
            self.emit('火势失控，本局结束', kind='fire_loss')
            self._end()

    @engine_input
    def advance(self, seconds):
        if seconds < 0 or not math.isfinite(seconds):
            raise ValueError("时间增量无效")
        # Small deterministic substeps preserve thermal transitions and action order.
        while seconds > 1e-9 and not self.ended:
            dt = min(seconds, .05, self.rules.round_limit-self.time)
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
                f.heated += dt*self.rules.work_rate(key,'heat')
                ready, burn, fire = self.rules.heat_thresholds(f.ingredient)
                if f.stage == "cooking" and f.heated >= ready-1e-8:
                    f.stage = "ready"
                    self.emit(f"{s.name}的 {f.id} 熟了！{burn-ready:g}s 后糊锅", kind="ready", station=key, item=f.id)
                if f.stage == "ready" and f.heated >= burn-1e-8:
                    f.stage = "burnt"
                    self.burns += 1
                    self.emit(f"{s.name}糊锅！{fire-burn:g}s 后着火；糊太久上桌会被拒收", kind="burn", station=key, item=f.id)
                if f.stage == "burnt" and f.heated >= fire-1e-8:
                    self.ignite(key)
            self._advance_fire(dt)
            if self.ended:
                break
            for target in {a.job.action.target for a in self.chefs.values()
                           if a.job and a.job.working and a.job.action.kind in ('chop', 'wash')}:
                kind = next(a.job.action.kind for a in self.chefs.values() if a.job and a.job.action.target == target)
                if len(self.work_participants(target, kind)) >= 2:
                    self.shared_overlap[target] = self.shared_overlap.get(target, 0.) + dt
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
                rate = 1
                if job.action.kind in ('chop','wash'):
                    food=self.stations[job.action.target].food
                    job.work=max(0,(self.rules.chop_work(food.ingredient)-food.chopped) if job.action.kind=='chop' else (self.wash_seconds-food.washed))
                    # Shared work: each active chef contributes work_rate * multiplier[n] / n.
                    workers=len(self.work_participants(job.action.target,job.action.kind))
                    rate=self.rules.progress_rate(job.action.target,job.action.kind,max(1,workers))
                used = min(job.work, remaining*rate)
                job.work -= used
                if job.action.kind == "chop":
                    self.stations[job.action.target].food.chopped += used
                elif job.action.kind == 'wash':
                    self.stations[job.action.target].food.washed += used
                if job.action.kind in ('chop','wash'):
                    for participant in self.work_participants(job.action.target,job.action.kind):
                        self.chefs[participant].job.work=job.work
                if job.work <= 1e-8:
                    self.provenance.around_finish(self, who, job, lambda: self._finish(who, job))
            self._after_step(dt)
            # Complete an on-time delivery before expiring the same deadline.
            closing = self.time >= self.rules.round_limit-1e-8
            for o in self.orders:
                # Closing takes priority over a deadline at the same moment.
                if closing and o["deadline"] >= self.rules.round_limit-1e-8:
                    continue
                if o["status"] == "pending" and self.time >= o["deadline"]-1e-8:
                    o["status"] = "expired"
                    penalty = self.rules.penalty['expired_order']
                    self.money += penalty
                    self.emit(f"{o['id']}超时，顾客离开，扣 {-penalty} 元", kind="expired", order_id=o['id'])
            self._goal_notices()
            if closing:
                self._end()

    @engine_input
    def abort(self):
        """End the round early at the session's request (never counts as reaching the goal)."""
        for who in self.chefs:
            if hasattr(self, 'set_manual'):
                self.set_manual(who, 0, 0)
            self.stop(who)
        self.aborted = True
        self._end()

    def _end(self):
        if not self.ended:
            self.ended = True
            for o in self.orders:
                if o['status'] == 'pending':
                    o['status'] = 'unresolved_at_close'
                    self.emit(f"{o['id']}在关店时仍未完成", kind='unresolved_at_close', order_id=o['id'])
            self.emit(self.result(), kind="round_end")

    def timing(self):
        """Rule durations in game seconds for this round (work at rate 1, one worker)."""
        r = self.rules
        heat = next(iter(r.heat), None)
        ready, burn, fire = r.heat_thresholds(heat) if heat else (None, None, None)
        chop = next(iter(r.chop), None)
        return {'wash': r.wash_work, 'dining': r.dining, 'chop': r.chop_work(chop) if chop else None,
                'cook': ready, 'ready_to_burn': None if heat is None else burn-ready,
                'burn_to_fire': None if heat is None else fire-burn, 'handling': r.handling,
                'extinguish': r.extinguish, 'clear': r.clear,
                'walk_same_area': r.same_area, 'walk_cross_area': r.cross_area}

    def goal_status(self):
        """Progress towards the goal as the players may see it.

        Only the target and current money: an upper bound would reveal the
        hidden future orders.
        """
        goal = self.rules.goal
        return {'type': goal['type'], 'target_money': goal['min_money'], 'money': self.money,
                'met_now': self.money >= goal['min_money'], 'judged_at': 'closing'}

    def revenue_ceiling(self):
        """Money now plus every waiting or future order at full price (engine-only knowledge)."""
        return self.money + sum(self.rules.prices[o['dish']] for o in self.orders if o['status'] in ('pending', 'future'))

    def _goal_notices(self):
        if getattr(self, '_goal_unreachable_noted', False):
            return
        if self.revenue_ceiling() < self.rules.goal['min_money']:
            # The bound only falls: serving converts it into money, expiries and penalties remove it.
            self._goal_unreachable_noted = True
            self.emit(f"已无法达成目标金额 {self.rules.goal['min_money']} 元；本局继续至关店", kind='goal_unreachable')

    def won(self):
        return not self.failure_reason and self.money >= self.rules.goal['min_money']

    def result(self):
        label = '火势失控' if self.failure_reason == 'fire_spread' else ("提前退出" if self.aborted else ("目标达成" if self.won() else "未达目标"))
        count = lambda status: sum(o['status'] == status for o in self.orders)
        refused = sum(e.get('kind') == 'dish_rejected' for e in self.events)
        return (f"{label}：净收入 {self.money}/{self.rules.goal['min_money']} 元；完成 {self.served} 单；超时 {count('expired')}；"
                f"拒收 {refused}；关店未完成 {count('unresolved_at_close')}；糊锅 {self.burns}，着火 {self.fires}")

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
                    "missing": self.rules.missing(self.parts(f)) if f.plate_id and self.rules.multi_component else [],
                    "chop_remaining": round(max(0, self.rules.chop_work(f.ingredient)-f.chopped), 2),
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
                      'pot_id': s.pot_id, 'counter': key in self.counters, 'stove': key in self.pots,
                      'type': self.rules.station_types[key]}
            record['fire_spread_in'] = round(max(0,self.rules.fire_spread-s.fire_elapsed),2) if s.fire else None
            record['fire_neighbors'] = self.fire_neighbors(key)
            record['workers']=self.work_participants(key,'chop')+self.work_participants(key,'wash')
            record['scorched'] = s.scorched
            if key in self.pots and s.food:
                h = s.food.heated
                ready, burn, fire = self.rules.heat_thresholds(s.food.ingredient)
                record.update({"ready_in": round(max(0,ready-h),2),
                               "burn_in": round(max(0,burn-h),2),
                               "fire_in": round(max(0,fire-h),2)})
            stations[key] = record
        return {"level": self.c.get("level"), "level_id": self.resolved['level']['id'], "config_hash": self.config_hash,
                "order_seed": self.resolved['seeds']['orders'], "time": round(self.time,2), "round_remaining": round(self.rules.round_limit-self.time,2),
                'tableware': {'total': self.plate_count, 'wash_seconds': self.wash_seconds,
                    'dining_seconds': self.dining_seconds, 'return_capacity': self.rules.return_capacity,
                    'counters': self.counters,
                    'customers': [{'plate_id': d['plate'].id, 'returns_in': round(max(0, d['returns_at']-self.time), 2),
                                   'waiting_for_space': d['returns_at'] <= self.time} for d in self.dining]},
                "chefs": chefs, "stations": stations,
                "ground": [{"location": item.location, "near": self.place(item.location).name,
                            "area": self.place(item.location).area, "food": food(item.food),
                            "used_by": item.lock} for item in self.ground.values()],
                "orders": [{**o, "remaining": round(o["deadline"]-self.time,2)} for o in self.orders if o["status"] != "future"],
                # Reveal only whether more orders will come, not how many.
                "future_orders": int(any(o["status"] == "future" for o in self.orders)),
                'goal_status': self.goal_status(), 'end_policy': self.rules.end_policy,
                # Rules visible to both chefs, from the same frozen configuration the engine runs.
                'menu': [{'id': r, 'name': self.rules.recipe_names[r], 'price': self.rules.prices[r],
                          'components': [{'item': c['item'], 'state': c['state']} for c in self.rules.recipes[r]['components']]}
                         for r in self.rules.menu],
                'assembly': self.rules.multi_component,
                # Every servable dish, including ones no order asks for.
                'dishes': [{'id': r, 'name': self.rules.recipe_names[r], 'price': self.rules.prices[r],
                            'components': [{'item': c['item'], 'state': c['state']} for c in self.rules.recipes[r]['components']]}
                           for r in self.rules.servable],
                # Only present when the ruleset enables it.
                **({'ground_assembly': True} if self.rules.ground_assembly and self.rules.multi_component else {}),
                'scoring': {'penalties': dict(self.rules.penalty),
                            'burnt_service': [dict(t) for t in self.rules.burnt_service]},
                'round_limit': self.rules.round_limit,
                'timing': self.timing(),
                "money": self.money, "served": self.served,
                'fire_safety': {'burning_count': sum(s.fire for s in self.stations.values()),
                                'loss_threshold': self.rules.fire_loss,
                                'spread_seconds': self.rules.fire_spread},
                'failure_reason': self.failure_reason,
                "goals": {"target_money": self.rules.goal['min_money']}}

    def assert_invariants(self):
        foods = ([s.food for s in self.stations.values() if s.food]
                 + [a.hand for a in self.chefs.values() if a.hand]
                 + [item.food for item in self.ground.values()])
        assert len({f.id for f in foods}) == len(foods), "物品重复"
        for item_id, item in self.ground.items():
            assert item_id == item.food.id and self.place(item.location)
            if item.lock:
                j = self.chefs[item.lock].job
                assert j and j.working and j.action.kind in ('pickup', 'plate_ground', 'load_ground','swap_ground_pot','assemble_ground') and j.action.expected[1] == item_id
        for key, s in self.stations.items():
            if key in self.counters:
                pass  # Each counter has exactly one physical item slot.
            elif key == self.rack:
                assert s.food is None or s.food.stage == 'extinguisher'
            elif key in (self.returns, self.sink):
                allowed = ('dirty_plate',) if key == self.returns else ('clean_plate', 'dirty_plate')
                assert s.food is None or s.food.stage in allowed
            elif key not in self.boards + self.pots:
                assert s.food is None, "禁止将食材存入出餐口或虚构窗口"
            if s.lock:
                j = self.chefs[s.lock].job
                assert j and j.working and j.action.target == key
            if s.fire:
                assert self.rules.combustible(key)
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
