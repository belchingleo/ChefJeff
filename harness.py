"""Jeff's harness: what the model is shown and which actions it is offered.

Everything that makes up Jeff's input lives here: the rule text, the kitchen as the model sees
it, the listed candidate actions and, per request, recent events and decisions, player messages
and cross-round memory. The clients in jev.py, whitebox_server.py and player_api.py only send
the result. tests/payload_fingerprint.py checks the input byte for byte; a change to it is a
model-prompt change.
"""
from __future__ import annotations
import math
import engine_english
from model_language import english_data, INPUT_LANGUAGE_VERSION
from cooperation_memory import PAST_EPISODES_RULE

# Bump whenever model-visible rule wording changes, so sessions stay comparable.
# v2: factual rules only; no instructions to cooperate with or help the human.
# v3: continuous service rules (money goal, burnt tiers, no bad reviews) where the level uses them.
# v4: plain English input with clear chef names and fewer duplicate choices.
# v5: a plate's missing components name the state they are needed in ("tomato (chopped)").
# v6: memory summaries distinguish historical work/messages from current roles and preferences.
# v7: the human's preference messages say who will do the work ("Chef human will do the cooking.").
# v8: chopping and washing need the hands over the station; two chefs may share it, side by side too.
# v9: boards and ingredient-source tops hold any one object, as counters do; a source with something on top gives no ingredient.
# v10: the objective is as much net revenue as possible, rated in stars (the target, 1.5 and 2 times it).
# v10 also: an ingredient part-way through chopping cannot be taken off its board (Overcooked 2), for both chefs.
# v11: orders arrive as in Overcooked 2 (two from the start, top-up, at most five; an expired order restarts).
# v12: the fire rule is short and in time order: food burns, its stove catches fire at once, then heat, spray, loss.
# v13: level 1's flow says fetch <ingredient> takes that raw ingredient from its source (the key is fetch beef).
# v14: the sink stacks dirty plates and each washed plate goes onto the drying rack; a held pan scoops.
# v15: standing at the sink, take <drying rack> takes the rack's top clean plate where the chef stands (Overcooked 2).
# v15 also: burnt food's burnt time runs while it stays on a stove, burning or not, until it leaves the stove; a fire no
# longer burns the food in a pan (food still cooking cooks on until it is cooked, then waits with cooked food and food
# put on the burning stove, and all of it cooks on once the fire is out); one fire per burning. Food put on a burning
# stove waits whether its pot is put there or the food is put or thrown into its pot (this rule had dropped the old
# "while burning, a stove does not heat", which covered those). The swap rule says a pot can be lifted, put back or
# swapped on a burning stove, as the engine has allowed since 2026-10-21 (it said the stove had to be put out first).
AGENT_RULES_VERSION = "rules-v15"


# How a recipe component's required state reads in model input: "tomato (chopped)".
STATE_WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'ready': 'cooked'}


def _required_states(state):
    """Ingredient -> the state the menu's dishes need it in, when every dish agrees."""
    seen = {}
    for dish in state.get('dishes', state.get('menu', [])):
        for c in dish.get('components', []):
            seen.setdefault(c['item'], set()).add(c.get('state'))
    return {item: states.pop() for item, states in seen.items() if len(states) == 1 and None not in states}


def _with_required_states(value, required):
    """Name the needed state next to each missing component of a partly assembled plate.

    The client reads ``missing`` as ingredient ids; the model gets "tomato (chopped)", so the
    plate it looks at says what still has to happen to each ingredient, as the recipe does."""
    if isinstance(value, list):
        return [_with_required_states(v, required) for v in value]
    if not isinstance(value, dict):
        return value
    out = {k: _with_required_states(v, required) for k, v in value.items()}
    if isinstance(value.get('missing'), list) and value.get('plate_id'):
        out['missing'] = [f"{m} ({STATE_WORDS.get(required[m], required[m])})" if m in required else m
                          for m in value['missing']]
    return out


def model_kitchen(state):
    """The kitchen state as the model sees it: display-only fields for the client are left out."""
    kitchen = {k: v for k, v in state.items() if k != 'items'}
    if 'chefs' in kitchen:
        kitchen['chefs'] = {who: {k: v for k, v in chef.items() if k != 'route_slide'} for who, chef in kitchen['chefs'].items()}
    for key in ('menu', 'dishes'):
        if key in kitchen:
            kitchen[key] = [{k: v for k, v in dish.items() if k != 'plating'} for dish in kitchen[key]]
    if 'map' in kitchen and 'equipment' in kitchen['map']:
        kitchen['map'] = {**kitchen['map'], 'equipment': {key: {k: v for k, v in e.items() if k != 'item'}
                                                           for key, e in kitchen['map']['equipment'].items()}}
    return _with_required_states(kitchen, _required_states(state))


def objective_text(state):
    """Objective and end rules, generated from the round's goal and end policy."""
    goal = state['goal_status']
    one, two, three = goal['star_scores']
    return (f"Earn as much net revenue as you can by closing time, {state['round_limit']:g} game seconds. The round is rated in "
            f"stars by the net revenue at closing: {one} yuan or more earns one star and reaches the target, {two} two stars, "
            f"{three} three stars; below {one} the target is missed. The round always runs until closing and only the net revenue "
            "at closing counts: penalties can take you below a star again. " + arrival_text(state) + " Orders still "
            "waiting at closing carry no penalty. There is no bonus for remaining time.")


def arrival_text(state):
    """How orders arrive: Overcooked 2's flow when the level uses it, else one per interval."""
    flow = state.get('order_flow')
    if not flow:
        return "Orders keep arriving until closing."
    return (f"Orders keep arriving until closing: one every {flow['interval']:g} game seconds, and at once whenever fewer than "
            f"{flow['keep_open']} are waiting, so serving quickly brings the next order sooner; at most {flow['max_open']} wait at a time.")


def score_text(state):
    """Scoring rules from the recipe prices and ruleset penalties of this round."""
    p = state['scoring']['penalties']
    prices = ', '.join(f"{r['id']} {r['price']} yuan" for r in state.get('dishes', state['menu']))
    tiers = []
    for tier in state['scoring']['burnt_service']:
        limit = tier['max_overcook_game_ms']
        span = f"burnt for up to {limit / 1000:g} s" if limit is not None else "burnt for longer"
        tiers.append(f"{span}: accepted at the price {tier['adjustment']:+d} yuan" if tier['outcome'] == 'accepted'
                     else f"{span}: refused with no payment; the dish is lost and the order keeps waiting")
    return (f"Serving a complete plated dish goes to the waiting order of the same dish with the earliest deadline and earns its price ({prices}); "
            "serving exactly at the deadline still counts. A plate can be served when its components are exactly those of one dish in kitchen.dishes; "
            "orders show which dishes customers are waiting for. Unplated food, or a plate that matches no dish, cannot be served. "
            "If any component was burnt, what counts is how long it had been burnt when it left the stove; that time runs while "
            "it stays on a stove, burning or not, and stops when the pan is lifted or the food is plated: " + '; '.join(tiers) + ". "
            f"Serving a dish that no shown order is waiting for: {p['wrong_dish']} yuan. Expired order: {p['expired_order']} yuan"
            + ("; the order stays and its countdown starts again. " if (state.get('order_flow') or {}).get('on_expire') == 'restart' else ". ") +
            f"Fire: {p['new_fire']} yuan per burning workstation. Discarding food or emptying a pot: {p['discard']} yuan. There are no bad reviews.")


def model_candidates(state, actions, per_area, keep_go=False):
    """Legal actions listed to the model, without duplicates or interchangeable copies.

    Engine legality is unchanged. Two mechanical rules, the same for every level:
    - "go X" is dropped when another listed action already walks to X (kept with keep_go, as the intent layer
      does: there walking to X and waiting is not what the other option at X does);
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
            if not (a.kind == 'go' and a.target in acted and a.key != 'go partner' and not keep_go)
            and not (a.kind in ('go', 'put_counter') and a.target in spare)]


# Cosmetic map settings belong in the run log/UI, not repeated model tokens; movement_rule,
# ground_rule and spawn_rule restate the rules paragraphs.
OMITTED_MAP_FIELDS = ('presentation','walk_boxes','walk_clearance','chef_separation','movement_rule','ground_rule','spawn_rule','corner_slide')


def _assembly_flow(state, geometry):
    """The flow paragraph for menus whose dishes are assembled from components on one plate."""
    recipes='; '.join(r['id']+' = '+', '.join(f"{c['item']} ({STATE_WORDS.get(c['state'],c['state'])})" for c in r['components'])
                      for r in state.get('dishes',state['menu']))
    ordered=', '.join(r['id'] for r in state['menu'])
    moved=('carried, put down or passed like other plates' if geometry.get('pass_range') else 'carried or put down, not thrown')
    return (f'Dishes, all components on one clean plate in any order: {recipes}. Orders in this round ask for: {ordered}. '
                   'Ingredients reach the listed state by chopping on a board '
                   'and, where the recipe needs cooked food, cooking in a pot on a stove; ingredients listed as chopped or as fetched are never cooked. '
                   f'Recipes and order ingredients are explicit in state. A plate that matches no dish can be {moved}, but not served.')


def rules(state, spatial=False, per_area=2):
    """Every rule paragraph Jeff reads, in the order the model sees them.

    The spatial kitchen (every listed level) words ground, flow, timing and visibility for its grid
    and adds movement, partner, throwing, plating, pot and sprint rules after the shared ones."""
    discard = -state['scoring']['penalties']['discard']
    pass_range = state.get('map', {}).get('pass_range')
    pot_pass = (f"like plates it can be passed to the other chef or the floor within {pass_range:g} tiles" if pass_range
                else "it cannot be thrown")
    # Levels with a drying rack beside the sink (Overcooked 2's washing station): dirty plates stack in the sink and
    # each washed plate goes onto the rack.
    dryer = next((key for key, st in state['stations'].items() if st.get('type') == 'drying_rack'), None)
    sink_rule = (f'put sink puts it in the sink, where dirty plates stack and stay until washed; wash with empty hands washes '
                 f'the first one in, and each washed plate goes onto the drying rack ({dryer}), the newest on top; take {dryer} '
                 f'collects the top clean plate for plating or storage, and standing at the sink, take {dryer} takes it '
                 f'where you stand.' if dryer else
                 'put sink puts it in an empty sink; wash with empty hands; take sink collects the clean plate for plating or storage.')
    stacking = ('Only the sink (dirty plates) and the drying rack (clean plates) stack plates.' if dryer else 'There is no stacking rack.')
    plate_pass = (f"can be passed to the other chef or the floor within {pass_range:g} tiles (never onto boards or counters); "
                  "a dropped plate keeps its food" if pass_range else "cannot be thrown")
    t = state['timing']
    fire = state['fire_safety']
    geometry = state.get('map', {})
    timing = {**{k: t[k] for k in ("wash", "dining", "chop", "cook", "ready_to_burn", "burn_to_fire",
                                   *(() if spatial else ("walk_same_area", "walk_cross_area")), "handling", "extinguish")},
              "take_put_fetch": t["handling"], "serve": t["handling"]}
    if spatial:
        timing['walk_cells_per_second'] = geometry['walk_speed']
        timing['throw_cells_per_second'] = geometry['throw_speed']
        timing['throw_windup'] = t['handling']
    rules = {
        "role": 'You control chef jeff. Chef human is controlled by a person in the same kitchen. Both chefs can perform the same actions; neither has a fixed role. Choose one next action for your own chef.',
        "objective": objective_text(state),
        "flow": _assembly_flow(state, geometry) if spatial and state.get('assembly') else (
            'fetch <ingredient> takes that raw ingredient from its source -> put bN places it on an empty board -> chop bN prepares it -> take bN picks up the chopped ingredient -> put pN puts it in the pot -> cooking runs automatically. take <counter_id> takes a clean plate -> plate pN transfers cooked food into the held plate -> serve delivers it. Alternatively, take pot pN lifts the whole pot off the stove; plate <counter_id> transfers its food onto a clean plate on that counter, leaving the plated food there and the empty pot in your hands. Return the pot with put pot pN, then collect the plated food. With a clean plate, plate ground <item_id> serves food from a pot on the floor; the empty pot remains there. Food cannot be removed from a pot with bare hands. Actions automatically walk to the target and then work; go only moves.'),
        "vessels": ('In action keys and these rules, pot means any cooking vessel on a stove or held. kitchen.vessels lists each kind of '
                    'vessel in this level, its name and the ingredients it cooks; each stove, held item or floor item that is a vessel '
                    'shows its kind as vessel. An ingredient can be put only into the kind of vessel that cooks it.'),
        "plate_reuse": 'Dirty plates cannot hold food or substitute for clean plates. If no clean plate is available, dirty plates must be washed before plating and serving can continue. Waiting alone does not clean plates. Decide when to wash and how to divide work based on the situation.',
        "tableware": f'Tableware is limited and distributed across counters. Each counter holds one item: a plate, a pot, or an ingredient. {stacking} tableware.counters lists counter IDs; stations, ground, and chefs show actual locations. clean_plate means clean; dirty_plate means dirty; food is plated only when plate_id is nonempty. Use take/put at counters. Removing cooked food requires a container: hold a clean plate and use plate pN at a stove, hold a filled pot and use plate <counter_id> at a clean plate on a counter, or hold a clean plate and use plate <counter_id> at a filled pot on a counter. take pot pN lifts the pot and contents together. An empty pot in hand scoops a loose ingredient it can cook from a board or counter with scoop <station_id>; the pot stays in your hands. A pot occupies your hands; {pot_pass}. Off the stove heating stops; returning it resumes heating. contents is the food inside. An empty stove cannot accept ingredients until its pot is returned. Recycling: take returns collects a dirty plate; {sink_rule} Washing can be interrupted and resumed by either chef with progress preserved. Diners return plates after the dining time. The return station holds one plate; further returns queue. Clean plates, dirty plates and plated food {plate_pass}. They can also be put down and picked up. Plates and pots cannot be destroyed. Discarding plated food leaves a dirty plate; emptying a pot leaves an empty pot, costing {discard} yuan. Decide when to wash, carry plates or lift pots; roles are not fixed.',
        "resources": 'Each chef holds one item. With an item in hand you can only take the extinguisher or pick up a loose raw or chopped ingredient from the floor; the previously held item is then placed on nearby ground when the action completes and can be recovered without a penalty. If no nearby space is available, the swap fails and neither item changes. To take anything else, first put the held item down. Each pot holds one food item. Each board, counter and the top of each ingredient source holds one object of any kind (an ingredient, a plate with or without food, a pot); take, put, plate, assemble, merge, load and swap pot work there as on a counter. Only a raw ingredient that needs chopping can be chopped, and only on a board; chopping requires empty hands and chopped food still occupies the board. An ingredient can be taken off a board before chopping starts or once it is chopped, not part-way through. While something rests on an ingredient source, take gives that object and the source gives no new ingredient; fetch from it returns once its top is clear. Cooking is automatic; no chef needs to stay at the stove. There is no transfer window.',
        "ground": (('Any held item can be put down with drop on the current or an adjacent free floor tile. Each tile holds one item. Actions walk to the destination; placing takes timing.handling seconds. No free tile means no drop. Either chef can use pickup <item_id> to walk to and pick up an item. With an item in hand you can only take the extinguisher or pick up a loose raw or chopped ingredient from the floor; the previous item then goes on nearby ground, and without free space nothing changes. To take anything else, put the held item down first; the person plays by the same rule. State and preparation progress are preserved, with no penalty, spoilage or heating. Only discard destroys food and costs money.') if spatial else
                   'Held items can be put down beside the current station using drop, taking timing.handling seconds, without a penalty or spoilage. ground lists all floor items and locations. Either chef can walk there and use pickup <item_id>; handling time is added to travel. Items retain their state and preparation progress; food on the floor is not heated. Cooked food must remain in a pot or on a plate. Dropping is different from discard at a bin: dropped items remain usable. Decide when to put down or pick up items.'),
        "timing": timing,
        "interrupt": 'continue keeps the current task; another action interrupts it. Chopping progress is preserved. Cooking in a pot does not stop when a chef switches tasks. Decide whether to continue or interrupt.',
        "fire": (f'Cooked food burns timing.ready_to_burn seconds after it is ready, and its stove catches fire at that moment; '
                 'burnt food left on a stove does not set it alight again. '
                 f'A fire heats every combustible workstation in the eight cells around it; next to one fire it ignites after '
                 f'{fire["flammability_seconds"]:g} seconds, more fires add up, and fire_heat (0 to 1) shows how close it is. '
                 'Fire never crosses a floor gap or wall. To put a fire out, take the extinguisher (it fills your hands; a held '
                 f'item goes to the floor) and extinguish: {t["extinguish"]:g} seconds of spraying in total. If you stop early, '
                 'the fire grows back after 2 seconds. A fire never burns food. When a fire reaches a stove, food still cooking '
                 'there cooks on until it is cooked and then waits, and cooked food waits; food put on a burning stove waits too, '
                 'whether its pot is put there or the food is put or thrown into its pot. Food that waits does not cook; once '
                 'the fire is out it cooks on from where it was. Burnt food stays '
                 'burnt and its burnt time keeps running. While burning, a source gives nothing and a board cannot chop, but items there '
                 'can still be taken, put or plated. Burnt food can be served under the burnt-food scoring or emptied at a bin. '
                 f'{fire["loss_threshold"]} workstations burning at once lose the round.'),
        "score": score_text(state),
        "visibility": 'Both chefs see the same kitchen state. All available actions are in criteria; legal does not mean useful. Waiting and continuing are allowed. The program does not choose your strategy.' + ((
            ' go X is listed only when no other listed action already walks to X. Empty counters differ only in place, '
            f'so for each area the {per_area} nearest empty counters are listed for go and put.') if spatial else '')
    }
    if not spatial:
        return rules
    sprint = state['chefs']['jeff']['sprint']
    collision = geometry.get('collision', {})
    contact = (f"Chefs cannot overlap: each keeps {collision['chef_separation']:g} tiles from the other, slides along the other chef when there is room "
               f"and pushes slowly when pressing on; walking never pushes a chef who is chopping or washing. A sprint into the other chef knocks them "
               f"back up to {collision['sprint_push']:g} tiles and stops their work (its progress is kept); when both sprint into each other, both bounce. "
               'A chef pinned against a wall is not knocked and keeps working. ' if 'sprint_push' in collision else '')
    if collision.get('stall_replan_after'):
        contact += (f"A routed chef whose route makes no progress for {collision['stall_replan_after']:g} s re-plans "
                    'from its current position around the other chef. ')
    rules['movement'] = ('This is a top-down grid kitchen. map specifies walls, equipment and reference access positions; position is the live coordinate. Travel follows the shortest navigable polyline by actual distance, going straight when clear and leaving body clearance around walls and equipment. Switching tasks during travel starts a new route from the current position. Stations can be used from the nearest reachable adjacent floor tile; access is only a reference, not the only usable side. '
                         'Walls and equipment block movement; floor items do not. '
                         'Chopping and washing need the hands over the station: within half a tile of the centre of one of its sides; '
                         'chop and wash walk there. Both chefs can chop on the same board or wash at the same sink together, from different sides '
                         'or side by side on one side, and their progress adds up. '
                         + contact +
                         'go only moves; drop and pickup move items via the floor.')
    rules['partner'] = ("human is the other chef, controlled by a person. position is the current coordinate; holding is the held item; task and target identify the current action; travel_remaining and work_remaining give remaining time. During travel, location may still name the origin station, so use position for distance. Future human intentions are not known facts.")
    reach = (f"Loose raw or chopped ingredients fly up to {geometry['throw_range']:g} tiles; clean plates, dirty plates, plated food and pots "
             f"up to {geometry['pass_range']:g} tiles (your throw_range shows the current limit); the extinguisher cannot be thrown. "
             if geometry.get('pass_range') else
             f"Only raw or chopped, unplated ingredients can be thrown, up to {geometry['throw_range']:g} tiles; carry or put down plates, "
             "plated food, pots and the extinguisher. ")
    rules['throw'] = ("throw partner throws toward the other chef's current position; throw <direction> (up, down, left, right, up-left, up-right, "
                      "down-left, down-right) throws to full range that way. These are the throws the person can make too. " + reach +
                      "Each throw option names where the item would come down. Throws pass over equipment; the first wall stops them. "
                      "An empty-handed chef who is walking or standing close to the path catches the item; a chef who is working or holding "
                      "something is not interrupted and it lands beside them. A raw or chopped ingredient that comes down on an empty board, "
                      "counter or ingredient-source top rests there (chop only on boards; take from any), and one that comes down in an empty pan on a stove that cooks it "
                      "goes in and starts heating. Anything else lands on the nearest free floor tile; with none free the throw is unavailable. "
                      "incoming_item marks a station an item is flying to. projectiles lists in-flight items and landing times; they cannot be "
                      "picked up in flight. At release your hands become empty. Decide whether and where to throw yourself.")
    rules['partner_plating'] = ("plate partner: approach the other chef holding a clean or compatible partially assembled plate. Add your prepared ingredient, or transfer cooked/burnt food from your held pot. When the menu has multi-ingredient dishes, you can also transfer all ingredients from your held plate if none duplicate the receiving plate. Food stays on the receiving plate; your pot or emptied plate stays in your hands, or your hand becomes empty after donating a loose ingredient. A chef currently performing work cannot receive, and the transfer does not interrupt that work. Proximity and held items are checked again on arrival and completion; if they change, the transfer is cancelled. Neither chef can directly take an item from the other chef's hands.")
    rules['pot_swap'] = 'swap pot <stove_or_counter_id> or swap pot ground <pot_id> exchanges your held pot with the target pot in place. Contents and cooking progress stay with each original pot. The incoming pot heats only on a stove; the outgoing pot stops heating in your hands. A chopped ingredient starts cooking when its pot reaches a stove. Empty pots do not heat; cooked or burnt food resumes its existing heat progress. A pot can be lifted, put back or swapped on a burning stove. Both chefs have these actions.'
    rules['off_stove_pots'] = 'load ground <pot_id> puts held food into an empty pot on the floor. load <counter_id> puts held food into an empty pot on that counter. The ingredient stays inside the pot; your hands become empty. Then pickup or take the pot and return it to a stove to heat it. Off-stove pots never heat food. Only food in the state that kitchen.vessels lists for that kind of vessel can be loaded. Rules are identical for both chefs and all levels.'
    if state.get('assembly'):
        rules['assembly']='assemble <counter_id> adds your ingredient to a counter plate, or the counter ingredient to your held plate. assemble <board_id> collects a prepared ingredient directly from that board into your held plate. Beef must be cooked before plating; chopped raw beef cannot be plated. merge <counter_id> transfers all ingredients from the counter plate into your held clean/partial plate if they do not overlap; the empty clean source plate stays on the counter. No plates disappear. plate partner can also add a prepared ingredient or merge a plate into the plate held by the other chef. Each ingredient appears once. plate actions transfer cooked beef from a pot into an empty plate or a partial burger plate without beef, on a counter, in your hand, on the floor (pot), or held by the other chef. Adding vegetables or bread to plated steak turns it into a partial burger until all four ingredients are present. One counter cell holds one object. Pots and plates cannot be stacked.'
        if state.get('ground_assembly'):
            rules['assembly']+=' assemble ground <item_id> does the same with a plate or prepared ingredient on the floor: your ingredient goes onto the floor plate, which stays on its tile, or the floor ingredient goes onto your held plate. pickup <item_id> still exchanges the held item instead.'
    cooldown=f', then {sprint["cooldown_after"]:g} seconds cooldown' if sprint['cooldown_after'] else '; a new sprint can start as soon as one ends'
    rules['sprint']=f'Both chefs may sprint: movement speed starts at {sprint["multiplier"]:g}x and eases back to walking over {sprint["duration"]:g} game seconds{cooldown}. Holding items is allowed; working speed is unchanged. Sprint does not bypass walls. Decide independently whether to request sprint along with next_action. It triggers only if the chosen action is accepted, you are moving, and cooldown is ready. No queued sprint; expiry/cooldown use game time, not response latency.'
    return rules


def payload(state, actions, config, spatial=False):
    """Jeff's request before the per-request additions of compose(): kitchen, rules and questions."""
    per_area = config.get('ai_empty_counters_per_area', 2)
    kitchen = model_kitchen(state)
    if spatial:
        kitchen['map'] = {k: v for k, v in kitchen['map'].items() if k not in OMITTED_MAP_FIELDS}
    import one_press
    listed = model_candidates(state, actions, per_area) if spatial else actions
    if any(a.kind in one_press.PUT_KINDS for a in listed) and (state['chefs']['jeff'].get('holding') is not None):
        places = {a.key: engine_english.label(a) for a in listed if a.kind in one_press.PLACES}
        if not places:     # nowhere to put the held item first: no one-press action
            listed = [a for a in listed if a.kind not in one_press.PUT_KINDS]
    else:
        places = {}
    questions = {"next_action": {
        "type": "choice",
        "instructions": "Given the whole kitchen situation, which action should chef jeff take now? The goals and score are shared by both chefs. The state includes both chefs' current actions, occupied equipment, order deadlines, and burning/fire risks. Choose one action now; an ongoing task may be continued or interrupted.",
        "criteria": {a.key: engine_english.label(a) for a in listed}
    }}
    if spatial:
        questions['sprint'] = {'type':'choice','instructions':'Request a short sprint for this accepted movement action or continuing travel?', 'criteria':{'yes':'Request sprint if moving and available','no':'Do not request sprint'}}
    if places and any(a.kind in one_press.PUT_KINDS for a in listed):
        questions[one_press.PUT_WHERE] = {
            'type': 'choice', 'criteria': places,
            'instructions': 'Only if next_action is a "put then ..." or "wash from" action: where the held item goes first. '
                            'Otherwise it is not used.'}
    return english_data({"model": config["model"],
                         "state": {"kitchen": kitchen, "rules": rules(state, spatial, per_area)},
                         "questions": questions})


PLAYER_COMMUNICATION_RULE = (
    'These are explicit messages from the human chef in this round. The latest preference replaces earlier preferences. '
    'A preference expresses what the human would like to do, not a fixed role, promise, or compulsory assignment for either chef. '
    'Decide how to coordinate using the current orders, risks and both chefs. A correction is the human opinion that something '
    'was wrong; its context identifies what was happening when sent, not proof of a rule violation or an exact explanation. '
    'Reassess recent and current actions against the rules and actual state. Do not assume the human has identified the right solution. '
    'Use message IDs and times to distinguish earlier feedback from a newly sent correction; repeated visibility does not mean the player corrected you again. '
    'Messages do not force an action or stop ongoing work. They expire at round end.')
CONTINUITY_RULE = (
    'recent_decisions lists recent choices and whether they were accepted; accepted does not mean completed. '
    'recent_events records actual actions and outcomes. Use them to check for repeatedly picking up and putting down the same item, '
    'swapping between ingredients, or fetching without free space. Swapping changes locations, not preparation progress; '
    'fetching more raw meat does not advance prepared ingredients. Existing food keeps its preparation state until someone acts on it. '
    'If the situation is unchanged, assess what repeating an action would accomplish. You may continue, wait, or choose another action; the choice is yours.')
NO_MEMORY = object()


# Engine action kinds that do each kind of work (engine semantics only, the same on every level).
WORK_KINDS = {
    'fetch': ('fetch',),
    'chop': ('chop',),
    'cook': ('put_pot', 'load_counter', 'scoop_counter', 'load_ground'),
    'plate': ('assemble', 'assemble_ground', 'plate_pot', 'plate_counter', 'plate_from_counter', 'plate_ground',
              'plate_partner'),
    'take_plate': ('take_plate', 'take_sink'),
    'serve': ('serve',),
    'collect_plates': ('take_return',),
    'wash_plates': ('wash',),
}


def for_model(payload):
    """The request as a model is sent it: without the version tags of the parts it was built from (state.*_version,
    rules_version) and of its wording (input_language). They are bookkeeping, not facts about the kitchen; the round's
    record keeps the payload with them, and research replay compares against that (2026-11-20)."""
    state = payload.get('state') if isinstance(payload, dict) else None
    if not isinstance(state, dict):
        return payload
    return {**payload, 'state': {key: value for key, value in state.items()
                                 if not (key.endswith('_version') or key == 'input_language')}}


def choices(answers, questions):
    """A decision API's choices for these questions: {question: choice}, leaving out any that are not choice answers."""
    answers = answers if isinstance(answers, dict) else {}
    return {q: answers[q]['choice'] for q in questions
            if isinstance(answers.get(q), dict) and answers[q].get('type') == 'choice' and 'choice' in answers[q]}


def choice_questions(payload):
    """Every extra choice question a request asks besides next_action and sprint: put_where (one_press.py), if asked."""
    import one_press
    return [one_press.PUT_WHERE] if one_press.PUT_WHERE in payload['questions'] else []


def choice_answer(answers, payload):
    """put_where (an offered key, else None) when the request asked it; {} otherwise."""
    import one_press
    answers = answers if isinstance(answers, dict) else {}
    out = {}
    if one_press.PUT_WHERE in payload['questions']:
        value = answers.get(one_press.PUT_WHERE)
        out[one_press.PUT_WHERE] = value if isinstance(value, str) and value in payload['questions'][one_press.PUT_WHERE]['criteria'] else None
    return out


PUT_WHERE_CHAT_RULE = ' When questions.put_where is present, also include "put_where": "<key>", one key of its criteria.'


def compose(payload, kitchen, recent_decisions, communication, memory=NO_MEMORY, one_press=None, undo=None,
            reach=False, names=False, split=False, burn=False,
            serve_note=False, steps=False, clear=False):
    """Add what one request needs beyond the snapshot; research replay rebuilds requests here too.

    undo is the undo_note state when that switch is on (its notes are added by jev.compose_payload, undo-note-v4), else None.
    reach is whether the reach_note switch is on: on a split floor, which stations each chef can reach.
    split is whether the split_floor switch is on: on a split floor where no dish can be made by one chef alone,
    which operations the menu needs are only on each side (split_floor.py); it comes right after rules.reach.
    burn is whether the burn_note switch is on: options on a stove whose food is cooked say when it burns (burn_note.py).
    serve_note: the serve option and options that pick up a finished dish name the waiting order it goes to
    (option_notes.py). steps: state.step_check, whether each kind of step the
    waiting orders need is possible now and what stands in the way (step_check.py). clear: item ids and "the held
    item" say what the thing is (clear_names.py); it runs again after the links table.
    names is whether the food_names switch is on: the request's food names are marked (jev.compose_payload) and
    the marks come off here, after translation.
    """
    # HTTP choices are stateless: return actual outcomes, not just today's snapshot.
    # Walking starts/stops are already in each chef's position and move_direction; as events
    # they only push outcomes out of the window. The run log keeps them.
    shown = [e for e in kitchen.events if e.get('kind') not in ('manual_move', 'position_resync')]
    # The engine_english trial (engine_english.py): the events the engine wrote in English too, in its English.
    shown = engine_english.events(kitchen, shown)
    payload['state']['recent_events'] = shown[-20:]
    payload['state']['recent_decisions'] = list(recent_decisions)
    if communication is not None:
        payload['state']['player_communication'] = communication
        payload['state']['rules']['player_communication'] = PLAYER_COMMUNICATION_RULE
    if memory is not NO_MEMORY:
        payload['state']['past_episodes'] = memory
        payload['state']['rules']['past_episodes'] = PAST_EPISODES_RULE
    payload['state']['rules']['continuity'] = CONTINUITY_RULE
    if one_press:
        import one_press as presses
        payload['state']['rules']['one_press'] = presses.RULE
    payload = english_data(payload)
    if names:
        import food_names
        payload = food_names.apply(payload)
    if engine_english.ON.get():
        engine_english.apply(payload, kitchen)
    payload['state']['input_language'] = INPUT_LANGUAGE_VERSION
    payload['state']['rules_version'] = AGENT_RULES_VERSION
    if one_press:
        payload['state']['one_press_version'] = presses.VERSION
    if reach:
        import reach_note
        reach_note.apply(payload, kitchen)
    if split:
        import split_floor
        split_floor.apply(payload, kitchen)
    if burn:
        import burn_note
        burn_note.apply(payload, kitchen)
    if serve_note:
        import option_notes
        option_notes.apply_serve(payload)
    if steps:
        import step_check
        step_check.apply(payload, kitchen)
    if clear:
        import clear_names
        clear_names.apply(payload, kitchen)
    return payload
