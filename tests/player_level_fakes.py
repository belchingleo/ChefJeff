"""Calibration stand-ins for test_player_level_queue.

The queue's spawned process imports the module that holds its calibrate function, so these live
apart from the tests: importing them must not pull in the servers (whose module names the
scripts folder, earlier on the test run's path, would shadow).
"""
from multiprocessing import Pool
import time


def quick(bundle, seeds, workers):
    return {'playable': True, 'target': 150, 'pacing': {'interval_game_ms': 30000}, 'pair_median': 300,
            'solo_median': 100, 'solo_reaches_target': False, 'seeds': list(seeds), 'runs': [{'seed': 1}],
            'diagnostics': []}


def pooled(bundle, seeds, workers):
    # As level_calibration.calibrate does with workers > 1: a pool inside the calibration process.
    with Pool(workers) as pool:
        pool.map(abs, seeds)
    return quick(bundle, seeds, workers)


def slow(bundle, seeds, workers):
    time.sleep(60)


def broken(bundle, seeds, workers):
    raise RuntimeError('a key or a path that must not reach the page')
