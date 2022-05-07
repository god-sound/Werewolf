from enum import Enum, unique


@unique
class WinType(Enum):
    Village = 0
    Cult = 1
    Wolf = 2
    Tanner = 3
    Neutral = 4
    SerialKiller = 5
    Lovers = 6
    SKHunter = 7


@unique
class KillMethod(Enum):
    Null = 0
    Lynch = 1
    Eat = 2
    Shoot = 3
    VisitWolf = 4
    VisitVictim = 5
    GuardWolf = 6
    Detected = 7
    Flee = 8
    Hunt = 9
    HunterShot = 10
    LoverDied = 11
    SerialKilled = 12
    HunterCult = 13
    GuardKiller = 14
    VisitKiller = 15
    Idle = 16
    Suicide = 17
    StealKiller = 18
    Chemistry = 19
    FallGrave = 20
    Spotted = 21
    Burn = 22
    VisitBurning = 23
