"""Config-driven experiment sweeps over matched instances (C7).

One instance is fixed by (map type, map size, robot count, seed). Every topology
runs on that same map, starts and goals, so only communication changes between
them. Each run becomes one result row; failures are rows too, never dropped.
"""

import csv
import hashlib
import json
import math
import platform
import random
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import distribution, version
from pathlib import Path

import yaml
from pogema import GridConfig, pogema_v0
from pogema.generator import generate_obstacles

from .channels import PerfectChannel
from .communication import (GlobalCommunication, KNNCommunication,
                            NoCommunication, RangeCommunication)
from .coordination import coordination_summary, goal_distances
from .interfaces import Planner
from .metrics import Metrics
from .oracle import oracle_metrics, oracle_soc_ratio, oracle_solve
from .planner import DCMAPFPlanner
from .runner import run_episode

MAP_TYPES = ("random", "warehouse", "maze")
CONFIG_KEYS = {"name", "kind", "maps", "n_agents", "seeds", "topologies", "size",
               "max_steps", "window", "obs_radius", "oracle", "oracle_timeout",
               "save_traces", "description"}


def random_map(seed, size, density=0.2):
    """POGEMA's own seeded obstacle sampler."""
    config = GridConfig(size=size, density=density, seed=seed, num_agents=1)
    return generate_obstacles(config).tolist()


def warehouse_map(size):
    """Shelves 2 rows x 6 columns, with one-cell aisles between shelf rows."""
    grid = [[0] * size for _ in range(size)]
    for r in range(2, size - 2, 3):
        for start in range(2, size - 6, 8):
            for c in range(start, start + 6):
                grid[r][c] = grid[r + 1][c] = 1
    return grid


def maze_map(seed, size, braid=0.3):
    """Depth-first maze with some walls removed, so corridors form loops.

    Cells sit at even coordinates of an odd-sized grid; an even size gets a free
    last row and column. Corridors are one cell wide, the hardest map for passing.
    """
    rng = random.Random(seed)
    n = size if size % 2 else size - 1
    grid = [[1] * n for _ in range(n)]
    grid[0][0] = 0
    stack, seen = [(0, 0)], {(0, 0)}
    while stack:
        r, c = stack[-1]
        options = [(r + dr, c + dc) for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2))
                   if 0 <= r + dr < n and 0 <= c + dc < n and (r + dr, c + dc) not in seen]
        if not options:
            stack.pop()
            continue
        nr, nc = rng.choice(options)
        grid[(r + nr) // 2][(c + nc) // 2] = 0
        grid[nr][nc] = 0
        seen.add((nr, nc))
        stack.append((nr, nc))

    # A wall between two cells has exactly one odd coordinate.
    for r in range(n):
        for c in range(n):
            if grid[r][c] and (r % 2) != (c % 2) and rng.random() < braid:
                grid[r][c] = 0
    if n < size:
        grid = [row + [0] for row in grid] + [[0] * size]
    return grid


def make_map(map_name, seed, size):
    if map_name == "random":
        return random_map(seed, size)
    if map_name == "warehouse":
        return warehouse_map(size)
    if map_name == "maze":
        return maze_map(seed, size)
    raise ValueError(f"Unknown map type {map_name!r}; use one of {MAP_TYPES}")


def map_string(grid):
    return "\n".join("".join("#" if cell else "." for cell in row) for row in grid)


def instance_id(grid, starts, goals):
    """Short fingerprint, so matched runs can be checked rather than assumed."""
    text = json.dumps([map_string(grid), starts, goals])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def make_instance(map_name, n_agents, seed, size=32):
    """Map, starts and goals for one matched instance, independent of topology.

    POGEMA places each start and goal in the same connected region.
    """
    grid = make_map(map_name, seed, size)
    config = GridConfig(map=map_string(grid), num_agents=n_agents, seed=seed,
                        observation_type="POMAPF", on_target="finish",
                        collision_system="priority", integration=None)
    env = pogema_v0(grid_config=config)
    try:
        env.reset(seed=seed)
        starts = [tuple(p) for p in env.unwrapped.get_agents_xy(ignore_borders=True)]
        goals = [tuple(p) for p in env.unwrapped.get_targets_xy(ignore_borders=True)]
    finally:
        env.close()
    return {"map": map_name, "size": size, "n_agents": n_agents, "seed": seed,
            "instance_id": instance_id(grid, starts, goals),
            "grid": grid, "starts": starts, "goals": goals}


def make_topology(name):
    """'global', 'none', 'range_<r>' or 'knn_<k>'; 'range_inf' has no limit."""
    if name == "global":
        return GlobalCommunication()
    if name == "none":
        return NoCommunication()
    family, _, value = name.partition("_")
    if family == "range" and value:
        return RangeCommunication(math.inf if value == "inf" else int(value))
    if family == "knn" and value:
        return KNNCommunication(int(value))
    raise ValueError(f"Unknown topology {name!r}")


def topology_parameter(name):
    """The swept value of a topology name: r for range, k for k-NN, else None."""
    family, _, value = name.partition("_")
    if family in ("range", "knn"):
        return math.inf if value == "inf" else int(value)
    return None


def build_run(instance, topology, max_steps, obs_radius=3):
    """Environment, communication model and planner for one run."""
    config = GridConfig(map=map_string(instance["grid"]), num_agents=instance["n_agents"],
                        agents_xy=[list(p) for p in instance["starts"]],
                        targets_xy=[list(p) for p in instance["goals"]],
                        seed=instance["seed"], obs_radius=obs_radius,
                        max_episode_steps=max_steps, observation_type="POMAPF",
                        on_target="finish", collision_system="priority", integration=None)
    env = pogema_v0(grid_config=config)
    planner = DCMAPFPlanner(instance["grid"], instance["goals"], moves=config.MOVES)
    return env, make_topology(topology), planner


class RecordingPlanner(Planner):
    """Pass every call to the planner and remember the action it chose.

    Actions are measurement only. They separate a chosen wait from a move
    the simulator rejected, which positions alone cannot show.
    """

    def __init__(self, planner):
        self.planner = planner
        self.actions = {}

    def reset(self):
        self.planner.reset()
        self.actions = {}

    def observe(self, agent_id, observation, position, goal):
        self.planner.observe(agent_id, observation, position, goal)

    def compose(self, agent_id, t):
        self.t = t
        return self.planner.compose(agent_id, t)

    def act(self, agent_id, observation, inbox, goal):
        action = self.planner.act(agent_id, observation, inbox, goal)
        self.actions.setdefault(self.t, {})[agent_id] = action
        return action


def instance_columns(instance):
    return {key: instance[key] for key in ("map", "size", "n_agents", "seed", "instance_id")}


def run_one(instance, topology, max_steps, window=10, obs_radius=3):
    """Run one topology on one instance; return a flat result row and details."""
    started = time.perf_counter()
    env, comm, planner = build_run(instance, topology, max_steps, obs_radius)
    recorder = RecordingPlanner(planner)
    try:
        env.reset(seed=instance["seed"])
        goals = [tuple(p) for p in env.unwrapped.get_targets_xy(ignore_borders=True)]
        metrics = Metrics(goals, seed=instance["seed"], window=window,
                          intent_provider=planner.intended_steps)
        summary = run_episode(env, comm, PerfectChannel(), recorder, metrics, max_steps)
        moves = env.unwrapped.grid_config.MOVES
    finally:
        env.close()
    runtime = time.perf_counter() - started

    # The environment must have used the instance it was given.
    if metrics.trace[0].positions != instance["starts"] or goals != instance["goals"]:
        raise RuntimeError("Environment starts or goals differ from the instance")

    distances = [goal_distances(instance["grid"], goal) for goal in goals]
    coordination, events = coordination_summary(metrics.trace, metrics.intents, recorder.actions,
                                                 goals, distances, moves)
    # In finish mode every unsolved episode runs until the step limit.
    outcome = "solved" if summary["CSR"] == 1.0 else (
        "time_limit" if summary["steps"] >= max_steps else "unfinished")
    row = {**instance_columns(instance), "topology": topology,
           "family": topology.partition("_")[0], "parameter": topology_parameter(topology),
           "max_steps": max_steps, "outcome": outcome, "error": None,
           "runtime_s": round(runtime, 4)}
    # Nested results (stall causes, native metrics, E5) stay in the trace bundle.
    row.update({key: value for key, value in summary.items()
                if key != "e5" and not isinstance(value, dict)})
    row.update(coordination)
    details = {"instance": instance, "topology": topology, "summary": summary,
               "raw": metrics.to_data(), "conflicts": events}
    return row, details


def oracle_row(instance, timeout):
    """Centralized reference on the same instance.

    oracle_solve returns None both for a timeout and for a solver failure;
    the runtime separates the two.
    """
    started = time.perf_counter()
    paths = oracle_solve(instance["grid"], instance["starts"], instance["goals"], timeout=timeout)
    runtime = round(time.perf_counter() - started, 4)
    if paths is None:
        status = "timeout" if runtime >= timeout else "failed"
        return {"oracle_status": status, "oracle_SoC": None, "oracle_makespan": None,
                "oracle_runtime_s": runtime}
    reference = oracle_metrics(paths)
    return {"oracle_status": "solved", "oracle_SoC": reference["SoC"],
            "oracle_makespan": reference["makespan"], "oracle_runtime_s": runtime}


def oracle_available():
    """Check the solver on a trivial instance before running a sweep."""
    return oracle_solve([[0, 0]], [(0, 0)], [(0, 1)], timeout=5) is not None


def as_list(value, length, key):
    """A scalar applies to every fleet size; a list pairs with n_agents by index."""
    if isinstance(value, list):
        if len(value) != length:
            raise ValueError(f"{key!r} has {len(value)} values but n_agents has {length}")
        return value
    return [value] * length


def load_config(path):
    """Read and check a config before any run starts."""
    with open(path, encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError(f"Config {path} is not a mapping")
    unknown = set(config) - CONFIG_KEYS
    if unknown:
        raise ValueError(f"Config {path} has unknown keys {sorted(unknown)}")
    for key in ("name", "kind", "maps", "n_agents", "seeds", "topologies"):
        if key not in config:
            raise ValueError(f"Config {path} is missing {key!r}")
    for key in ("n_agents", "seeds"):
        values = config[key]
        if not values or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
            raise ValueError(f"{key!r} must be a nonempty list of nonnegative integers")
    if len(set(config["seeds"])) != len(config["seeds"]):
        raise ValueError("Seeds must be distinct, or instances would be counted twice")
    for name in config["topologies"]:
        make_topology(name)
    for name in config["maps"]:
        if name not in MAP_TYPES:
            raise ValueError(f"Unknown map type {name!r}; use one of {MAP_TYPES}")
    n = len(config["n_agents"])
    config["size"] = as_list(config.get("size", 32), n, "size")
    config["max_steps"] = as_list(config.get("max_steps", 256), n, "max_steps")
    return config


def equivalence_notes(config):
    """Topologies that duplicate global communication for some fleet or map size."""
    notes = []
    for n, size in zip(config["n_agents"], config["size"]):
        for name in config["topologies"]:
            family, value = name.partition("_")[0], topology_parameter(name)
            # 2(size-1) is the largest Manhattan distance on the map.
            if family == "range" and value >= 2 * (size - 1):
                notes.append(f"{name} equals global on a {size} x {size} map")
            if family == "knn" and value >= n - 1:
                notes.append(f"{name} equals global when N = {n}")
    return notes


def software_versions():
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ("pogema", "numpy", "matplotlib", "PyYAML"):
        try:
            versions[package] = version(package)
        except Exception:
            versions[package] = None
    try:
        source = distribution("pogema").read_text("direct_url.json")
        versions["pogema_source"] = json.loads(source) if source else None
    except Exception:
        versions["pogema_source"] = None
    try:
        root = Path(__file__).resolve().parents[1]
        versions["repository_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
            check=True).stdout.strip()
    except Exception:
        versions["repository_commit"] = None
    return versions


def _run_job(job):
    """Run one job; a crash becomes an 'error' row instead of stopping the sweep."""
    instance, topology, settings = job
    try:
        return run_one(instance, topology, **settings)
    except Exception as exc:
        row = {**instance_columns(instance), "topology": topology,
               "family": topology.partition("_")[0], "parameter": topology_parameter(topology),
               "max_steps": settings["max_steps"], "outcome": "error",
               "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        return row, None


def write_csv(path, rows):
    columns = []
    for row in rows:
        columns.extend(key for key in row if key not in columns)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run_sweep(config_path, out_dir, workers=1):
    """Run every map x fleet size x seed x topology on matched instances.

    Writes, under out_dir: config.yaml (exact copy, rerunnable), metadata.json,
    instances.json, results.jsonl (one line per finished run, written as it
    goes), results.csv (all rows at the end) and optional traces/. An existing
    folder with results is never overwritten.
    """
    config = load_config(config_path)
    out_dir = Path(out_dir)
    if (out_dir / "results.jsonl").exists() or (out_dir / "results.csv").exists():
        raise FileExistsError(f"{out_dir} already has results; choose a new output folder")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.yaml").write_text(Path(config_path).read_text(encoding="utf-8"),
                                         encoding="utf-8")
    save_traces = config.get("save_traces", False)
    if save_traces:
        (out_dir / "traces").mkdir(exist_ok=True)

    notes = equivalence_notes(config)
    for note in notes:
        print(f"note: {note}")
    oracle_wanted = config.get("oracle", False)
    oracle_on = oracle_wanted and oracle_available()
    if oracle_wanted and not oracle_on:
        print("LaCAM3 is not available (set LACAM3_BINARY_PATH); oracle_status = unavailable.")
    started = datetime.now(timezone.utc).isoformat()

    instances = []
    for map_name in config["maps"]:
        for n, size, max_steps in zip(config["n_agents"], config["size"], config["max_steps"]):
            for seed in config["seeds"]:
                instances.append((make_instance(map_name, n, seed, size), max_steps))
    (out_dir / "instances.json").write_text(json.dumps(
        [{**instance_columns(inst), "max_steps": max_steps, "grid": map_string(inst["grid"]),
          "starts": inst["starts"], "goals": inst["goals"]} for inst, max_steps in instances]),
        encoding="utf-8")

    oracles = {}
    for instance, _ in instances:
        if oracle_on:
            oracles[instance["instance_id"]] = oracle_row(instance, config.get("oracle_timeout", 30))
        else:
            oracles[instance["instance_id"]] = {
                "oracle_status": "unavailable" if oracle_wanted else "disabled",
                "oracle_SoC": None, "oracle_makespan": None, "oracle_runtime_s": None}

    settings = {"window": config.get("window", 10), "obs_radius": config.get("obs_radius", 3)}
    jobs = [(instance, topology, {**settings, "max_steps": max_steps})
            for instance, max_steps in instances for topology in config["topologies"]]
    metadata = {"experiment": config["name"], "started_utc": started, "workers": workers,
                "n_instances": len(instances), "n_runs": len(jobs), "notes": notes,
                "channel": "PerfectChannel", "planner": "DCMAPFPlanner",
                "collision_system": "priority", "on_target": "finish",
                "oracle": "enabled" if oracle_on else
                          ("unavailable" if oracle_wanted else "disabled"),
                "versions": software_versions()}
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    rows = []
    executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    results = executor.map(_run_job, jobs) if executor else map(_run_job, jobs)
    try:
        with open(out_dir / "results.jsonl", "w", encoding="utf-8") as lines:
            for done, (row, details) in enumerate(results, start=1):
                row = {"experiment": config["name"], **row, **oracles[row["instance_id"]]}
                row["soc_ratio"] = (oracle_soc_ratio(row["SoC"], row["oracle_SoC"])
                                    if row.get("SoC") is not None and row["oracle_SoC"] else None)
                lines.write(json.dumps(row) + "\n")
                lines.flush()
                if save_traces and details is not None:
                    name = (f"{row['map']}_s{row['size']}_n{row['n_agents']}_seed{row['seed']}_"
                            f"{row['topology']}.json")
                    (out_dir / "traces" / name).write_text(json.dumps(details), encoding="utf-8")
                rows.append(row)
                status = row["outcome"] if row["outcome"] == "error" else f"ISR={row['ISR']}"
                print(f"[{done}/{len(jobs)}] {row['map']} {row['size']}x{row['size']} "
                      f"n={row['n_agents']} seed={row['seed']} {row['topology']}: {status}",
                      flush=True)
    finally:
        if executor:
            executor.shutdown()

    for row in rows:
        row["arrival_steps"] = json.dumps(row.get("arrival_steps"))
        row.pop("traceback", None)
    write_csv(out_dir / "results.csv", rows)
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["n_errors"] = sum(r["outcome"] == "error" for r in rows)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return rows
