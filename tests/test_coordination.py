"""Hand-built traces with known conflicts, responses, delays and blocked moves."""

from decentralized_mapf import StepRecord
from decentralized_mapf.coordination import (blocked_moves, conflict_events,
                                             coordination_summary, goal_distances, respond)

MOVES = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]
WAIT, LEFT, RIGHT = 0, 3, 4
CORRIDOR = [[0, 0, 0, 0, 0]]


def row(t, positions, heard):
    return StepRecord(t, positions, 1.0, 1, sum(map(len, heard.values())), heard)


def test_goal_distances_go_around_walls():
    grid = [[0, 1, 0],
            [0, 0, 0]]
    assert goal_distances(grid, (0, 2)) == {(0, 2): 0, (1, 2): 1, (1, 1): 2,
                                            (1, 0): 3, (0, 0): 4}


def test_responses_follow_distance_change():
    distances = goal_distances(CORRIDOR, (0, 0))
    assert respond((0, 2), (0, 1), (0, 2), distances) == "wait"
    assert respond((0, 2), (0, 1), (0, 1), distances) == "proceed"
    assert respond((0, 2), (0, 1), (0, 3), distances) == "retreat"
    open_grid = [[0, 0], [0, 0]]
    # Claimed (0,0) via (0,1); stepping down to (1,0) is another shortest road.
    assert respond((1, 1), (0, 1), (1, 0), goal_distances(open_grid, (0, 0))) == "detour"


def test_head_on_swap_records_both_sides():
    goals = [(0, 4), (0, 0)]
    distances = [goal_distances(CORRIDOR, goal) for goal in goals]
    trace = [row(0, [(0, 1), (0, 2)], {0: [1], 1: [0]}),
             row(1, [(0, 1), (0, 3)], {0: [], 1: []})]
    intents = {0: {0: (0, 2), 1: (0, 1)}}
    actions = {0: {0: WAIT, 1: RIGHT}}

    events = conflict_events(trace, intents, actions, goals, distances, MOVES)
    assert [(e["agent"], e["blocker"], e["has_priority"], e["response"]) for e in events] == [
        (0, 1, True, "wait"), (1, 0, False, "retreat")]
    assert all(e["heard"] and e["heard_back"] and not e["rejected"] for e in events)


def test_unheard_blocker_and_rejected_move():
    goals = [(0, 4), (0, 0)]
    distances = [goal_distances(CORRIDOR, goal) for goal in goals]
    trace = [row(0, [(0, 1), (0, 2)], {0: [], 1: []}),
             row(1, [(0, 1), (0, 2)], {0: [], 1: []})]
    intents = {0: {0: (0, 2), 1: (0, 1)}}
    actions = {0: {0: RIGHT, 1: LEFT}}

    events = conflict_events(trace, intents, actions, goals, distances, MOVES)
    assert all(e["response"] == "proceed" and e["rejected"] and not e["heard"] for e in events)
    assert blocked_moves(trace, actions, MOVES) == 2


def test_summary_counts_and_first_arrival_delay():
    goals = [(0, 4), (0, 0)]
    distances = [goal_distances(CORRIDOR, goal) for goal in goals]
    # Robot 1 holds its cell once, blocking robot 0, then walks two cells: delay 1.
    # Robot 0 never arrives.
    trace = [row(0, [(0, 3), (0, 2)], {0: [1], 1: [0]}),
             row(1, [(0, 3), (0, 2)], {0: [], 1: []}),
             row(2, [(0, 3), (0, 1)], {0: [], 1: []}),
             row(3, [(0, 3), (0, 0)], {0: [], 1: []})]
    intents = {0: {0: (0, 2), 1: (0, 2)}, 1: {0: (0, 3), 1: (0, 1)}, 2: {0: (0, 3), 1: (0, 0)}}
    actions = {0: {0: WAIT, 1: WAIT}, 1: {0: WAIT, 1: LEFT}, 2: {0: WAIT, 1: LEFT}}

    summary, events = coordination_summary(trace, intents, actions, goals, distances, MOVES)
    assert summary["arrival_steps"] == [None, 3]
    assert (summary["delay_mean"], summary["delay_max"]) == (1, 1)
    assert summary["n_conflicts"] == 1 and summary["n_wait_heard"] == 1
    assert summary["n_blocked_moves"] == 0
