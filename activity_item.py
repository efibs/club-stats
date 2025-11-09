from dataclasses import dataclass


@dataclass
class ActivityItem:
    userId: str
    type: int
    xpReward: int
    recordedAt: str