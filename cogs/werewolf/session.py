import asyncio
import random
from typing import List, Dict, Optional, Union

import qq

__all__ = (
    "Player",
    "Session"
)

from qq.ext import commands
from qq.utils import MISSING, get, find

from cogs.werewolf.roles import ROLES, Role


class Player:
    def __init__(self, player: qq.Member):
        self.member = player
        self.role: Optional[Role] = MISSING
        self.cult_leader: bool = False
        self.dead: bool = False

    def __repr__(self):
        return f'<Player member={self.member}, role={self.role}, cult_leader={self.cult_leader}>'

    def set_role(self, role: Role):
        self.role = role


class Setting:
    min_players: int = 8
    game_join_time: int = 120
    disabled_role: int = 0
    burning_overkill: bool = True
    thief_full: bool = False


class Session:

    def __init__(
            self,
            ctx: commands.Context,
            chaos: bool
    ):
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.ctx = ctx
        self.players: Dict[int, Player] = {}
        self.is_joining: bool = True
        self.is_running: bool = False
        self.force_start: bool = False
        self.join_time: int = 120
        self.setting: Setting = Setting()
        self.chaos: bool = chaos
        self.day: int = 0
        self.night: bool = True

    def join(self, player: Union[qq.Member, Player]):
        if not isinstance(player, Player):
            player = Player(player)
        self.players[player.member.id] = player

    def leave(self, player: qq.Member):
        if player.id in self.players:
            return False
        self.players.pop(player.id)

    async def main_game_loop(self):
        while True:
            if self.force_start:
                break
            if self.join_time in [10, 30, 60]:
                if self.join_time == 60:
                    await self.ctx.send("还有 1 分钟")
                else:
                    await self.ctx.send("还剩 %d 秒" % self.join_time)
            if self.join_time:
                self.join_time -= 1
                await asyncio.sleep(1)
            else:
                break
        self.is_joining = False

        await asyncio.sleep(2)
        if self.player_count < self.setting.min_players:
            return await self.ctx.send("人数不足，游戏取消。")
        await self.ctx.send("游戏启动中，正在分配角色及更新数据库，请稍等片刻。")

        self.is_running = True
        self.assign_role()
        await self.notify_roles()

        while self.is_running:
            self.day += 1

    async def check_role(self):
        pass

    def get_player_with_role(self, role: Role) -> List[Player]:
        return [n for n in self.players.values() if n.role is role and not n.dead]

    @property
    def player_count(self) -> int:
        return len(self.players)
        # return 16

    @property
    def player_list_string(self) -> str:
        if not self.is_joining:
            return ""
        players = "\n".join([m.member.mention for n, m in self.players.items()])
        return f'玩家: {self.player_count}\n{players}'

    def is_disabled(self, role: Role) -> bool:
        return not not (self.setting.disabled_role & (1 << role.bit))

    def assign_role(self) -> None:
        role_to_assign = self.balance()
        player = list(self.players.values())

        random.shuffle(role_to_assign)
        random.shuffle(player)
        for ply, role in zip(player, role_to_assign):
            ply.set_role(role)

        for ply in self.players.values():
            ply.cult_leader = ply.role == ROLES.Cultist

    def balance(self) -> List[Role]:
        role_to_assign = self.get_role_list()
        if self.player_count > len(role_to_assign):
            role_to_assign += [ROLES.Villager] * (self.player_count - len(role_to_assign))
        count = 0
        while True:
            count += 1
            roles = random.choices(role_to_assign, k=self.player_count)
            if count >= 500:
                break
            pointless_role = [x for x in roles if
                              x in [ROLES.Traitor, ROLES.SnowWolf, ROLES.Sorcerer]]

            if pointless_role and ROLES.Wolf not in roles:
                roles[roles.index(pointless_role[0])] = ROLES.Wolf

            if (
                    ROLES.Cultist in roles and
                    ROLES.CultistHunter not in roles and
                    not self.is_disabled(ROLES.CultistHunter)
            ):
                if ROLES.Villager in roles:
                    roles[roles.index(ROLES.Villager)] = ROLES.CultistHunter
                else:
                    roles[roles.index(ROLES.Cultist)] = ROLES.Villager

            if (
                    not self.setting.burning_overkill and
                    ROLES.Arsonist in roles and
                    ROLES.SerialKiller in roles
            ):
                roles[roles.index(ROLES.Arsonist)] = ROLES.Villager

            if ROLES.ApprenticeSeer in roles and ROLES.Seer not in roles:
                roles[roles.index(ROLES.ApprenticeSeer)] = ROLES.Seer

            villagers = [x for x in roles if x in ROLES.not_evil_list]
            baddies = [x for x in roles if x in ROLES.evil_list]
            if not (villagers and baddies):
                continue

            if len(villagers) < len(baddies):
                continue

            if self.chaos:
                break

            villager_strength = sum([n.strength for n in villagers])
            enemy_strength = sum([n.strength for n in baddies])
            variance = self.player_count // 4 + 1
            if abs(villager_strength - enemy_strength) <= variance:
                break
        return roles

    def get_role_list(self) -> List[Role]:
        possible_wolf = [n for m, n in ROLES.wolf.items() if not self.is_disabled(n)]
        role_to_assign: List[Role] = []

        wolf_count = min(max(self.player_count // 5, 1), 5)
        if wolf_count == 1:
            if ROLES.SnowWolf in possible_wolf:
                possible_wolf.remove(ROLES.SnowWolf)
        for n in range(wolf_count):
            role = random.choice(possible_wolf)
            if role is not ROLES.Wolf:
                possible_wolf.remove(role)
            role_to_assign.append(role)

        for name, role in ROLES.not_wolf.items():
            if self.is_disabled(role):
                continue
            if role is ROLES.Cultist:
                if self.player_count > 10:
                    role_to_assign.append(role)
                continue
            role_to_assign.append(role)

        if not self.is_disabled(ROLES.Mason):
            role_to_assign.append(ROLES.Mason)
            role_to_assign.append(ROLES.Mason)

        if ROLES.CultistHunter in role_to_assign and not self.is_disabled(ROLES.Cultist):
            role_to_assign.append(ROLES.Cultist)
            role_to_assign.append(ROLES.Cultist)

        for n in range(self.player_count // 4):
            role_to_assign.append(ROLES.Villager)

        return role_to_assign

    async def notify_roles(self) -> None:
        for ply in self.players.values():
            if ply.role is MISSING:
                continue
        for ply in self.players.values():
            await ply.member.send(self.get_role_info(ply.role))

    def get_role_info(self, role: Role) -> str:
        if role is ROLES.Thief:
            return role.desc[1] if self.setting.thief_full else role.desc[0]
        msg = random.choice(role.desc)
        if role is ROLES.Beholder:
            seer = get(self.players.values(), role=ROLES.Seer)
            if seer:
                msg += "\n%s 是先知。" % seer.member.display_name
            else:
                msg += "\n这局没有先知！"
        if role is ROLES.Mason:
            msg += "\n其他共济会会员是：\n" + '\n'.join(
                [n.member.display_name for n in self.players.values() if n.role is ROLES.Mason]
            )
        if role in ROLES.wolf.values():
            msg += "\n当前狼群：\n" + '\n'.join(
                [n.member.display_name for n in self.players.values() if n.role in ROLES.wolf.values()]
            )
        if role is ROLES.Cultist:
            msg += "\n目前邪教教会成员: \n" + '\n'.join(
                [n.member.display_name for n in self.players.values() if n.role is ROLES.Cultist]
            )
        return msg


# if __name__ == '__main__':
    #     import timeit
    #     number = 10000
    #     time = timeit.timeit(
    #         'sess.assign_role()',
    #         setup='''from __main__ import Session, Player, random
    #
    # class Dummy:
    #     @property
    #     def id(self):
    #         return random.randint(0, 65565)
    #
    #     def __repr__(self):
    #         return "<Dummy>"
    #
    # sess = Session(False)
    # for n in range(16):
    #     d = Dummy()
    #     p = Player(d)
    #     sess.join(p)
    # ''',
    #         number=number
    #     )
    #     print(time / number * 1000, 'ms per')

    # class Dummy:
    #     @property
    #     def id(self):
    #         return random.randint(0, 65565)
    #
    #     @property
    #     def display_name(self):
    #         return 'Bob_' + str(self.id)
    #
    #     def __repr__(self):
    #         return "<Dummy>"
    #
    #
    # sess = Session(True)
    # for n in range(16):
    #     d = Dummy()
    #     p = Player(d)
    #     sess.join(p)
    # sess.assign_role()
