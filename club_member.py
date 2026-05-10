from dataclasses import dataclass

from member import Member


@dataclass
class ClubMember:
    user: Member