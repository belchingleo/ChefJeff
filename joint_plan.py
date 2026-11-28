"""Shared order focus and bilateral commitment (the joint_plan trial, features.json, joint-plan-v1).

Unlike the earlier solo plan modes (plan-v2, rolling-v3), a joint plan anchors both chefs on a live pending order
with a complementary division derived purely from the recipe's components. Its progress is computed objectively from
the kitchen state regardless of which chef did each step, it suspends automatically (and disappears from Jeff's input)
during any fire or stove within BURN_SUSPEND_SECONDS of burning, and both chefs can propose, accept, decline or
release it. Active commitments keep ask_ahead enabled without asking extra plan questions on ordinary turns.
"""
from __future__ import annotations

from copy import deepcopy

from model_language import english_text

VERSION = 'joint-plan-v1'
PROPOSAL_Q = 'joint_proposal'
REPLY_Q = 'joint_reply'
STATUS_Q = 'joint_status'
QUESTIONS = (PROPOSAL_Q, REPLY_Q, STATUS_Q)
DIVISIONS = ('shared', 'jeff_cook', 'jeff_prep')

PROPOSAL_TTL = 8.0
PROPOSAL_COOLDOWN = 8.0
BURN_SUSPEND_SECONDS = 8.0
STALL_RECHECK_SECONDS = 12.0
RECHECK_INTERVAL = 10.0

STATE_WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'ready': 'cooked'}

RULE = (
    'joint_plan records a shared order focus between you and the other chef, derived from the current kitchen state. '
    'status is proposed (waiting for confirmation) or active (confirmed by both). '
    'progress lists each recipe component objectively from the kitchen regardless of which chef worked on it. '
    'The focus ends when the order is served or expires, or when either chef releases it; during a fire or a stove '
    'within 8 s of burning it is suspended and omitted. It does not change legal actions or override urgent risks. '
    'When questions.joint_proposal, questions.joint_reply or questions.joint_status is present, choose one key from '
    'its criteria; the other chef sees your proposal, acceptance, decline or release.'
)


def chat_rule_for(question):
    """Extra sentence for OpenAI-compatible chat system prompts when a joint_plan question is present."""
    return f' When questions.{question} is present, also include "{question}": "<key>", one key of its criteria.'


def start():
    """Fresh per-round joint_plan state (JSON-serializable for replay and logging)."""
    return {
        'status': 'none',
        'seq': 0,
        'id': None,
        'proposer': None,
        'order_id': None,
        'dish': None,
        'order_deadline': None,
        'division': 'shared',
        'explicit_division': False,
        'created_t': None,
        'accepted_t': None,
        'accepted_by': None,
        'suspended': False,
        'suspend_reason': None,
        'cooldown_until': 0.0,
        'progress_sig': None,
        'last_progress_t': 0.0,
        'last_recheck_t': 0.0,
        'recheck': False,
        'event_cursor': 0,
        'notice_seq': 0,
        'last_notice': None,
    }


def _pending_orders(kitchen):
    return sorted(
        (o for o in kitchen.orders if o.get('status') == 'pending'),
        key=lambda o: (o.get('deadline', float('inf')), o.get('id', '')),
    )


def _find_pending(kitchen, order_id):
    return next((o for o in kitchen.orders if o.get('status') == 'pending' and o.get('id') == order_id), None)


def _dish_en(kitchen, dish_id):
    return english_text(kitchen.rules.recipe_names.get(dish_id, dish_id))


def _item_en(kitchen, item_id):
    return english_text(kitchen.rules.item_names.get(item_id, item_id))


def _place_en(kitchen, place):
    if place in kitchen.stations:
        return english_text(kitchen.stations[place].name)
    if place == 'jeff':
        return 'your hand'
    if place == 'human':
        return "other chef's hand"
    if place == 'air':
        return 'in the air'
    return 'floor'


def recipe_parts(kitchen, dish_id):
    """(heated_items, unheated_items) for a recipe, preserving recipe order."""
    recipe = kitchen.rules.recipes.get(dish_id) or {}
    components = recipe.get('components') or []
    heated = [c['item'] for c in components if c.get('state') == 'ready']
    unheated = [c['item'] for c in components if c.get('state') != 'ready']
    return heated, unheated


def available_divisions(kitchen, dish_id):
    """Complementary divisions that make structural sense for this dish."""
    heated, unheated = recipe_parts(kitchen, dish_id)
    if heated and unheated:
        return ('jeff_cook', 'jeff_prep', 'shared')
    if heated and any(item in kitchen.rules.chop for item in heated):
        return ('jeff_cook', 'jeff_prep', 'shared')
    return ('shared',)


def division_text(kitchen, dish_id, division):
    """Factual English (jeff_part, other_chef_part) strings for this dish and division."""
    heated, unheated = recipe_parts(kitchen, dish_id)
    heated_names = ', '.join(_item_en(kitchen, i) for i in heated)
    unheated_names = ', '.join(_item_en(kitchen, i) for i in unheated)
    if division == 'jeff_cook':
        if heated and unheated:
            return (f'{heated_names} and stove', f'{unheated_names}, plating and serving')
        if heated:
            return (f'cooking {heated_names}, plating and serving', f'fetching and chopping {heated_names}')
    if division == 'jeff_prep':
        if heated and unheated:
            return (f'{unheated_names}, plating and serving', f'{heated_names} and stove')
        if heated:
            return (f'fetching and chopping {heated_names}', f'cooking {heated_names}, plating and serving')
    return ('any remaining step', 'any remaining step')


def crisis_reason(kitchen):
    """'fire' if any station burns, 'burn_risk' if any stove food is within BURN_SUSPEND_SECONDS of burning, else None."""
    if any(s.fire for s in kitchen.stations.values()):
        return 'fire'
    for sid in getattr(kitchen, 'pots', ()):
        s = kitchen.stations.get(sid)
        food = s.food if s is not None else None
        if food is not None and food.stage in ('cooking', 'ready') and food.ingredient in kitchen.rules.heat:
            _, burn, _ = kitchen.rules.heat_thresholds(food.ingredient)
            if burn - food.heated <= BURN_SUSPEND_SECONDS:
                return 'burn_risk'
    return None


def _all_foods(kitchen):
    """Yield (place_key, food_object, on_stove_sid_or_None) for every live food/container in the kitchen."""
    for sid, s in kitchen.stations.items():
        if s.food is not None:
            on_stove = sid if sid in getattr(kitchen, 'pots', ()) else None
            yield sid, s.food, on_stove
            if s.food.stage == 'pot' and s.food.contents is not None:
                yield sid, s.food.contents, None
    for who, chef in kitchen.chefs.items():
        if chef.hand is not None:
            yield who, chef.hand, None
            if chef.hand.stage == 'pot' and chef.hand.contents is not None:
                yield who, chef.hand.contents, None
    for g in getattr(kitchen, 'ground', {}).values():
        if g.food is not None:
            yield 'floor', g.food, None
            if g.food.stage == 'pot' and g.food.contents is not None:
                yield 'floor', g.food.contents, None
    for p in getattr(kitchen, 'projectiles', {}).values():
        food = p.get('food')
        if food is not None:
            yield 'air', food, None
            if food.stage == 'pot' and food.contents is not None:
                yield 'air', food.contents, None


def order_progress(kitchen, order):
    """Objective, deterministic component progress for a pending order across the whole kitchen."""
    dish_id = order['dish']
    recipe = kitchen.rules.recipes.get(dish_id) or {}
    components = recipe.get('components') or []
    required_set = {c['item'] for c in components}
    foods = list(_all_foods(kitchen))

    best_plate = None
    best_rank = None
    for place, food, _ in foods:
        if not food.plate_id or food.stage == 'burnt':
            continue
        is_complete = kitchen.dish(food) == dish_id
        parts = set(kitchen.parts(food)) if food.components or food.ingredient else set()
        if not is_complete and (not parts or not parts <= required_set):
            continue
        rank = (1 if is_complete else 0, len(parts), 0 if place in ('floor', 'air') else 1)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_plate = (place, food, parts, is_complete)

    on_plate = best_plate[2] if best_plate else set()
    plate_place = _place_en(kitchen, best_plate[0]) if best_plate else None
    if best_plate and best_plate[3]:
        plate_status = f'complete {_dish_en(kitchen, dish_id)} ready to serve ({plate_place})'
    elif best_plate:
        present = ', '.join(_item_en(kitchen, i) for i in sorted(on_plate))
        plate_status = f'partial plate with {present} ({plate_place})'
    else:
        plate_status = 'no plate started yet'

    rows = []
    for comp in components:
        item, need = comp['item'], comp['state']
        name_zh = kitchen.rules.item_names.get(item, item)
        name_en = _item_en(kitchen, item)
        if item in on_plate:
            rows.append({'item': item, 'name': name_zh, 'name_en': name_en, 'need': need,
                         'status': 'on_plate', 'detail': f'on plate ({plate_place})'})
            continue
        best = None  # (priority, status, detail)
        for place, food, on_stove in foods:
            if food.plate_id or food.stage in ('pot', 'clean_plate', 'dirty_plate', 'extinguisher', 'burnt'):
                continue
            if food.ingredient != item:
                continue
            where = _place_en(kitchen, place)
            if food.stage == need:
                cand = (5, 'ready', f'{STATE_WORDS.get(need, need)} ({where})')
            elif need == 'ready' and food.stage == 'cooking' and item in kitchen.rules.heat:
                ready_t, _, _ = kitchen.rules.heat_thresholds(item)
                left = max(0.0, ready_t - food.heated)
                note = f'cooking ({where}, {left:.1f} s left)' if on_stove else f'partially cooked ({where}, {left:.1f} s left on stove)'
                cand = (4, 'working', note)
            elif need == 'ready' and food.stage == 'chopped':
                cand = (3, 'in_progress', f'chopped ({where}, needs stove)')
            elif food.stage == 'raw' and food.chopped > 0 and item in kitchen.rules.chop:
                left = max(0.0, kitchen.rules.chop_work(item) - food.chopped)
                cand = (2, 'working', f'chopping ({where}, {left:.1f} s left)')
            elif food.stage == 'raw':
                cand = (1, 'fetched', f'as fetched ({where})')
            else:
                continue
            if best is None or cand[0] > best[0]:
                best = cand
        if best is None:
            rows.append({'item': item, 'name': name_zh, 'name_en': name_en, 'need': need,
                         'status': 'needed', 'detail': 'needed'})
        else:
            rows.append({'item': item, 'name': name_zh, 'name_en': name_en, 'need': need,
                         'status': best[1], 'detail': best[2]})
    return {'components': rows, 'plate_status': plate_status, 'sig': [r['status'] for r in rows]}


def _set_notice(plan, kitchen, kind, actor, order_id=None, dish=None, division=None):
    plan['notice_seq'] = int(plan.get('notice_seq', 0)) + 1
    plan['last_notice'] = {
        'id': plan['notice_seq'],
        't': round(kitchen.time, 2),
        'kind': kind,
        'actor': actor,
        'order_id': order_id,
        'dish': dish,
        'dish_name': kitchen.rules.recipe_names.get(dish, dish) if dish else None,
        'division': division,
    }


def _clear(plan, kitchen, kind=None, actor='engine', cooldown=False):
    order_id, dish, division = plan.get('order_id'), plan.get('dish'), plan.get('division')
    if kind:
        _set_notice(plan, kitchen, kind, actor, order_id, dish, division)
    plan.update(
        status='none', id=None, proposer=None, order_id=None, dish=None, order_deadline=None,
        division='shared', explicit_division=False, created_t=None, accepted_t=None, accepted_by=None,
        suspended=False, suspend_reason=None, progress_sig=None, recheck=False,
        event_cursor=len(kitchen.events),
    )
    if cooldown:
        plan['cooldown_until'] = round(kitchen.time + PROPOSAL_COOLDOWN, 2)


def _human_matches_division(kitchen, plan, event):
    """Whether a human action event starts or completes work aligned with their side of Jeff's proposal."""
    if event.get('actor') != 'human' or event.get('kind') not in ('action_start', 'action_done'):
        return False
    action = str(event.get('action') or '')
    if not action or action in ('wait', 'continue', 'stop') or action.startswith(('go ', 'drop', 'discard')):
        return False
    dish_id = plan.get('dish')
    heated, unheated = recipe_parts(kitchen, dish_id)
    division = plan.get('division', 'shared')
    if division == 'jeff_cook':
        items = set(unheated) if unheated else set(heated)
        kinds = ('assemble', 'merge', 'plate', 'serve', 'take_plate', 'take_sink') if unheated else ('chop',)
    elif division == 'jeff_prep':
        items = set(heated) if heated else set(unheated)
        kinds = ('put_pot', 'scoop', 'lift_pot') if unheated else ('put_pot', 'plate', 'serve')
    else:
        items = set(heated) | set(unheated)
        kinds = ('chop', 'put_pot', 'assemble', 'merge', 'plate', 'serve')
    for item in items:
        if action == f'fetch {item}':
            return True
    if any(action.startswith(prefix) for prefix in ('plate ', 'assemble ', 'merge ', 'serve', 'scoop ')):
        if any(k in ('assemble', 'plate', 'serve', 'scoop') for k in kinds):
            return True
    if action.startswith('put ') and len(action.split()) == 2:
        target = action.split()[1]
        if target in getattr(kitchen, 'pots', ()) and 'put_pot' in kinds:
            return True
    if action.startswith('chop ') and len(action.split()) == 2:
        sid = action.split()[1]
        food = kitchen.stations[sid].food if sid in kitchen.stations else None
        if food is not None and food.ingredient in items:
            return True
    hand = kitchen.chefs['human'].hand
    if hand is not None and hand.ingredient in items:
        return True
    return False


def sync(plan, kitchen):
    """Advance commitment lifecycle from current engine state. Returns a list of transition logs."""
    if plan is None:
        return []
    logs = []
    status = plan['status']
    if status == 'none':
        return logs

    order = _find_pending(kitchen, plan['order_id'])
    if order is None:
        served = any(o.get('id') == plan['order_id'] and o.get('status') == 'served' for o in kitchen.orders)
        kind = 'completed' if served else 'order_gone'
        logs.append({'transition': kind, 'id': plan['id'], 'order_id': plan['order_id'], 't': round(kitchen.time, 2)})
        _clear(plan, kitchen, kind=kind, actor='engine', cooldown=False)
        return logs

    if plan.get('order_deadline') is not None and abs(order.get('deadline', 0.0) - plan['order_deadline']) > 0.5:
        logs.append({'transition': 'expired', 'id': plan['id'], 'order_id': plan['order_id'], 't': round(kitchen.time, 2)})
        _clear(plan, kitchen, kind='expired', actor='engine', cooldown=False)
        return logs

    if status == 'proposed':
        if plan['proposer'] == 'jeff':
            for event in kitchen.events[plan.get('event_cursor', 0):]:
                if _human_matches_division(kitchen, plan, event):
                    plan['status'] = 'active'
                    plan['accepted_t'] = round(kitchen.time, 2)
                    plan['accepted_by'] = 'human_implicit'
                    progress = order_progress(kitchen, order)
                    plan['progress_sig'] = progress['sig']
                    plan['last_progress_t'] = round(kitchen.time, 2)
                    plan['last_recheck_t'] = round(kitchen.time, 2)
                    _set_notice(plan, kitchen, 'accepted_implicit', 'human', plan['order_id'], plan['dish'], plan['division'])
                    logs.append({'transition': 'accepted_implicit', 'id': plan['id'], 'order_id': plan['order_id'],
                                 'division': plan['division'], 't': round(kitchen.time, 2)})
                    break
            plan['event_cursor'] = len(kitchen.events)
        if plan['status'] == 'proposed' and plan.get('created_t') is not None and kitchen.time - plan['created_t'] >= PROPOSAL_TTL:
            logs.append({'transition': 'proposal_expired', 'id': plan['id'], 'order_id': plan['order_id'],
                         'proposer': plan['proposer'], 't': round(kitchen.time, 2)})
            _clear(plan, kitchen, kind='proposal_expired', actor='engine', cooldown=plan['proposer'] == 'jeff')
            return logs

    if plan['status'] == 'active':
        progress = order_progress(kitchen, order)
        if progress['sig'] != plan.get('progress_sig'):
            plan['progress_sig'] = progress['sig']
            plan['last_progress_t'] = round(kitchen.time, 2)
        reason = crisis_reason(kitchen)
        was_suspended = bool(plan.get('suspended'))
        plan['suspended'] = reason is not None
        plan['suspend_reason'] = reason
        if plan['suspended'] and not was_suspended:
            _set_notice(plan, kitchen, 'suspended', 'engine', plan['order_id'], plan['dish'], plan['division'])
            logs.append({'transition': 'suspended', 'id': plan['id'], 'reason': reason, 't': round(kitchen.time, 2)})
        elif not plan['suspended'] and was_suspended:
            _set_notice(plan, kitchen, 'resumed', 'engine', plan['order_id'], plan['dish'], plan['division'])
            logs.append({'transition': 'resumed', 'id': plan['id'], 't': round(kitchen.time, 2)})
    return logs


def human_action(plan, kitchen, action, order_id=None, division=None):
    """Apply a human UI command ('focus', 'accept', 'decline', 'release'). Returns (ok, error_or_None, log_or_None)."""
    if plan is None:
        return False, '当前对局未启用共享订单聚焦。', None
    sync(plan, kitchen)
    if action == 'release':
        if plan['status'] == 'none':
            return True, None, None
        entry = {'transition': 'released', 'by': 'human', 'id': plan['id'], 'order_id': plan['order_id'],
                 't': round(kitchen.time, 2)}
        _clear(plan, kitchen, kind='released', actor='human', cooldown=True)
        return True, None, entry

    if action == 'accept':
        if plan['status'] != 'proposed' or plan['proposer'] != 'jeff':
            return False, '当前没有待确认的 Jeff 提议。', None
        order = _find_pending(kitchen, plan['order_id'])
        if order is None:
            _clear(plan, kitchen, kind='order_gone', actor='engine')
            return False, '该订单已结束。', None
        if division is not None:
            allowed = available_divisions(kitchen, order['dish'])
            if division not in allowed:
                return False, '分工选项无效。', None
            plan['division'] = division
        plan['status'] = 'active'
        plan['accepted_t'] = round(kitchen.time, 2)
        plan['accepted_by'] = 'human'
        progress = order_progress(kitchen, order)
        plan['progress_sig'] = progress['sig']
        plan['last_progress_t'] = round(kitchen.time, 2)
        plan['last_recheck_t'] = round(kitchen.time, 2)
        _set_notice(plan, kitchen, 'accepted', 'human', plan['order_id'], plan['dish'], plan['division'])
        return True, None, {'transition': 'accepted', 'by': 'human', 'id': plan['id'], 'order_id': plan['order_id'],
                            'division': plan['division'], 't': round(kitchen.time, 2)}

    if action == 'decline':
        if plan['status'] != 'proposed' or plan['proposer'] != 'jeff':
            return False, '当前没有待拒绝的 Jeff 提议。', None
        entry = {'transition': 'declined', 'by': 'human', 'id': plan['id'], 'order_id': plan['order_id'],
                 't': round(kitchen.time, 2)}
        _clear(plan, kitchen, kind='declined', actor='human', cooldown=True)
        return True, None, entry

    if action == 'focus':
        order = _find_pending(kitchen, order_id)
        if order is None:
            return False, '该订单当前不在等待列表中。', None
        allowed = available_divisions(kitchen, order['dish'])
        explicit = division is not None
        chosen_div = division if explicit else 'shared'
        if chosen_div not in allowed:
            return False, '分工选项无效。', None
        # Clicking the exact order Jeff just proposed (without overriding division) directly accepts it.
        if (plan['status'] == 'proposed' and plan['proposer'] == 'jeff' and plan['order_id'] == order['id']
                and (not explicit or chosen_div == plan['division'])):
            return human_action(plan, kitchen, 'accept')
        # Clicking the already focused order again with no division change toggles it off.
        if plan['status'] in ('proposed', 'active') and plan['order_id'] == order['id'] and not explicit:
            return human_action(plan, kitchen, 'release')
        # Clicking the division chip that is already active or already proposed by the human is a no-op.
        if plan['status'] in ('proposed', 'active') and plan['order_id'] == order['id'] and explicit and chosen_div == plan['division']:
            return True, None, None
        plan['seq'] = int(plan.get('seq', 0)) + 1
        progress = order_progress(kitchen, order)
        plan.update(
            status='proposed',
            id=f"P{plan['seq']}",
            proposer='human',
            order_id=order['id'],
            dish=order['dish'],
            order_deadline=order['deadline'],
            division=chosen_div,
            explicit_division=explicit,
            created_t=round(kitchen.time, 2),
            accepted_t=None,
            accepted_by=None,
            suspended=False,
            suspend_reason=None,
            progress_sig=progress['sig'],
            last_progress_t=round(kitchen.time, 2),
            last_recheck_t=round(kitchen.time, 2),
            recheck=False,
            event_cursor=len(kitchen.events),
        )
        _set_notice(plan, kitchen, 'proposed', 'human', order['id'], order['dish'], chosen_div)
        return True, None, {'transition': 'proposed', 'by': 'human', 'id': plan['id'], 'order_id': order['id'],
                            'dish': order['dish'], 'division': chosen_div, 'explicit_division': explicit,
                            't': round(kitchen.time, 2)}

    return False, '不支持的聚焦操作。', None


def _needs_recheck(plan, kitchen):
    """Whether an active commitment should ask Jeff keep/release on this turn."""
    if plan['status'] != 'active' or plan.get('suspended'):
        return False
    if plan.get('recheck'):
        return True
    if kitchen.time - plan.get('last_recheck_t', 0.0) < RECHECK_INTERVAL:
        return False
    if kitchen.time - plan.get('last_progress_t', 0.0) >= STALL_RECHECK_SECONDS:
        return True
    current = _find_pending(kitchen, plan['order_id'])
    if current is not None:
        urgent_other = any(
            o.get('id') != current['id'] and o.get('deadline', float('inf')) + 10.0 < current.get('deadline', float('inf'))
            and (o.get('deadline', float('inf')) - kitchen.time) <= 25.0
            for o in _pending_orders(kitchen)
        )
        if urgent_other:
            return True
    return False


def _proposal_criteria(kitchen):
    """Build concise, bounded proposal options (max 5 keys including 'none') for Jeff."""
    pending = _pending_orders(kitchen)
    if not pending:
        return {}
    first = pending[0]
    criteria = {'none': 'Do not propose a shared order focus now'}
    dish_name = _dish_en(kitchen, first['dish'])
    left = max(0.0, first.get('deadline', 0.0) - kitchen.time)
    for div in available_divisions(kitchen, first['dish']):
        if div == 'shared' and len(available_divisions(kitchen, first['dish'])) > 1:
            continue
        my_part, other_part = division_text(kitchen, first['dish'], div)
        criteria[f"{first['id']}:{div}"] = (
            f"Propose shared focus on {first['id']} ({dish_name}, {left:.0f} s left): "
            f"you handle {my_part}; the other chef handles {other_part}"
        )
    # On multi-dish menus, also allow proposing the earliest waiting order of a different dish.
    other = next((o for o in pending[1:] if o['dish'] != first['dish']), None)
    if other is not None:
        other_name = _dish_en(kitchen, other['dish'])
        other_left = max(0.0, other.get('deadline', 0.0) - kitchen.time)
        div = available_divisions(kitchen, other['dish'])[0]
        my_part, other_part = division_text(kitchen, other['dish'], div)
        criteria[f"{other['id']}:{div}"] = (
            f"Propose shared focus on {other['id']} ({other_name}, {other_left:.0f} s left): "
            f"you handle {my_part}; the other chef handles {other_part}"
        )
    return criteria


def _reply_criteria(kitchen, plan):
    """Criteria for Jeff's reply to a human order-focus proposal."""
    order = _find_pending(kitchen, plan['order_id'])
    if order is None:
        return {}
    dish_name = _dish_en(kitchen, order['dish'])
    if plan.get('explicit_division'):
        my_part, other_part = division_text(kitchen, order['dish'], plan['division'])
        return {
            'accept': f"Accept focusing {order['id']} ({dish_name}): you handle {my_part}; the other chef handles {other_part}",
            'decline': f"Decline focusing {order['id']} now (the other chef is informed)",
        }
    criteria = {}
    for div in available_divisions(kitchen, order['dish']):
        my_part, other_part = division_text(kitchen, order['dish'], div)
        criteria[f'accept:{div}'] = (
            f"Accept focusing {order['id']} ({dish_name}): you handle {my_part}; the other chef handles {other_part}"
        )
    criteria['decline'] = f"Decline focusing {order['id']} now (the other chef is informed)"
    return criteria


def _state_block(kitchen, plan):
    order = _find_pending(kitchen, plan['order_id'])
    if order is None:
        return None
    progress = order_progress(kitchen, order)
    my_part, other_part = division_text(kitchen, order['dish'], plan['division'])
    block = {
        'id': plan['id'],
        'status': plan['status'],
        'proposed_by': 'the other chef' if plan['proposer'] == 'human' else 'you',
        'order': f"{order['id']} {_dish_en(kitchen, order['dish'])} ({max(0.0, order['deadline'] - kitchen.time):.1f} s left)",
        'your_part': my_part,
        'other_chef_part': other_part,
        'progress': {r['name_en']: r['detail'] for r in progress['components']},
        'plate': progress['plate_status'],
    }
    return block


def apply(payload, kitchen, plan_state, ask_ahead=False):
    """Purely add joint_plan state, rule and optional question to a composed English payload."""
    if plan_state is None:
        return payload
    state = payload['state']
    state['joint_plan_version'] = VERSION
    if crisis_reason(kitchen) is not None or plan_state.get('suspended'):
        return payload

    status = plan_state.get('status', 'none')
    questions = payload['questions']
    added = False

    if status in ('proposed', 'active'):
        block = _state_block(kitchen, plan_state)
        if block is not None:
            state['joint_plan'] = block
            added = True
            if status == 'proposed' and plan_state.get('proposer') == 'human':
                criteria = _reply_criteria(kitchen, plan_state)
                if criteria:
                    questions[REPLY_Q] = {
                        'type': 'choice',
                        'instructions': 'The other chef clicked to propose a shared order focus. Accept (choosing a division if offered) or decline.',
                        'criteria': criteria,
                    }
            elif not ask_ahead and status == 'active' and _needs_recheck(plan_state, kitchen):
                order_label = block['order']
                questions[STATUS_Q] = {
                    'type': 'choice',
                    'instructions': 'Keep the current shared order focus, or release it (the other chef will be informed)?',
                    'criteria': {
                        'keep': f'Keep current shared focus on {order_label}',
                        'release': f'Release shared focus on {order_label} and inform the other chef',
                    },
                }
    elif status == 'none' and not ask_ahead and kitchen.time >= plan_state.get('cooldown_until', 0.0):
        criteria = _proposal_criteria(kitchen)
        if len(criteria) > 1:
            questions[PROPOSAL_Q] = {
                'type': 'choice',
                'instructions': 'Optionally propose a shared order focus to the other chef, or choose none.',
                'criteria': criteria,
            }
            added = True

    if added:
        state['rules']['joint_plan'] = RULE
    return payload


def apply_answer(plan, kitchen, result, asked_questions):
    """Update live plan state from Jeff's model answer. Returns a transition log dict or None."""
    if plan is None or not asked_questions:
        return None
    sync(plan, kitchen)

    if REPLY_Q in asked_questions and plan['status'] == 'proposed' and plan['proposer'] == 'human':
        ans = result.get(REPLY_Q)
        if not isinstance(ans, str):
            return None
        order = _find_pending(kitchen, plan['order_id'])
        if order is None:
            _clear(plan, kitchen, kind='order_gone', actor='engine')
            return None
        if ans == 'decline':
            entry = {'transition': 'declined', 'by': 'jeff', 'id': plan['id'], 'order_id': plan['order_id'],
                     't': round(kitchen.time, 2)}
            _clear(plan, kitchen, kind='declined', actor='jeff', cooldown=True)
            return entry
        if ans == 'accept' or ans.startswith('accept:'):
            div = ans.split(':', 1)[1] if ':' in ans else plan['division']
            if div not in available_divisions(kitchen, order['dish']):
                div = plan['division']
            plan['division'] = div
            plan['status'] = 'active'
            plan['accepted_t'] = round(kitchen.time, 2)
            plan['accepted_by'] = 'jeff'
            progress = order_progress(kitchen, order)
            plan['progress_sig'] = progress['sig']
            plan['last_progress_t'] = round(kitchen.time, 2)
            plan['last_recheck_t'] = round(kitchen.time, 2)
            _set_notice(plan, kitchen, 'accepted', 'jeff', plan['order_id'], plan['dish'], div)
            return {'transition': 'accepted', 'by': 'jeff', 'id': plan['id'], 'order_id': plan['order_id'],
                    'division': div, 't': round(kitchen.time, 2)}
        return None

    if STATUS_Q in asked_questions and plan['status'] == 'active':
        ans = result.get(STATUS_Q)
        plan['recheck'] = False
        plan['last_recheck_t'] = round(kitchen.time, 2)
        if ans == 'release':
            entry = {'transition': 'released', 'by': 'jeff', 'id': plan['id'], 'order_id': plan['order_id'],
                     't': round(kitchen.time, 2)}
            _clear(plan, kitchen, kind='released', actor='jeff', cooldown=True)
            return entry
        return {'transition': 'kept', 'by': 'jeff', 'id': plan['id'], 'order_id': plan['order_id'],
                't': round(kitchen.time, 2)} if ans == 'keep' else None

    if PROPOSAL_Q in asked_questions and plan['status'] == 'none':
        ans = result.get(PROPOSAL_Q)
        if not isinstance(ans, str) or ans == 'none' or ':' not in ans:
            return None
        order_id, div = ans.split(':', 1)
        order = _find_pending(kitchen, order_id)
        if order is None or div not in available_divisions(kitchen, order['dish']):
            return None
        plan['seq'] = int(plan.get('seq', 0)) + 1
        progress = order_progress(kitchen, order)
        plan.update(
            status='proposed',
            id=f"P{plan['seq']}",
            proposer='jeff',
            order_id=order['id'],
            dish=order['dish'],
            order_deadline=order['deadline'],
            division=div,
            explicit_division=True,
            created_t=round(kitchen.time, 2),
            accepted_t=None,
            accepted_by=None,
            suspended=False,
            suspend_reason=None,
            progress_sig=progress['sig'],
            last_progress_t=round(kitchen.time, 2),
            last_recheck_t=round(kitchen.time, 2),
            recheck=False,
            event_cursor=len(kitchen.events),
        )
        _set_notice(plan, kitchen, 'proposed', 'jeff', order['id'], order['dish'], div)
        return {'transition': 'proposed', 'by': 'jeff', 'id': plan['id'], 'order_id': order['id'],
                'dish': order['dish'], 'division': div, 't': round(kitchen.time, 2)}

    return None


def snapshot_for_record(plan):
    """Frozen copy of plan state stored on ai_request so research replay rebuilds the exact request."""
    return deepcopy(plan) if plan is not None else None


def public_state(plan, kitchen):
    """Player-facing joint_plan view exposed on /api/state and /api/joint-plan."""
    if plan is None:
        return {'enabled': False}
    order = _find_pending(kitchen, plan['order_id']) if plan.get('order_id') else None
    progress = order_progress(kitchen, order) if order is not None else None
    ttl = (round(max(0.0, PROPOSAL_TTL - (kitchen.time - plan['created_t'])), 1)
           if plan['status'] == 'proposed' and plan.get('created_t') is not None else None)
    return {
        'enabled': True,
        'status': plan['status'],
        'id': plan['id'],
        'proposer': plan['proposer'],
        'order_id': plan['order_id'],
        'dish': plan['dish'],
        'dish_name': kitchen.rules.recipe_names.get(plan['dish'], plan['dish']) if plan.get('dish') else None,
        'division': plan['division'],
        'divisions': list(available_divisions(kitchen, order['dish'])) if order is not None else [],
        'suspended': bool(plan.get('suspended')),
        'suspend_reason': plan.get('suspend_reason'),
        'accepted_by': plan.get('accepted_by'),
        'ttl_remaining': ttl,
        'progress': progress,
        'notice': deepcopy(plan.get('last_notice')),
    }
