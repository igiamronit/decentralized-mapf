"""Independent exhaustive references and real seeded cross-component checks.

These are correctness/stress fixtures, not the missing research experiment
harness: no statistical planner comparison or oracle optimality is asserted.
"""

import json
from collections import deque
from itertools import product

import pytest
from pogema import GridConfig, pogema_v0

from decentralized_mapf import (
    DCMAPFPlanner, GlobalCommunication, KNNCommunication, Metrics,
    NoCommunication, PerfectChannel, RangeCommunication, StepRecord, run_episode,
)
from decentralized_mapf.monitors import rho_live
from decentralized_mapf.pathfinding import astar


def test_astar_on_every_two_by_three_binary_map_against_bfs():
    cells = list(product(range(2), range(3)))
    for obstacles in product((0, 1), repeat=6):
        grid = [obstacles[:3], obstacles[3:]]
        free = [p for p in cells if not grid[p[0]][p[1]]]
        for start, goal in product(free, repeat=2):
            queue, distances = deque([start]), {start: 0}
            while queue:
                current = queue.popleft()
                for candidate in free:
                    if candidate not in distances and sum(abs(a - b) for a, b in zip(
                            current, candidate)) == 1:
                        distances[candidate] = distances[current] + 1
                        queue.append(candidate)
            path = astar(grid, start, goal)
            if goal not in distances or start == goal:
                assert path == []
            else:
                assert len(path) == distances[goal]
                assert path[-1] == goal
                for before, after in zip([start] + path, path):
                    assert after in free
                    assert sum(abs(a - b) for a, b in zip(before, after)) == 1


def test_liveness_against_explicit_eventually_formula_on_all_short_signals():
    for distances in product(range(4), repeat=5):
        rows = [StepRecord(t, [(0, d)], 0, 1, 0, {}) for t, d in enumerate(distances)]
        arrival = next((t for t, d in enumerate(distances) if d == 0), len(rows))
        for window in range(1, 6):
            starts = [t for t in range(len(rows) - window) if t < arrival]
            observed = rho_live(rows, 0, [(0, 0)], window)
            if not starts:
                assert observed is None
            else:
                holds = all(any(distances[j] < distances[t]
                                for j in range(t + 1, t + window + 1)) for t in starts)
                assert (observed >= 0) == holds


@pytest.mark.parametrize("seed", [1, 7])
@pytest.mark.parametrize("n_agents", [10, 25, 100])
@pytest.mark.parametrize("topology", ["global", "none", "range", "knn"])
def test_seeded_production_pipeline_invariants_and_replay(seed, n_agents, topology):
    config = GridConfig(num_agents=n_agents, size=32, density=0.2, seed=seed,
                        max_episode_steps=24, obs_radius=2, observation_type="POMAPF",
                        on_target="finish", collision_system="priority", integration=None)
    env = pogema_v0(grid_config=config)
    try:
        env.reset(seed=seed)
        grid = env.unwrapped.get_obstacles(ignore_borders=True)
        goals = env.unwrapped.get_targets_xy(ignore_borders=True)
        planner = DCMAPFPlanner(grid, goals, moves=config.MOVES)
        model = {"global": GlobalCommunication(), "none": NoCommunication(),
                 "range": RangeCommunication(3), "knn": KNNCommunication(2)}[topology]
        runs = []
        for _ in range(2):
            metrics = Metrics(goals, seed=seed, window=5, intent_provider=planner.intended_steps)
            result = run_episode(env, model, PerfectChannel(), planner, metrics, 24)
            assert result["steps"] <= 24
            assert result["rho_safe"] is None or result["rho_safe"] >= 0
            assert 0 <= result["ISR"] <= 1
            assert result["n_messages"] == sum(sum(map(len, r.inbox_senders.values()))
                                               for r in metrics.trace)
            for before, after in zip(metrics.trace, metrics.trace[1:]):
                for p, q in zip(before.positions, after.positions):
                    assert grid[q[0]][q[1]] == 0
                    assert sum(abs(a - b) for a, b in zip(p, q)) <= 1
            restored = Metrics.from_data(json.loads(json.dumps(metrics.to_data())))
            assert restored.summary() == result
            runs.append((result, metrics.trace))
        assert runs[0] == runs[1]
    finally:
        env.close()
