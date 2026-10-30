"""Deterministic four-connected A* on a known static, borderless grid map."""

from heapq import heappop, heappush

from .communication import manhattan


def free_neighbours(grid_map, cell, blocked=()):
    """Yield free cardinal neighbours in row/column order."""
    row, col = cell
    height, width = len(grid_map), len(grid_map[0])
    for nxt in ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col)):
        r, c = nxt
        if 0 <= r < height and 0 <= c < width and not grid_map[r][c] and nxt not in blocked:
            yield nxt


def astar(grid_map, start, goal, blocked=()):
    """Return cells after start through goal, or [] at goal / when unreachable.

    Zero cells are traversable; nonzero cells are static obstacles. Temporary
    blocked cells are used only by local conflict resolution. Equal-cost paths
    break ties by row/column, independently of agent or container iteration order.
    The caller supplies a rectangular map and valid free start/goal cells.
    """
    start, goal = tuple(start), tuple(goal)
    forbidden = set(blocked)
    costs, parent = {start: 0}, {}
    frontier = [(manhattan(start, goal), 0, start)]
    while frontier:
        _, cost, cell = heappop(frontier)
        if cost != costs[cell]:
            continue
        if cell == goal:
            path = []
            while cell != start:
                path.append(cell)
                cell = parent[cell]
            return path[::-1]
        for nxt in free_neighbours(grid_map, cell, forbidden):
            if cost + 1 >= costs.get(nxt, float("inf")):
                continue
            costs[nxt], parent[nxt] = cost + 1, cell
            heappush(frontier, (cost + 1 + manhattan(nxt, goal), cost + 1, nxt))
    return []
