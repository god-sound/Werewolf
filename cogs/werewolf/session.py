from __future__ import annotations

import asyncio
import datetime
import random
from typing import List, Dict, Optional, Union, TYPE_CHECKING

import qq

__all__ = (
    "Player",
    "Session"
)

from qq.ext import commands
from qq.utils import MISSING, get

from cogs.werewolf.enum import WinType, KillMethod, QuestionType
from cogs.werewolf.roles import ROLES, Role

if TYPE_CHECKING:
    from cogs.werewolf import Werewolf

WOLF_ROLES = [ROLES.Wolf, ROLES.AlphaWolf, ROLES.WolfCub, ROLES.Lycan]


class Player:
    def __init__(self, player: qq.Member, session: Session):
        self.member = player
        self.role: Optional[Role] = MISSING
        self.cult_leader: bool = False
        self.dead: bool = False
        self.died_last_night: bool = False
        self.win: bool = False
        self.bitten: bool = False
        self.role_model: Optional[Player] = MISSING
        self.in_love: Optional[Player] = MISSING
        self.session: Session = session
        self.changed_role_count = 0
        self.time_died: Optional[int] = 0
        self.bullet: int = 2
        self.current_questions: Optional[str] = None
        self.choice: int = 0
        self.drunk: bool = False
        self.kill_by_role: Optional[Role] = MISSING
        self.kill_method: Optional[KillMethod] = MISSING
        self.final_shot_delay: Optional[KillMethod] = MISSING
        self.converted_to_cult: bool = False
        self.flee: bool = False
        self.used_ability: bool = False
        self.doused: bool = False

    def __repr__(self):
        return f'<Player member={self.member}, role={self.role}, cult_leader={self.cult_leader}>'

    def set_role(self, role: Role):
        self.role = role

    @property
    def name(self):
        return self.member.display_name

    @property
    def role_description(self) -> str:
        return f"{self.name}是个{self.role.emoji}{self.role.name}"

    async def process_aps(self):
        if not self.dead:
            seer = self.session.get_player_with_role(ROLES.Seer)[0]
            if seer.dead:
                self.role = ROLES.Seer
                self.changed_role_count += 1
                await self.member.send(f"{seer.name} 曾是先知。作为学徒，你挺身而出，成为新一代先知。")
                beholder = self.session.get_survived_player_with_role(ROLES.Beholder)
                if beholder and not beholder.dead:
                    await beholder.member.send(f"{self.name} 曾是先知的学徒，现在他代替 {seer.name} 成为新一代先知。")

    async def process_wc(self):
        if not self.dead and self.role_model.dead:
            self.role = ROLES.Wolf
            self.changed_role_count += 1
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
            self.changed_role_count += 1
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
                beholder = self.session.get_survived_player_with_role(ROLES.Beholder)
                if beholder:
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
    night_time: int = 120


class Session:

    def __init__(
            self,
            ctx: commands.Context,
            chaos: bool,
            cog: Werewolf
    ):
        self.cog = cog
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.ctx = ctx
        self.bot: commands.Bot = ctx.bot
        self.players: Dict[int, Player] = {}
        self.is_joining: bool = True
        self.is_running: bool = False
        self.force_start: bool = False
        self.wolf_cub_killed: bool = True
        self.sandman_sleep: bool = False
        self.silver_spread: bool = False
        self.join_time: int = 120
        self.setting: Setting = Setting()
        self.chaos: bool = chaos
        self.day: int = 0
        self.night: bool = True
        self.end_time: Optional[datetime.datetime] = MISSING
        self.start_time: Optional[datetime.datetime] = MISSING

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
        self.start_time = datetime.datetime.now()

        await asyncio.sleep(2)
        if self.player_count < self.setting.min_players:
            return await self.ctx.send("人数不足，游戏取消。")
        await self.ctx.send("游戏启动中，正在分配角色及更新数据库，请稍等片刻。")

        self.is_running = True
        self.assign_role()
        await self.notify_roles()

        while self.is_running:
            self.day += 1
            await self.check_role_changes()

    async def night_loop(self):
        self.night = True
        if not self.is_running or self.check_game_end(True):
            return
        for p in self.players.values():
            p.choice = 0
            p.choice2 = 0
            p.current_question = MISSING
            p.votes = 0
            p.died_last_night = False
            p.being_visited_same_night_count = 0
            if p.bitten:
                p.bitten = False
                if not p.dead and p.role not in WOLF_ROLES + ROLES.SnowWolf:
                    if p.role == ROLES.Cultist:
                        for cultist in [n for n in self.alive_players if n.role == ROLES.Cultist]:
                            await cultist.member.send(f"奇怪，当你们决定今晚让谁入会时，邪教徒{p.name}好像不在家。")
                    p.role = ROLES.Wolf
                    await p.member.send("现在你已经是🐺狼人了!")
                    wolfs = self.get_survived_player_with_roles(WOLF_ROLES + ROLES.SnowWolf)
                    await p.member.send("当前狼群:" + ', '.join([n.name for n in wolfs]))
                    await self.check_role_changes()
        if self.check_game_end():
            return
        night_time = self.setting.night_time
        if self.sandman_sleep:
            self.sandman_sleep = False
            self.silver_spread = False
            self.wolf_cub_killed = False
            for player in self.players:
                player.drunk = False
            await self.ctx.send(
                "💤奇怪，天怎么突然这么黑，好像也停电了，火也点不燃，该回家睡觉了"
                "，今晚注定是个宁静的夜晚。今晚没有人会活动"
            )
            return

        await self.ctx.send(
            "夜幕降临，人们都活在恐惧中，彻夜难眠。这漫长的夜晚竟然有 %s 秒！\n"
            "请所有夜晚（主动）行动的角色，私聊机器人以使用自己能力。" % night_time
        )
        await self.ctx.send(self.player_list_string)

    async def check_game_end(self, check_bitten=False):
        if self.is_running:
            return True
        survivor = self.alive_players
        if all(n.role not in WOLF_ROLES for n in survivor):
            if not check_bitten or all(not n.bitten for n in survivor):
                return False
            snow_wolf = self.get_survived_player_with_role(ROLES.SnowWolf)
            if snow_wolf:
                snow_wolf.role = ROLES.Wolf
                snow_wolf.changed_role_count += 1
                await snow_wolf.member.send("你似乎是最后的狼了，为了生存，你不得不变成了只普通🐺狼人。")
            else:
                traitor = self.get_survived_player_with_role(ROLES.Traitor)
                if traitor:
                    traitor.role = ROLES.Wolf
                    traitor.changed_role_count += 1
                    await traitor.member.send("现在你已经成为狼人了，你这个叛徒！！！")
        if not survivor:
            return self.end(WinType.NoOne)
        elif len(survivor) == 1:
            p = survivor[0]
            if p.role in [ROLES.Tanner, ROLES.Sorcerer, ROLES.Thief, ROLES.Doppelganger]:
                return self.end(WinType.NoOne)
            else:
                return self.end(p.role.party)
        elif len(survivor) == 2:
            if all(n.in_love for n in survivor):
                return await self.end(WinType.Lovers)
            if all(n in [ROLES.Tanner, ROLES.Sorcerer, ROLES.Thief, ROLES.Doppelganger] for n in survivor):
                return self.end(WinType.NoOne)
            if any(n.role is ROLES.Hunter for n in survivor):
                other = [n for n in survivor if n.role != ROLES.Hunter]
                if not other:
                    return await self.end(WinType.Village)
                else:
                    other = other[0]
                if other.role is ROLES.SerialKiller:
                    return await self.end(WinType.SKHunter)
                if other.role in WOLF_ROLES:
                    hunter = get(survivor, role=ROLES.Hunter)
                    if random.random() >= 0.5:
                        await self.ctx.send(
                            f"半夜，{hunter.name}拿着枪准备跑出去练枪法，却看见{other.name}正在大嚼特嚼……于是猎人熟练的关保险、"
                            f"上膛、瞄准。啪~【狼人🐺】被打死了。"
                        )
                        return await self.end(WinType.Village)
                    else:
                        await self.ctx.send(
                            f"知道只剩 🎯猎人{hunter.name} 了,🐺狼人 {other.name} 找到了一个好时机，趁机杀死了 {hunter.name}。 #狼人胜"
                        )
                        return await self.end(WinType.Wolf)
            if any(n.role is ROLES.SerialKiller for n in survivor):
                return self.end(WinType.SerialKiller)
            if any(n.role is ROLES.Arsonist for n in survivor):
                return self.end(WinType.Arsonist)
            if any(n.role is ROLES.Cultist for n in survivor):
                other = [n for n in survivor if n.role != ROLES.Cultist]
                if not other:
                    return await self.end(WinType.Cult)
                else:
                    other = other[0]
                if other.role in WOLF_ROLES:
                    return self.end(WinType.Wolf)
                if other.role is ROLES.CultistHunter:
                    cultist = get(survivor, role=ROLES.Cultist)
                    await cultist.member.send(
                        f"最后，村里只剩💂邪教捕手{other.name} 和 👤邪教徒 {cultist.name} 了..."
                        f"可惜 {cultist.name} 最后的邪教仪式，还是被 {other.name} 发现了... #村民胜 "
                    )
                    await self.kill_player(cultist, KillMethod.HunterCult, other)
                    return self.end(WinType.Villager)
                other.converted_to_cult = True
                other.role = ROLES.Cultist
                return self.end(WinType.Cult)
        elif len(survivor) == 3:
            if all(n in [ROLES.Tanner, ROLES.Sorcerer, ROLES.Thief, ROLES.Doppelganger] for n in survivor):
                return self.end(WinType.NoOne)

        if any(n.role.party in [ROLES.SerialKiller, ROLES.Arsonist] for n in survivor):
            return False
        if all(x.role.party == ROLES.Cultist for x in survivor):
            return self.end(WinType.Cult)

        wolfs = [n for n in survivor if n.role in ROLES.Wolf]
        others = [n for n in survivor if n.role not in ROLES.Wolf]
        if wolfs > others:
            gunner = get(survivor, role=ROLES.Gunner)
            if (
                    gunner and gunner.bullet > 0 and
                    (
                            len(wolfs) == len(others) or
                            (len(wolfs) == len(others) + 1 and len([n for n in wolfs if n.in_love]) == 2)
                    )
            ):
                return False
            return self.end(WinType.Wolf)
        if all(
                n.role not in [
                    ROLES.SnowWolf, ROLES.Cultist, ROLES.SerialKiller, ROLES.Arsonist
                ] + WOLF_ROLES for n in survivor
        ):
            if not check_bitten or all(n.bitten for n in survivor):
                return self.end(WinType.Villager)
        return False

    async def kill_player(
            self,
            p: Player,
            kill_method: KillMethod,
            killer: Optional[Player] = None,
            is_night: bool = True,
            hunter_final_shot: bool = True,
    ):
        p.died_last_night = is_night and kill_method != KillMethod.LoverDied
        p.time_died = self.day
        if killer:
            p.kill_by_role = killer.role
        p.dead = True
        p.kill_method = kill_method
        if p.in_love and not p.in_love.dead:
            if not is_night:
                await self.ctx.send(
                    f"当看到 {p.in_love.name} 倒在血泊中时， {p.name} 不敢相信眼前发生的一切，撕吼着急急冲到他身边，可他已经断气..."
                    f"{p.name} 顿时崩溃了，整个人像被掏空一样，趴在另一半身上恸哭不止。"
                    f"最后他实在无法承受失去另一半的痛苦，找到一把枪自杀了。{p.role_description}"
                )
            await self.kill_player(p.in_love, KillMethod.LoverDied, p, is_night=is_night)
            await self.check_role_changes()

        if p.role is ROLES.WolfCub:
            self.wolf_cub_killed = True
        if p.role is ROLES.Hunter:
            if hunter_final_shot and kill_method:
                await self.hunter_final_shot(p, kill_method, delay=is_night)
                pass

    async def send_night_action(self):
        if not self.players:
            return
        for p in self.players.values():
            p.current_questions = None
            p.choice = 0
            msg = ""
            targets = []
            q_type = QuestionType.Trouble
            target_base = [n for n in self.players.values() if not n.dead and not n.drunk]
            if p.role is ROLES.SerialKiller:
                targets = target_base
                msg = "今晚你想杀掉谁？"
                q_type = QuestionType.SerialKill
            elif p.role is ROLES.Harlot:
                targets = target_base
                msg = "你打算去谁家？"
                q_type = QuestionType.Visit
            elif p.role in [ROLES.Fool, ROLES.Seer, ROLES.Sorcerer, ROLES.Oracle]:
                targets = target_base
                msg = "你想占卜谁的身份？"
                q_type = QuestionType.See
            elif p.role is ROLES.GuardianAngel:
                targets = target_base
                msg = "你想守护谁？"
                q_type = QuestionType.Guard
            elif p.role in WOLF_ROLES:
                if self.silver_spread:
                    break
                targets = [n for n in target_base if n.role not in WOLF_ROLES and n.role != ROLES.SnowWolf]
                other = self.get_survived_player_with_roles(WOLF_ROLES)
                msg = "你想要吃掉谁？\n" + "请确定你已与 %s 商量。" % ", ".join([n.name for n in other])
                q_type = QuestionType.Kill
            elif p.role is ROLES.Cultist:
                targets = [n for n in target_base if n.role != ROLES.Cultist]
                other = self.get_survived_player_with_roles([ROLES.Cultist])
                msg = "你想为谁施洗？\n" + "请确定你已与 %s 商量。" % ", ".join([n.name for n in other])
                q_type = QuestionType.Convert
            elif p.role is ROLES.CultistHunter:
                targets = target_base
                msg = "你想审判谁？"
                q_type = QuestionType.Hunt
            elif p.role is ROLES.WildChild:
                if self.day == 1:
                    targets = target_base
                    msg = "你想成为谁的追随者？"
                    q_type = QuestionType.RoleModel
                else:
                    p.choice = -1
            elif p.role is ROLES.Doppelganger:
                if self.day == 1:
                    targets = target_base
                    msg = "你希望哪个玩家死后，自己可以变成他？"
                    q_type = QuestionType.RoleModel
                else:
                    p.choice = -1
            elif p.role is ROLES.Cupid:
                if self.day == 1:
                    targets = target_base
                    msg = "你想让哪两个玩家成为情侣？请选择第一个玩家"
                    q_type = QuestionType.Lover1
                else:
                    p.choice = -1
            elif p.role is ROLES.Thief:
                if self.day == 1 or self.setting.thief_full:
                    targets = target_base
                    msg = "你想偷谁的能力?"
                    q_type = QuestionType.Thief
                else:
                    p.choice = -1
            elif p.role is ROLES.Chemist:
                if p.used_ability:
                    targets = target_base
                    msg = "今晚你想和谁进行博弈？"
                    q_type = QuestionType.Chemistry
                else:
                    p.used_ability = False
                    p.choice = -1
                    await p.member.send("夜深人静，疯狂的化学家开始制药了，希望不被人发现。")
            elif p.role is ROLES.SnowWolf:
                if not self.silver_spread:
                    targets = target_base
                    msg = "你想冻结谁的能力？"
                    q_type = QuestionType.Freeze
            elif p.role is ROLES.Arsonist:
                targets = [n for n in target_base if not n.doused]
                msg = "今天你想浇汽油，还是放一把火，烧掉你曾经浇过汽油的房子？"
                q_type = QuestionType.Douse
            else:
                continue

            if p.drunk or not msg:
                p.choice = -1
                continue

            await self.cog.send_menu([n.name for n in targets], targets, p.member, msg, q_type)

    async def hunter_final_shot(self, hunter: Player, kill_method: KillMethod, delay: bool = False):
        if delay:
            hunter.final_shot_delay = kill_method
            return
        target = self.alive_players
        random.shuffle(target)

        if kill_method == KillMethod.Lynch:
            msg = "村民们决定要处死你！这是你最后的机会，快！选择一名玩家和你陪葬吧！你有三十秒"
        else:
            msg = "你被谋杀了！ 在你的最后时刻，你有机会射杀某人……快点！你有三十秒"
        msg += '\n可用的目标：\n' + '-1: 跳过\n' + '\n'.join(f"{idx}: {ply.name}" for idx, ply in enumerate(target))
        msg += '\n发送你要射杀那个人的ID！或者输入 -1 来跳过。'

        def check(message: qq.Message):
            return (
                    message.author == hunter.member and
                    message.content.isnumeric() and
                    int(message.content) <= len(target)
            )

        choice = None
        hunter.dead = True
        try:
            choice = await self.bot.wait_for('message', check=check, timeout=30)
        except asyncio.TimeoutError:
            pass

        if choice is None:
            if kill_method == KillMethod.Lynch:
                await self.ctx.send(
                    f"当绳索快套紧{hunter.name}的脖子时，他摸索着手枪想杀个人来陪葬，但却慢了一步，因为颈部清脆的断裂声已经响起..."
                )
            else:
                await self.ctx.send(
                    f"似乎对{hunter.name}的打击太大了，以至于他们甚至无法伸手去拿自己的武器，躺在血泊中……"
                )
        elif choice == -1:
            if kill_method == KillMethod.Lynch:
                await self.ctx.send(
                    f"{hunter.name}看着围观的一群愚民，拔出手枪，想找人陪葬。最终他没有扣下扳机，而是选择接受上天的安排，坦然面对死亡..."
                )
            else:
                await self.ctx.send(
                    f"{hunter.name} 躺在地上，还剩下最后一口气，原本还有机会射杀一人来陪葬，"
                    f"他却放弃了……他决定听天由命……"
                )
        else:
            killed = target[choice]
            if killed.role is ROLES.WiseElder:
                await self.ctx.send(
                    f"🎯猎人{hunter.name} 向长老 {killed.name}开枪 ，但很快就后悔了，"
                    f"因此{killed.name}放弃了他的身份，成为了一位普通村民。"
                )
                killed.role = ROLES.Villager
                killed.changed_role_count += 1
                return
            if kill_method == KillMethod.Lynch:
                await self.ctx.send(
                    f"绳索套上 {hunter.name} 的脖子时，不甘被处死的他想找人陪葬，他迅速掏出一把枪，瞄准某处，扣动扳机，"
                    f"只见 {killed.name} 满脸讶然之色，缓缓倒在地上。 {killed.name} 当场死亡。 {killed.role_description}"
                )
            else:
                await self.ctx.send(
                    f"{hunter.name}倒在地上快死了…… 但最后一刻他抓住了他的手枪，向{killed.name}开火，{killed.name}在两眼之间中了一枪。"
                    f"{killed.name} 当场死亡。 {killed.role_description}"
                )
            await self.kill_player(killed, KillMethod.HunterShot, killer=hunter, is_night=False)
            await self.check_role_changes()

    async def end(self, teams: WinType):
        if not self.is_running:
            return False
        self.is_running = False
        msg = ""

        self.end_time = datetime.datetime.now()
        if teams == WinType.Lovers:
            lover = [n for n in self.players.values() if n.in_love]
            for w in lover:
                w.win = True
        else:
            for k in self.players.values():
                if k.role.party != teams:
                    break
                if teams in [WinType.SerialKiller, WinType.Arsonist]:
                    continue

                if teams == WinType.Tanner and not k.died_last_night:
                    continue

                k.win = True
                if k.in_love:
                    k.in_love.win = True

        if teams == WinType.NoOne:
            survivor = [n for n in self.players.values() if not n.dead]
            death_message = ""
            if len(survivor) == 3:
                doppelganger = self.get_survived_player_with_role(ROLES.Doppelganger)
                thief = self.get_survived_player_with_role(ROLES.Thief)
                sorc = self.get_survived_player_with_role(ROLES.Sorcerer)

                if doppelganger and thief and sorc:
                    death_message = f"清晨的雾气消散，🔮暗黑法师{sorc.name}，寻找下一个繁盛的村庄。 #暗黑法师胜\n" \
                                    f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                    "现在村子里只有一个人，没有人可以模仿。他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n" \
                                    f"👻小偷{thief.name} 离开了这个落后的小村庄，去追寻 诗和远方 （划去）..更好更多的职业 #小偷胜"
            elif len(survivor) == 2:
                if any(n.role == ROLES.Tanner for n in survivor) and any(n.role in [
                    ROLES.Sorcerer, ROLES.Thief, ROLES.Doppelganger
                ] for n in survivor):
                    sorc_thief_dg = [n for n in survivor if n.role in [ROLES.Sorcerer, ROLES.Thief, ROLES.Doppelganger]]
                    tann = self.get_survived_player_with_role(ROLES.Tanner)

                    if sorc_thief_dg and tann:
                        sorc_thief_dg = sorc_thief_dg[0]
                        if sorc_thief_dg.role == ROLES.Doppelganger:
                            await sorc_thief_dg.process_dg()
                            if sorc_thief_dg.role == ROLES.Tanner:
                                await self.kill_player(sorc_thief_dg, KillMethod.Suicide, sorc_thief_dg, False)
                                death_message += f"胜利还是属于死亡，{sorc_thief_dg.name} " \
                                                 f"在清晨的阳光中走入了烈火，世界最终会归尽。 #👺皮匠胜。"
                            else:
                                death_message += f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？" \
                                                 f"夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                                 "现在村子里只有一个人，没有人可以模仿。" \
                                                 "他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n"
                        else:
                            if sorc_thief_dg.role == ROLES.Sorcerer:
                                death_message += f"清晨的雾气消散，🔮暗黑法师{sorc_thief_dg.name}" \
                                                 f"离开这个空无一人村庄，寻找下一个繁盛的村庄。"
                            if sorc_thief_dg.role == ROLES.Thief:
                                death_message += f"👻小偷{sorc_thief_dg.name}离开了这个落后的小村庄，" \
                                                 f"去追寻 诗和远方 （划去）..更好更多的职业 #小偷胜"
                            if sorc_thief_dg.role == ROLES.Doppelganger:
                                death_message += f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？" \
                                                 f"夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                                 "现在村子里只有一个人，没有人可以模仿。" \
                                                 "他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n"
                elif any(n.role == ROLES.Sorcerer for n in survivor) and any(n.role in [
                    ROLES.Thief, ROLES.Doppelganger
                ] for n in survivor):
                    sorc = self.get_survived_player_with_role(ROLES.Sorcerer)
                    thief_dg = [n for n in survivor if n.role in [ROLES.Thief, ROLES.Doppelganger]]
                    if sorc and thief_dg:
                        thief_dg = thief_dg[0]
                        death_message = f"清晨的雾气消散，🔮暗黑法师{sorc.name}" \
                                        f"离开这个空无一人村庄，寻找下一个繁盛的村庄。"
                        if thief_dg.role == ROLES.Doppelganger:
                            death_message += f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？" \
                                             f"夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                             "现在村子里只有一个人，没有人可以模仿。" \
                                             "他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n"
                        else:
                            death_message += f"👻小偷{thief_dg.name}离开了这个落后的小村庄，" \
                                             f"去追寻 诗和远方 （划去）..更好更多的职业 #小偷胜"
                if all(n.role in [ROLES.Doppelganger, ROLES.Thief] for n in survivor):
                    thief = self.get_survived_player_with_role(ROLES.Thief)
                    dg = self.get_survived_player_with_role(ROLES.Doppelganger)

                    if dg and thief:
                        death_message = f"👻小偷{thief.name}离开了这个落后的小村庄，" \
                                        f"去追寻 诗和远方 （划去）..更好更多的职业 #小偷胜"
                        death_message += f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？" \
                                         f"夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                         "现在村子里只有一个人，没有人可以模仿。" \
                                         "他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n"
            elif len(survivor) == 1:
                survivor = survivor[0]
                if survivor.role is ROLES.Tanner:
                    await self.kill_player(survivor, KillMethod.Suicide, survivor, False)
                    death_message = f"胜利还是属于死亡，{survivor.name} " \
                                    f"在清晨的阳光中走入了烈火，世界最终会归尽。 #👺皮匠胜。"
                elif survivor.role is ROLES.Sorcerer:
                    death_message = f"清晨的雾气消散，🔮暗黑法师{survivor.name}" \
                                    f"离开这个空无一人村庄，寻找下一个繁盛的村庄。"
                elif survivor.role is ROLES.Thief:
                    death_message = f"👻小偷{survivor.name}离开了这个落后的小村庄，" \
                                    f"去追寻 诗和远方 （划去）..更好更多的职业 #小偷胜"
                elif survivor.role is ROLES.Doppelganger:
                    death_message = f"啊！一个连自己唯一的任务都无法完成的人，其生活能有多悲惨？" \
                                    f"夺取他人外表的能力只是一个传说吗？我们永远也不会知道！" \
                                    "现在村子里只有一个人，没有人可以模仿。" \
                                    "他们唯一能做的就是模仿镜子里的人！这就是他们的能力。 #替身胜\n"
            death_message += "所有人都死了。这届人类不行啊。 #无人胜 #空城"
            await self.ctx.send(death_message)
        elif teams == WinType.Wolf:
            msg += "#狼人胜！ 看来这届村民不行啊！"
            await self.ctx.send(msg)
        elif teams == WinType.Tanner:
            msg += "糟糕！你们竟然昏了头脑把皮匠公审了！#皮匠胜。"
            await self.ctx.send(msg)
        elif teams == WinType.Arsonist:
            if len(self.alive_players) > 1:
                alive = self.alive_players
                other = [n for n in alive if n.role != ROLES.Arsonist][0]
                arsonist = [n for n in alive if n.role == ROLES.Arsonist][0]
                msg = f"只剩🔥纵火犯 {arsonist.name}和 {other.name} ... " \
                      f"突然 {arsonist.name} 笑起来, 划了一根火柴，" \
                      f"丢向了了 {other.name}，{other.name} 瞬间燃烧起来了... \n"
                other.dead = True
                other.time_died = self.day
            msg += "最后，除了🔥纵火犯的家，村子里只剩一片火海。#纵火犯胜..."
            await self.ctx.send(msg)
        elif teams == WinType.Cult:
            msg += "次日清晨，所有人👤邪教徒走上街头，最后一个人也受洗成为👤邪教徒 —— #邪教徒胜！"
            await self.ctx.send(msg)
        elif teams == WinType.SerialKiller:
            if len(self.alive_players) > 1:
                alive = self.alive_players
                other = [n for n in alive if n.role != ROLES.SerialKiller][0]
                sk = [n for n in alive if n.role == ROLES.SerialKiller][0]
                msg = f"这天早上，剩下的两个市民走到广场中央，🔪变态杀人狂 {sk.name} 看了一眼 {other.name} ，" \
                      f"脸上露出邪恶的笑容，「唰！」的一声抽出一把匕首，手起刀落，只见 {other.name} 已倒下。" \
                      f"整个城市只剩下 {sk.name} 是活着的…… #杀人狂胜"
                other.dead = True
                other.time_died = self.day
            msg += "唯一活着的竟然是🔪变态杀人狂！！ #杀人魔胜"
            await self.ctx.send(msg)
        elif teams == WinType.Lovers:
            msg += "胜利属于爱神！ #情侣胜！"
            await self.ctx.send(msg)
        elif teams == WinType.SKHunter:
            h = [n for n in self.alive_players if n.role == ROLES.Hunter]
            sk = [n for n in self.alive_players if n.role == ROLES.SerialKiller]
            msg += "所有人都死了。这届人类不行啊。 #无人胜 #空城"
            if sk:
                await self.kill_player(sk[0], KillMethod.HunterCult, h[0], False)
                if h:
                    await self.kill_player(sk[0], KillMethod.HunterCult, h[0], False)
                    msg += f"曙光乍现， {sk[0].name} 和 {h[0].name} 并排前行，忽然🔪变态杀人狂 {sk[0].name} 拔出了匕首，" \
                           f"跳到 {h[0].name} 身上，把匕首狠狠刺入 {h[0].name} 胸部的同时，猎人 {h[0].name} 也反应迅敏地拔出枪，" \
                           f"对着 {sk[0].name} 的脸就是一枪，把 {sk[0].name} 的头打爆了。\n {h[0].name} 也好不到哪儿去，" \
                           f"匕首已经刺穿了他的心脏……最后两人都死了……\n这就是传说中的相爱相杀？ #空城"
            await self.ctx.send(msg)
        else:
            msg += "#人类胜！ "
            await self.ctx.send(msg)
        survivor = self.alive_players
        msg = f"幸存者们: {len(survivor)}/{len(self.players)}"
        for p in sorted(self.players.values(), key=lambda a: a.time_died):
            msg += f"{p.member.mention}: {'❌ 死亡' if p.dead else '✅ 存活'}{'(🏳️ 已逃跑)' if p.flee else ''}"
            msg += f"{'❤️' if p.in_love else ''} {'胜利' if p.win else '失败'}\n"
        time_played = self.start_time - self.end_time
        msg += f"游戏进行了：{time_played}"
        await self.ctx.send(msg)

    async def check_role_changes(self):
        aps = self.get_survived_player_with_role(ROLES.ApprenticeSeer)
        if aps:
            await aps.process_aps()

        wc = self.get_survived_player_with_role(ROLES.WildChild)
        if wc:
            await wc.process_wc()

        dg = self.get_survived_player_with_role(ROLES.Doppelganger)
        if dg:
            await dg.process_dg()

    def get_survived_player_with_role(self, role: Role) -> Optional[Player]:
        ts = self.get_player_with_role(role)
        for t in ts:
            if not t.dead:
                return t
        else:
            return None

    def get_survived_player_with_roles(self, roles: List[Role]) -> List[Player]:
        players = [n for n in self.players.values() if n.role in roles and not n.dead]
        return players if players else []

    def get_player_with_role(self, role: Role) -> List[Player]:
        players = [n for n in self.players.values() if n.role is role]
        return players if players else []

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

    @property
    def alive_players(self) -> List[Player]:
        return [n for n in self.players.values() if not n.dead]

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
            pointless_role = [
                x for x in roles if
                x in [ROLES.Traitor, ROLES.SnowWolf, ROLES.Sorcerer]
            ]

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
