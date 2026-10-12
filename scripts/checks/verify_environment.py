"""Run the six C1 checks; functions are independently callable and import-safe."""

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import distribution
from pathlib import Path
from time import perf_counter

import numpy as np
import pogema
from pogema import GridConfig, SumOfCostsAndMakespanMetric, pogema_v0


def make_config(seed, **overrides):
    """Keep sensing, collision, and target settings explicit across checks."""
    settings = dict(num_agents=8, size=16, density=0.3, seed=seed,
                    obs_radius=3, max_episode_steps=128,
                    observation_type="POMAPF", collision_system="priority",
                    on_target="finish", integration=None)
    settings.update(overrides)
    return GridConfig(**settings)


def require(condition, message):
    """Unlike assert, checks remain enabled when Python runs with -O."""
    if not condition:
        raise AssertionError(message)


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, default=json_value).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_state(env):
    """Return map-relative row/column coordinates, including inactive agents."""
    base = env.unwrapped
    return {"positions": base.get_agents_xy(ignore_borders=True),
            "goals": base.get_targets_xy(ignore_borders=True)}


def action_id(config, delta):
    moves = [tuple(move) for move in config.MOVES]
    return moves.index(delta)


def check_scale(seed):
    config = make_config(seed, num_agents=100, size=64, max_episode_steps=256)
    started = perf_counter()
    env = pogema_v0(grid_config=config)
    try:
        observations, _ = env.reset(seed=seed)
        reset_seconds = perf_counter() - started
        require(len(observations) == 100, "Expected 100 observations")
        initial_goals = read_state(env)["goals"]
        rng = np.random.default_rng(seed)
        rollout_start = perf_counter()
        for steps in range(1, config.max_episode_steps + 1):
            actions = rng.integers(len(config.MOVES), size=100).tolist()
            observations, _, terminated, truncated, infos = env.step(actions)
            state = read_state(env)
            require(len(state["positions"]) == 100, "Lost agent IDs in state")
            require(state["goals"] == initial_goals, "Fixed goals changed")
            require(len(observations) == 100, "Lost agent observations")
            if all(terminated) or all(truncated):
                break
        rollout_seconds = perf_counter() - rollout_start
        require(all(terminated) or all(truncated), "Episode did not end")
        return {"config": config.model_dump(), "steps": steps,
                "end_reason": "all_arrived" if all(terminated) else "time_limit",
                "create_and_reset_seconds": reset_seconds,
                "rollout_seconds": rollout_seconds,
                "total_seconds": perf_counter() - started,
                "metrics": infos[0].get("metrics", {}),
                "state_reads": steps + 1,
                "policy": "seeded NumPy random actions; no path planner"}
    finally:
        env.close()


def collision_case(seed, starts, goals, steps):
    config = make_config(seed, map=".........", num_agents=2, obs_radius=2,
                         agents_xy=starts, targets_xy=goals, max_episode_steps=30)
    env = pogema_v0(grid_config=config)
    try:
        env.reset(seed=seed)
        frames = [read_state(env)["positions"]]
        actions = [action_id(config, (0, 1)), action_id(config, (0, -1))]
        for _ in range(steps):
            env.step(actions)
            positions = read_state(env)["positions"]
            require(len({tuple(p) for p in positions}) == 2, "Shared occupied cell")
            frames.append(positions)
        return frames
    finally:
        env.close()


def check_collisions(seed):
    same_cell = collision_case(seed, [[0, 0], [0, 2]], [[0, 8], [0, 7]], 1)
    moved = sum(a != b for a, b in zip(same_cell[0], same_cell[1]))
    require(moved == 1, "Priority resolution should allow one claimant to move")
    swap = collision_case(seed, [[0, 0], [0, 1]], [[0, 8], [0, 7]], 1)
    require(swap[0] == swap[1], "Adjacent agents unexpectedly swapped cells")
    corridor = collision_case(seed, [[0, 0], [0, 8]], [[0, 8], [0, 0]], 12)
    require(all(frame == corridor[-1] for frame in corridor[-5:]),
            "Corridor did not exhibit sustained blocking")
    a, b = corridor[-1]
    require(abs(a[1] - b[1]) == 1, "Expected adjacent blocked robots")
    require(corridor[-1] != [[0, 8], [0, 0]], "Blocked robots reached their goals")
    return {"collision_system": "priority", "same_cell_frames": same_cell,
            "swap_frames": swap, "corridor_frames": corridor,
            "conclusion": "No co-occupancy or swap in these cases; corridor stalls."}


def check_state_access(seed):
    config = make_config(seed)
    env = pogema_v0(grid_config=config)
    try:
        observations, _ = env.reset(seed=seed)
        state = read_state(env)
        base = env.unwrapped
        offset = config.obs_radius
        require(state["positions"] == [[r - offset, c - offset]
                                      for r, c in base.grid.positions_xy],
                "Public positions disagree with grid positions")
        require(state["goals"] == [[r - offset, c - offset]
                                  for r, c in base.grid.finishes_xy],
                "Public goals disagree with grid goals")
        obstacles = base.get_obstacles(ignore_borders=True)
        require(obstacles.shape == (16, 16), "Unexpected borderless map size")
        for row, col in state["positions"] + state["goals"]:
            require(0 <= row < 16 and 0 <= col < 16, "Out-of-map coordinate")
            require(obstacles[row, col] == 0, "Start or goal lies in an obstacle")
        for i, observation in enumerate(observations):
            start, goal = state["positions"][i], state["goals"][i]
            require(tuple(observation["xy"]) == (0, 0),
                    "Expected observation coordinates relative to agent start")
            require(tuple(observation["target_xy"]) == (
                        goal[0] - start[0], goal[1] - start[1]),
                    "Observation goal does not match its start-relative frame")
        return {"initial_state": state, "map_shape": list(obstacles.shape),
                "grid_coordinate_offset": offset,
                "coordinate_convention": "[row, column], ignore_borders=True",
                "positions_api": "env.unwrapped.get_agents_xy(ignore_borders=True)",
                "goals_api": "env.unwrapped.get_targets_xy(ignore_borders=True)",
                "observation_coordinates": "xy and target_xy are relative to each agent's initial position",
                "inactive_agents": "Included by default; consult info[i]['is_active']."}
    finally:
        env.close()


def check_custom_actions(seed):
    config = make_config(seed, map=".........", num_agents=2,
                         agents_xy=[[0, 0], [0, 8]], targets_xy=[[0, 4], [0, 5]])
    env = pogema_v0(grid_config=config)
    try:
        env.reset(seed=seed)
        before = read_state(env)["positions"]
        actions = [action_id(config, (0, 1)), action_id(config, (0, 0))]
        env.step(actions)
        after = read_state(env)["positions"]
        require(after == [[0, 1], [0, 8]], "Move/wait actions were not independent")
        return {"moves": config.MOVES, "actions": actions,
                "before": before, "after": after}
    finally:
        env.close()


def replay(env, seed):
    observations, infos = env.reset(seed=seed)
    initial = {**read_state(env),
               "obstacles": env.unwrapped.get_obstacles(ignore_borders=True)}
    trace = [fingerprint([read_state(env), observations, infos])]
    rng = np.random.default_rng(seed)
    for _ in range(8):
        actions = rng.integers(len(env.unwrapped.grid_config.MOVES), size=8).tolist()
        observations, rewards, terminated, truncated, infos = env.step(actions)
        trace.append(fingerprint([read_state(env), observations, rewards,
                                  terminated, truncated, infos]))
        if all(terminated) or all(truncated):
            break
    return fingerprint(initial), trace


def check_seeding(seed):
    env = pogema_v0(grid_config=make_config(seed))
    other = pogema_v0(grid_config=make_config(seed))
    try:
        first = replay(env, seed)
        repeated = replay(env, seed)
        independent = replay(other, seed)
        different = replay(other, seed + 1)
        require(first == repeated, "Reset with the same seed changed the run")
        require(first == independent, "Separate environments disagree for same seed")
        require(first[0] != different[0], "Different seeds produced identical instances")
        return {"seed": seed, "different_seed": seed + 1,
                "instance_sha256": first[0], "different_instance_sha256": different[0],
                "same_seed_same_instance_and_rollout": True,
                "same_environment_reset_reproducible": True,
                "steps_compared": len(first[1]) - 1,
                "action_rng": "Dedicated NumPy generator reset with the run seed"}
    finally:
        env.close()
        other.close()


def metric_episode(seed, with_costs):
    config = make_config(seed, map=".........", num_agents=2,
                         agents_xy=[[0, 0], [0, 8]], targets_xy=[[0, 1], [0, 6]])
    env = pogema_v0(grid_config=config)
    if with_costs:
        env = SumOfCostsAndMakespanMetric(env)
    try:
        observations, reset_info = env.reset(seed=seed)
        shapes = {key: {"shape": list(np.asarray(value).shape),
                        "dtype": str(np.asarray(value).dtype)}
                  for key, value in observations[0].items()}
        right, left, wait = (action_id(config, d) for d in [(0, 1), (0, -1), (0, 0)])
        _, _, _, _, first_info = env.step([right, left])
        _, _, terminated, truncated, final_info = env.step([wait, left])
        require(all(terminated) and not any(truncated), "Known two-step run failed")
        require(final_info[0]["metrics"]["ISR"] == 1.0, "Incorrect individual success")
        require(final_info[0]["metrics"]["CSR"] == 1.0, "Incorrect cooperative success")
        require("metrics" not in final_info[1], "Unexpected metric location")
        require(not reset_info[0].get("metrics") and not first_info[0].get("metrics"),
                "Unexpected early aggregate metrics")
        require(reset_info[0]["is_active"] and not final_info[0]["is_active"],
                "Goal-reaching agent did not become inactive")
        return {"observation_fields": shapes, "reset_info": reset_info,
                "first_step_info": first_info, "final_info": final_info}
    finally:
        env.close()


def check_observations_and_metrics(seed):
    default = metric_episode(seed, with_costs=False)
    wrapped = metric_episode(seed, with_costs=True)
    require({"obstacles", "agents", "xy", "target_xy"}.issubset(
                default["observation_fields"]), "Missing POMAPF fields")
    costs = wrapped["final_info"][0]["metrics"]
    require({"SoC", "makespan"}.issubset(costs), "Cost wrapper did not add metrics")
    require(costs["makespan"] == 2, "Incorrect makespan on the known run")
    require(costs["SoC"] == 3, "Incorrect SoC for arrivals at steps 1 and 2")
    require(default["final_info"][0]["metrics"]["ep_length"] == 1.5,
            "Unexpected mean episode length for arrivals at steps 1 and 2")
    return {"default": default, "with_cost_wrapper": wrapped,
            "known_first_arrival_steps": [1, 2], "expected_first_arrival_SoC": 3,
            "wrapper_SoC_matches_first_arrivals": True}


CHECKS = {"scale": check_scale, "collisions": check_collisions,
          "state_access": check_state_access, "custom_actions": check_custom_actions,
          "seeding": check_seeding, "observations_and_metrics": check_observations_and_metrics}


def run_checks(seed):
    provenance = distribution("pogema").read_text("direct_url.json")
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
              "versions": {"python": platform.python_version(),
                           "pogema": pogema.__version__, "numpy": np.__version__},
              "pogema_source": json.loads(provenance) if provenance else None,
              "checks": {}}
    for name, check in CHECKS.items():
        try:
            evidence = check(seed)
            report["checks"][name] = {"passed": True, "evidence": evidence}
            print(f"PASS {name}", flush=True)
        except Exception as exc:
            report["checks"][name] = {"passed": False,
                                      "error": f"{type(exc).__name__}: {exc}"}
            print(f"FAIL {name}: {exc}", flush=True)
    report["all_passed"] = all(result["passed"] for result in report["checks"].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", type=Path, default=(
        Path(__file__).resolve().parents[2] / "outputs/verification/environment.json"))
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("--seed must be non-negative")
    report = run_checks(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=json_value) + "\n",
                           encoding="utf-8")
    print(f"Evidence: {args.output.resolve()}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
