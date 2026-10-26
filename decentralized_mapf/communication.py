"""Communication topologies and shared statistics, independent of POGEMA."""

from .interfaces import CommunicationModel


def graph_stats(edges: dict[int, list[int]]) -> dict:
    """Measure outgoing degree and components in the undirected graph view.

    Include every robot as a key, even when it has no receivers. Receiver IDs
    must also appear as keys. Links represent a simple graph without self-links
    or duplicate receivers. An empty graph has zero components and is not
    connected; a single isolated robot is connected.
    """
    neighbours = {sender: set() for sender in edges}
    for sender, receivers in edges.items():
        for receiver in receivers:
            if receiver not in neighbours:
                raise ValueError(f"Receiver {receiver} is missing from the graph keys")
            neighbours[sender].add(receiver)
            neighbours[receiver].add(sender)

    remaining = set(neighbours)
    n_components = 0
    while remaining:
        n_components += 1
        pending = [remaining.pop()]
        while pending:
            for neighbour in neighbours[pending.pop()]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    pending.append(neighbour)

    n_agents = len(edges)
    return {
        "mean_degree": sum(len(receivers) for receivers in edges.values()) / n_agents
        if n_agents else 0.0,
        "n_components": n_components,
        "is_connected": n_components == 1,
    }


class GlobalCommunication(CommunicationModel):
    """Every robot can send to every other robot, regardless of distance."""

    def get_edges(self, positions: list[tuple[int, int]]) -> dict[int, list[int]]:
        return {
            sender: [receiver for receiver in range(len(positions)) if receiver != sender]
            for sender in range(len(positions))
        }

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        return graph_stats(edges)


class NoCommunication(CommunicationModel):
    """No messages between robots; local sensing remains a separate setting."""

    def get_edges(self, positions: list[tuple[int, int]]) -> dict[int, list[int]]:
        return {sender: [] for sender in range(len(positions))}

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        return graph_stats(edges)

def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Calculate Manhattan distance between two grid positions."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class RangeCommunication(CommunicationModel):
    """Allow communication between robots within Manhattan distance r."""

    def __init__(self, r: float):
        if (
            isinstance(r, bool)
            or not isinstance(r, (int, float))
            or not r >= 0
        ):
            raise ValueError("r must be a nonnegative number")
        self.r = r

    def get_edges(
        self, positions: list[tuple[int, int]]
    ) -> dict[int, list[int]]:
        return {
            sender: [
                receiver
                for receiver in range(len(positions))
                if receiver != sender
                and manhattan(positions[sender], positions[receiver])
                <= self.r
            ]
            for sender in range(len(positions))
        }

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        return graph_stats(edges)


class KNNCommunication(CommunicationModel):
    """Each robot sends to its k nearest robots by Manhattan distance."""

    def __init__(self, k: int):
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k must be a nonnegative integer")
        self.k = k

    def get_edges(
        self, positions: list[tuple[int, int]]
    ) -> dict[int, list[int]]:
        return {
            sender: [
                receiver
                for _, receiver in sorted(
                    (
                        manhattan(
                            positions[sender], positions[receiver]
                        ),
                        receiver,
                    )
                    for receiver in range(len(positions))
                    if receiver != sender
                )[:self.k]
            ]
            for sender in range(len(positions))
        }

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        return graph_stats(edges)
