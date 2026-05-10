from dataclasses import dataclass

from club_member import ClubMember


@dataclass
class Club:
    name: str
    tag: str
    members: list[ClubMember]