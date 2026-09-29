#!/usr/bin/env python3
"""Local spatial whitebox; shares rules, API protections and real Jev scheduling."""
import argparse
import math
from http.server import ThreadingHTTPServer
import threading
import webbrowser
from kitchen import ROOT
from spatial_kitchen import SpatialKitchen
from web_server import GameSession, Handler
from jev import JevClient


STATE_WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'ready': 'cooked'}


def model_candidates(state, actions, per_area):
    """Legal actions listed to the model, without duplicates or interchangeable copies.

    Engine legality is unchanged. Two mechanical rules, the same for every level:
    - "go X" is dropped when another listed action already walks to X;
    - empty counters differ only by place, so per area only the per_area nearest
      (straight-line distance to their access cell) are offered for go/put.
    """
    me = state['chefs']['jeff']['position']
    equipment = state['map']['equipment']
    def distance(key):
        cell = equipment.get(key, {}).get('access') or equipment.get(key, {}).get('cell')
        return math.dist(me, cell) if cell else math.inf
    empty = {}
    for key, station in state['stations'].items():
        if station.get('counter') and not station.get('food') and not station.get('fire'):
            empty.setdefault(station['area'], []).append(key)
    offered = {key for keys in empty.values() for key in sorted(keys, key=lambda k: (distance(k), k))[:per_area]}
    spare = {key for keys in empty.values() for key in keys} - offered
    acted = {a.target for a in actions if a.kind not in ('go', 'throw')}
    return [a for a in actions
            if not (a.kind == 'go' and a.target in acted and a.key != 'go partner')
            and not (a.kind in ('go', 'put_counter') and a.target in spare)]


class SpatialJevClient(JevClient):
    def payload(self, state, actions):
        payload = super().payload(state, actions)
        per_area = self.c.get('ai_empty_counters_per_area', 2)
        listed = {a.key for a in model_candidates(state, actions, per_area)}
        criteria = payload['questions']['next_action']['criteria']
        payload['questions']['next_action']['criteria'] = {k: v for k, v in criteria.items() if k in listed}
        payload['state']['rules']['visibility'] += (
            ' go X is listed only when no other listed action already walks to X. Empty counters differ only in place, '
            f'so for each area the {per_area} nearest empty counters are listed for go and put.')
        kitchen = payload['state']['kitchen']
        if state.get('end_policy') == 'fixed_round':
            # Service rounds have no bad reviews, delivery gate or time bonus; omit the legacy fields.
            for key in ('bad_reviews', 'settlement'):
                kitchen.pop(key, None)
            kitchen['goals'] = {'target_money': state['goals']['target_money']}
            kitchen['scoring'].pop('time_bonus_per_second', None)
        # Cosmetic settings belong in the run log/UI, not repeated model tokens.
        # movement_rule/ground_rule/spawn_rule restate the rules paragraphs below.
        for key in ('presentation','walk_boxes','walk_clearance','chef_separation','movement_rule','ground_rule','spawn_rule'):
            payload['state']['kitchen']['map'].pop(key,None)
        rules = payload['state']['rules']
        geometry = state['map']
        sprint = state['chefs']['jeff']['sprint']
        rules['ground'] = ('Any held item can be put down with drop on the current or an adjacent free floor tile. Each tile holds one item. Actions walk to the destination; placing takes timing.handling seconds. No free tile means no drop. Either chef can use pickup <item_id> to walk to and pick up an item. Taking another item automatically puts the previous item on nearby ground; without free space nothing changes. State and preparation progress are preserved, with no penalty, spoilage or heating. Only discard destroys food and costs money.')
        collision = geometry.get('collision', {})
        contact = (f"Chefs cannot overlap: each keeps {collision['chef_separation']:g} tiles from the other, slides along the other chef when there is room "
                   f"and pushes slowly when pressing on; a sprint can push the other chef at most {collision['sprint_push']:g} tiles. "
                   'A chef chopping or washing is not pushed. ' if 'sprint_push' in collision else '')
        if collision.get('stall_replan_after'):
            contact += (f"A routed chef whose route makes no progress for {collision['stall_replan_after']:g} s re-plans "
                        'from its current position around the other chef. ')
        rules['movement'] = ('This is a top-down grid kitchen. map specifies walls, equipment and reference access positions; position is the live coordinate. Travel follows the shortest navigable polyline by actual distance, going straight when clear and leaving body clearance around walls and equipment. Switching tasks during travel starts a new route from the current position. Stations can be used from the nearest reachable adjacent floor tile; access is only a reference, not the only usable side. '
                             'Walls and equipment block movement; floor items do not. '
                             + contact +
                             'go only moves; drop and pickup move items via the floor.')
        rules['partner'] = ("human is the other chef, controlled by a person. position is the current coordinate; holding is the held item; task and target identify the current action; travel_remaining and work_remaining give remaining time. During travel, location may still name the origin station, so use position for distance. Future human intentions are not known facts.")
        if geometry.get('pass_range'):
            rules['throw'] = (f"throw x y throws toward a floor coordinate; throw partner targets the other chef's current position. Loose raw or chopped ingredients fly up to {geometry['throw_range']:g} tiles; clean plates, dirty plates, plated food, pots and extinguishers can be passed up to {geometry['pass_range']:g} tiles (your throw_range shows the current limit). throw bN or throw <counter_id> can land raw or chopped ingredients (only those) on an empty board or counter; chop only on boards, and take from either surface after landing. A corner counter marked reach=corner is accessed from its explicit diagonal access cell; use take to retrieve items there. incoming_item marks an incoming ingredient. Boards do not accept plates, pots or tools and occupied boards are not overwritten. Out-of-range throws are shortened along the same direction and land on the floor at the range limit. An occupied or reserved floor destination redirects to the nearest free adjacent floor cell; if the adjacent cells are full, the throw is unavailable. The first wall stops a throw at an available tile before it; throws never go around walls. Any held item can be thrown or passed; plates, plated food, pots and extinguishers only to the floor or the other chef, within the pass range. A dropped plate keeps its food, a dropped pot keeps its contents (off-stove pots never heat), and either can be picked up again. Thrown items can pass over equipment. The destination is fixed at release and does not track the other chef. On arrival, the other chef catches only if at the receiving position, empty-handed and not performing work such as taking, placing, chopping or washing. Otherwise the item lands on a reserved adjacent tile, without interrupting work. No available landing tile means no throw. projectiles lists in-flight items and landing times; they cannot be picked up in flight. At release your hands become empty; fetch can take another ingredient immediately, even while the previous item is in flight. There is no once-per-round throw limit. Each throw requires a held item and a legal destination within its range; an occupied or reserved board cannot receive another item. Decide the destination and whether to throw yourself.")
        else:
            rules['throw'] = (f"throw x y throws toward a floor coordinate; throw partner targets the other chef's current position, with a maximum range of {geometry['throw_range']:g} tiles. throw bN or throw <counter_id> can land raw or chopped ingredients on an empty board or counter; chop only on boards, and take from either surface after landing. A corner counter marked reach=corner is accessed from its explicit diagonal access cell; use take to retrieve items there. incoming_item marks an incoming ingredient. Boards do not accept plates, pots or tools and occupied boards are not overwritten. Out-of-range throws are shortened along the same direction. An occupied or reserved floor destination redirects to the nearest free adjacent floor cell; if the adjacent cells are full, the throw is unavailable. The first wall stops a throw at an available tile before it; throws never go around walls. Only raw or chopped, unplated ingredients can be thrown. Clean plates, dirty plates, plated food, pots and extinguishers cannot be thrown; carry them or put them down and pick them up. Throwable ingredients can pass over equipment. The destination is fixed at release and does not track the other chef. On arrival, the other chef catches only if at the receiving position, empty-handed and not performing work such as taking, placing, chopping or washing. Otherwise the item lands on a reserved adjacent tile, without interrupting work. No available landing tile means no throw. projectiles lists in-flight items and landing times; they cannot be picked up in flight. At release your hands become empty; fetch can take another ingredient immediately, even while the previous item is in flight. There is no once-per-round throw limit. Each throw requires a held throwable ingredient and a legal destination; an occupied or reserved board cannot receive another item. Decide the destination and whether to throw yourself.")
        rules['partner_plating'] = ("plate partner: approach the other chef holding a clean or compatible partially assembled plate. Add your prepared ingredient, or transfer cooked/burnt food from your held pot. When the menu has multi-ingredient dishes, you can also transfer all ingredients from your held plate if none duplicate the receiving plate. Food stays on the receiving plate; your pot or emptied plate stays in your hands, or your hand becomes empty after donating a loose ingredient. A chef currently performing work cannot receive, and the transfer does not interrupt that work. Proximity and held items are checked again on arrival and completion; if they change, the transfer is cancelled. Neither chef can directly take an item from the other chef's hands.")
        rules['pot_swap'] = 'swap pot <stove_or_counter_id> or swap pot ground <pot_id> exchanges your held pot with the target pot in place. Contents and cooking progress stay with each original pot. The incoming pot heats only on a stove; the outgoing pot stops heating in your hands. A chopped ingredient starts cooking when its pot reaches a stove. Empty pots do not heat; cooked or burnt food resumes its existing heat progress. A burning stove must be extinguished before exchanging pots. Both chefs have these actions.'
        rules['off_stove_pots'] = 'load ground <pot_id> puts held chopped beef into an empty pot on the floor. load <counter_id> puts held chopped beef into an empty pot on that counter. The ingredient stays inside the pot; your hands become empty. Then pickup or take the pot and return it to a stove to heat it. Off-stove pots never heat food. Raw unchopped beef, vegetables and bread cannot be loaded into a pot. Rules are identical for both chefs and all levels.'
        timing = rules['timing']
        timing.pop('walk_same_area', None)
        timing.pop('walk_cross_area', None)
        timing['walk_cells_per_second'] = geometry['walk_speed']
        timing['throw_cells_per_second'] = geometry['throw_speed']
        timing['throw_windup'] = state['timing']['handling']
        if state.get('assembly'):
            recipes='; '.join(r['id']+' = '+', '.join(f"{c['item']} ({STATE_WORDS.get(c['state'],c['state'])})" for c in r['components'])
                              for r in state.get('dishes',state['menu']))
            ordered=', '.join(r['id'] for r in state['menu'])
            moved=('carried, put down or passed like other plates' if geometry.get('pass_range') else 'carried or put down, not thrown')
            rules['flow']=(f'Dishes, all components on one clean plate in any order: {recipes}. Orders in this round ask for: {ordered}. '
                           'Ingredients reach the listed state by chopping on a board '
                           'and, where the recipe needs cooked food, cooking in a pot on a stove; ingredients listed as chopped or as fetched are never cooked. '
                           f'Recipes and order ingredients are explicit in state. A plate that matches no dish can be {moved}, but not served.')
            rules['assembly']='assemble <counter_id> adds your ingredient to a counter plate, or the counter ingredient to your held plate. assemble <board_id> collects a prepared ingredient directly from that board into your held plate. Beef must be cooked before plating; chopped raw beef cannot be plated. merge <counter_id> transfers all ingredients from the counter plate into your held clean/partial plate if they do not overlap; the empty clean source plate stays on the counter. No plates disappear. plate partner can also add a prepared ingredient or merge a plate into the plate held by the other chef. Each ingredient appears once. plate actions transfer cooked beef from a pot into an empty plate or a partial burger plate without beef, on a counter, in your hand, on the floor (pot), or held by the other chef. Adding vegetables or bread to plated steak turns it into a partial burger until all four ingredients are present. One counter cell holds one object. Pots and plates cannot be stacked.'
            if state.get('ground_assembly'):
                rules['assembly']+=' assemble ground <item_id> does the same with a plate or prepared ingredient on the floor: your ingredient goes onto the floor plate, which stays on its tile, or the floor ingredient goes onto your held plate. pickup <item_id> still exchanges the held item instead.'
        rules['sprint']=f'Both chefs may sprint at {sprint["multiplier"]:g}x movement speed for {sprint["duration"]:g} game seconds, followed by {sprint["cooldown_after"]:g} seconds cooldown. Holding items is allowed; working speed is unchanged. Sprint does not bypass walls. Decide independently whether to request sprint along with next_action. It triggers only if the chosen action is accepted, you are moving, and cooldown is ready. No queued sprint; expiry/cooldown use game time, not response latency.'
        payload['questions']['sprint']={'type':'choice','instructions':'Request a short sprint for this accepted movement action or continuing travel?', 'criteria':{'yes':'Request sprint if moving and available','no':'Do not request sprint'}}
        return payload


class WhiteboxHandler(Handler):
    web_root = ROOT/'whitebox'


def main():
    parser = argparse.ArgumentParser(description='打开可走动的厨房白模')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    game = GameSession(kitchen_factory=SpatialKitchen, client_factory=SpatialJevClient, log_prefix='whitebox')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), WhiteboxHandler)
    except OSError as e:
        raise SystemExit(f'白模启动失败：{e}')
    server.game = game
    threading.Thread(target=game.run, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'厨房白模已就绪：{url}\n点击「开始做菜」才会计时和调用真实 Jev。Ctrl+C 关闭。', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        game.close()
        server.server_close()


if __name__ == '__main__':
    main()
