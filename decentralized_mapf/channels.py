"""Message delivery channels, independent of topology and robot observations."""

from .interfaces import Channel


class PerfectChannel(Channel):
    """Deliver every supplied transmission immediately, in its original order.

    Inherits Channel's pass-through deliver() and stateless reset(). No messages
    are copied, dropped, delayed, or deduplicated; sent_at remains unchanged.
    Recipient routing belongs to the episode runner, not the channel.
    """
