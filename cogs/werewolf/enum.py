from enum import Enum, unique


@unique
class QuestionType:
    Lynch = 0
    Kill = 1
    Visit = 2
    See = 3
    Shoot = 4
    Guard = 5
    Detect = 6
    Convert = 7
    RoleModel = 8
    Hunt = 9
    HunterKill = 10
    SerialKill = 11
    Lover1 = 12
    Lover2 = 13
    Mayor = 14
    SpreadSilver = 15
    Kill2 = 16
    Sandman = 17
    Pacifist = 18
    Thief = 19
    Trouble = 20
    Chemistry = 21
    Freeze = 22
    Douse = 23


@unique
class WinType(Enum):
    Villager = 0
    Cult = 1
    Wolf = 2
    Tanner = 3
    Neutral = 4
    SerialKiller = 5
    Lovers = 6
    SKHunter = 7
    NoOne = 8
    Arsonist = 9
    Doppelganger = 10
    Sorcerer = 11


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
