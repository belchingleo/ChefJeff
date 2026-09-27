"""Authored levels. Game parameters and seeded orders are recorded in each round."""
import random

def level_config(base, level):
    c=dict(base);c['level']=level
    if level==2:
        c.update(boards=2,pots=1,pot_count=1,plate_count=2,round_seconds=240,
                 order_count=3,order_interval=30,order_patience=180,target_served=3,target_money=120)
        c['order_seed']=base.get('order_seed',random.SystemRandom().randrange(2**31))
    elif level==3:
        c.update(level=3,boards=3,pots=2,pot_count=3,plate_count=3,round_seconds=360,
                 order_count=5,order_interval=30,order_patience=100,target_served=5,target_money=140)
        c['order_seed']=base.get('order_seed',random.SystemRandom().randrange(2**31))
    return c


def burger_map():
    from map_definition import load_map, geometry
    return geometry(load_map(3))


def counter_map():
    from map_definition import load_map, geometry
    return geometry(load_map(2))
