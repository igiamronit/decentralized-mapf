"""One episode loop; planning, delivery, and offline metrics remain pluggable."""

from copy import deepcopy

from .interfaces import Channel, CommunicationModel, Planner


def _active_edges(comm, positions, active):
    """Select among active robots, then map local indices to stable robot IDs.

    Preserve original ID order when compacting positions, so distance ties still
    favour the lower original ID. Filtering after selection would let finished
    robots consume k-NN neighbour slots.
    """
    agent_ids = [i for i, is_active in enumerate(active) if is_active]
    edges = comm.get_edges([positions[i] for i in agent_ids])
    return {
        agent_ids[sender]: [agent_ids[receiver] for receiver in receivers]
        for sender, receivers in edges.items()
    }


def run_episode(env, comm: CommunicationModel, channel: Channel,
                planner: Planner, metrics, max_steps: int) -> dict:
    """Run a seeded POGEMA POMAPF episode with on_target='finish'.

    metrics supplies record(t, positions, graph_stats, arrived, inboxes) and
    summary(); use a fresh recorder per episode. Records include the initial
    state and final state, so K environment steps produce K+1 records. The final
    record has no transmissions or actions. Specifications run offline.

    An optional metrics.capture_environment(infos) hook receives POGEMA wrapper
    metrics after reset/step; it only copies data, never evaluates specifications.
    Older recorders without this hook retain their original behavior.

    Optional capture_e5_round/finalize_e5 hooks observe deliveries before actions
    and close the tracker at the final timestamp; they do not steer the planner.

    Planner.reset() clears episode state; observe() receives each active robot's
    current observation and own map-relative position/goal before any compose().
    The runner never constructs a planner, changes sensing settings, or closes
    the caller's environment. Channel implementations must preserve recipient.
    """
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
        raise ValueError("max_steps must be a nonnegative integer")
    config = env.unwrapped.grid_config
    if config.observation_type != "POMAPF" or config.on_target != "finish":
        raise ValueError("The runner requires observation_type='POMAPF', on_target='finish'")
    if config.seed is None:
        raise ValueError("Set the environment's seed before running an episode")

    observations, infos = env.reset(seed=config.seed)
    capture_environment = getattr(metrics, "capture_environment", None)
    capture_e5_round = getattr(metrics, "capture_e5_round", None)
    finalize_e5 = getattr(metrics, "finalize_e5", None)
    if capture_environment is not None:
        capture_environment(infos)
    channel.reset()
    planner.reset()
    goals = [tuple(p) for p in env.unwrapped.get_targets_xy(ignore_borders=True)]
    # Recorder metadata is part of the experiment evidence. A mismatched seed
    # or goal ordering can otherwise produce plausible but mislabeled results.
    # Minimal legacy recorders without these attributes remain supported.
    if hasattr(metrics, "seed") and metrics.seed != config.seed:
        raise ValueError("Recorder seed differs from the environment seed")
    if hasattr(metrics, "goals") and [tuple(p) for p in metrics.goals] != goals:
        raise ValueError("Recorder goals differ from the environment goals")
    wait = [tuple(move) for move in config.MOVES].index((0, 0))
    finished = False

    for t in range(max_steps + 1):
        positions = [tuple(p) for p in env.unwrapped.get_agents_xy(ignore_borders=True)]
        active = [info["is_active"] for info in infos]
        edges = _active_edges(comm, positions, active)
        stats = comm.graph_stats(edges)
        inboxes = {i: [] for i in range(len(positions))}

        if t == max_steps or finished or not any(active):
            metrics.record(t, positions, stats, [], inboxes)
            if finalize_e5 is not None:
                finalize_e5(t)
            break

        for i, is_active in enumerate(active):
            if is_active:
                planner.observe(i, observations[i], positions[i], goals[i])
        outbox = {i: planner.compose(i, t) for i in edges}
        in_flight = []
        for sender, receivers in edges.items():
            if outbox[sender].sender != sender:
                raise ValueError("compose() returned a message with the wrong sender")
            for receiver in receivers:
                message = deepcopy(outbox[sender])
                message.recipient = receiver
                in_flight.append(message)

        arrived = []
        for message in channel.deliver(in_flight, t):
            if message.recipient is None or message.recipient not in inboxes:
                raise ValueError("Channel returned a message without a valid recipient")
            if active[message.recipient]:
                inboxes[message.recipient].append(message)
                arrived.append(message)

        # Capture exactly once per decision round, after all deliveries.
        if capture_e5_round is not None:
            active_ids = [
                i for i, is_active in enumerate(active) if is_active
            ]
            capture_e5_round(
                t=t,
                positions=positions,
                active=active_ids,
                broadcasts=outbox,
                inboxes=inboxes,
            )

        metrics.record(t, positions, stats, arrived, inboxes)
        actions = [
            planner.act(i, observations[i], inboxes[i], goals[i]) if active[i] else wait
            for i in range(len(positions))
        ]
        observations, _, terminated, truncated, infos = env.step(actions)
        if capture_environment is not None:
            capture_environment(infos)
        finished = all(done or timed_out for done, timed_out in zip(terminated, truncated))

    return metrics.summary()
