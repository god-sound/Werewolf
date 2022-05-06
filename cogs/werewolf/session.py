from __future__ import annotations

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
    def __init__(self, player: qq.Member, session: Session):
        self.member = player
        self.role: Optional[Role] = MISSING
        self.cult_leader: bool = False
        self.dead: bool = False
        self.role_model: Optional[Player] = MISSING
        self.session: Session = session

    def __repr__(self):
        return f'<Player member={self.member}, role={self.role}, cult_leader={self.cult_leader}>'

    def set_role(self, role: Role):
        self.role = role

    @property
    def name(self):
        return self.member.display_name

    async def process_aps(self):
        if not self.dead:
            seer = self.session.get_player_with_role(ROLES.Seer)[0]
            if seer.dead:
                self.role = ROLES.Seer
                await self.member.send(f"{seer.name} 曾是先知。作为学徒，你挺身而出，成为新一代先知。")
                beholder = self.session.get_player_with_role(ROLES.Beholder)[0]
                if beholder and not beholder.dead:
                    await beholder.member.send(f"{self.name} 曾是先知的学徒，现在他代替 {seer.name} 成为新一代先知。")

    async def process_wc(self):
        if not self.dead and self.role_model.dead:
            self.role = ROLES.Wolf
            wolves = self.session.get_player_with_roles(ROLES.wolf.values())
            for wolf in wolves:
                if wolf.dead:
                    continue
                await wolf.member.send(f"{self.name} 的偶像死了，他成了狼人！")
            await self.member.send(f"你的偶像 %s 死了！所以你成为了狼人！你的新队友是：\n") + '\n'.join(
                [n.member.display_name for n in wolves if not n.dead]
            )

    async def process_dg(self):
        if not self.dead and self.role_model.dead:
            self.role = self.role_model.role
            if self.role is ROLES.Mason:
                masons = self.session.get_player_with_role(ROLES.Mason)
                for mason in masons:
                    if not mason.dead:
                        await mason.member.send(f"替身 {self.name} 已变成共济会会员，一起互帮互助。")
                return await self.member.send(
                    f"你所选择的 {self.role_model.name} 已死，所以你变成了共济会会员。"
                    f"你的队友（如果有的话）是 :" + '\n'.join([n.name for n in masons if not n.dead])
                )
            if self.role is ROLES.Seer:
                beholder = self.session.get_player_with_role(ROLES.Beholder)[0]
                if beholder and not beholder.dead:
                    await beholder.member.send(f"{self.name} 曾是替身，现在他代替 {self.role_model.name} 成为新一代先知。")
            if self.role in ROLES.wolf:
                wolves = self.session.get_player_with_roles(ROLES.wolf.values())
                for wolf in wolves:
                    if wolf.dead:
                        continue
                    await wolf.member.send(f"替身 {self.name} 已变成{self.role.emoji}{self.role.name}，就像你一样。")
                return await self.member.send(
                    f"你所选择的 {self.role_model.name} 已死，所以你变成了{self.role.emoji}{self.role.name}。"
                    f"你的队友（如果有的话）是: \n" + '\n'.join([n.member.display_name for n in wolves if not n.dead])
                )
            if self.role is ROLES.Cultist:
                cultists = self.session.get_player_with_role(ROLES.Cultist)
                for cultist in cultists:
                    if cultist.dead:
                        continue
                    await cultist.member.send(f"替身 {self.name} 已变成邪教徒，就像你一样。")
                return await self.member.send(
                    f"你所选择的 {self.role_model.name} 已死，所以你变成了邪教徒。你的队友（如果有的话）是 :\n" + "\n".join(
                        [n.member.display_name for n in cultists if not n.dead]
                    )
                )
            return await self.member.send(
                f"你所选择的 {self.role_model.name} 已死，所以你变成了{self.role.emoji}{self.role.name}" +
                self.session.get_role_info(self.role)
            )


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
            player = Player(player, self)
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

    async def check_role_changes(self):
        aps = self.get_player_with_role(ROLES.ApprenticeSeer)[0]
        if aps:
            await aps.process_aps()

        wc = self.get_player_with_role(ROLES.WildChild)[0]
        if wc:
            await wc.process_wc()

        dg = self.get_player_with_role(ROLES.Doppelganger)[0]
        if dg:
            await dg.process_dg()

    def get_player_with_role(self, role: Role) -> List[Player]:
        players = [n for n in self.players.values() if n.role is role]
        return players if players else [None]

    def get_player_with_roles(self, roles: List[Role]) -> List[Player]:
        players = [n for n in self.players.values() if n.role in roles]
        return players if players else [None]

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
