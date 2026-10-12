"""Shared contracts from section 3 of docs/TEAM_BUILD_GUIDE.md.

Keep field names and method signatures stable so teammates can build independently.
This module depends only on Python's standard library, not on POGEMA.

Shared coordinates are map-relative (row, column), with no POGEMA border padding.
POGEMA's start-relative observations need conversion before use in messages.
"""

from dataclasses import dataclass, field


@dataclass
class Message:
    """One robot's position, goal, intended next cells, and sending timestep.

    Each message has its own next_cells list. Sender is a stable robot ID.
    The runner sets recipient on each transmission; compose() can leave it None.
    """

    sender: int
    position: tuple[int, int]
    goal: tuple[int, int]
    next_cells: list[tuple[int, int]] = field(default_factory=list)
    sent_at: int = 0
    recipient: int | None = None


@dataclass
class StepRecord:
    """One timestep's evidence for offline metrics and specification monitors.

    positions[i] belongs to robot i. inbox_senders records actual delivery,
    rather than the neighbours that could potentially send. n_messages counts
    delivered transmissions, and max_age is the largest t - sent_at delivered
    at this timestep (zero when no messages arrive).
    """

    t: int
    positions: list[tuple[int, int]]
    mean_degree: float
    n_components: int
    n_messages: int
    inbox_senders: dict[int, list[int]]
    max_age: int = 0


class CommunicationModel:
    """Deterministic communication topology; channel randomness lives elsewhere."""

    def get_edges(self, positions: list[tuple[int, int]]) -> dict[int, list[int]]:
        """Return {sender_id: [receiver_ids]}; links may be asymmetric.

        positions[i] is robot i's position. Concrete models implement the link
        selection rule. This method does not create or deliver messages.
        """
        raise NotImplementedError

    def graph_stats(self, edges: dict[int, list[int]]) -> dict:
        """Return mean_degree, n_components, and is_connected.

        Mean degree counts outgoing links. For component/connectivity analysis,
        use the undirected view of the graph, including isolated robots.
        """
        raise NotImplementedError


class Channel:
    """Delivery interface; the base channel passes everything through unchanged.

    Future channel implementations can drop or delay transmissions while keeping
    the same interface. This base class has no queue or random state.
    """

    def deliver(self, messages: list[Message], t: int) -> list[Message]:
        """Return messages arriving at timestep t; preserve their sending times."""
        return messages

    def reset(self) -> None:
        """Clear episode-specific delivery state; the base channel has none."""
        pass


class Planner:
    """Robot decision interface shared by all communication topologies.

    A concrete planner uses its observation, inbox, and goal. It must support an
    empty inbox and must not branch on which topology produced that inbox.
    """

    def reset(self) -> None:
        """Clear episode-specific state; override if the planner keeps caches."""
        pass

    def observe(self, agent_id: int, observation, position: tuple[int, int],
                goal: tuple[int, int]) -> None:
        """Update this robot's local state before compose(), without taking action.

        position and goal use shared map coordinates; observation stays in
        POGEMA's original frame. Only this robot's state is supplied here.
        Override to refresh positions and intended paths used by compose().
        """
        pass

    def act(self,
            agent_id: int,
            observation,
            inbox: list[Message],
            goal: tuple[int, int]) -> int:
        """Return one POGEMA action for this robot, including when inbox is empty."""
        raise NotImplementedError

    def compose(self, agent_id: int, t: int) -> Message:
        """Return this robot's outgoing payload, stamped with sending timestep t."""
        raise NotImplementedError
