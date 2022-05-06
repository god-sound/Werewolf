import asyncio
from typing import Dict
import random

from qq.ext import commands

from cogs.werewolf.session import Session


class Werewolf(commands.Cog):
    def __int__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: Dict[int, Session] = {}

    @commands.Command
    async def start(self, ctx: commands.Context):
        await self.start_game(ctx, False)

    async def start_game(self, ctx: commands.Context, chaos: bool):
        msg = [
            "%s 已经敲响了末日的钟声！ 发送 /join 来参加这场屠杀宴会……说不定会暴死当场！",
            "%s 已经召唤出了血月！ 发送 /join 来互相伤害！",
            "反人类的 %s 开启了一场死亡游戏！ 发送 /join 来参加这场互相伤害的盛会！"
        ] if not chaos else [
            "%s 召唤出了隐藏着邪恶力量的钥匙……发送 /join 来成为暴徒……混乱才是现实的真正模样。",
            "以 %s 为先锋，混乱模式全面启动！发送 /join 来响应 %s 的号召。",
            "%s 解除了混乱的封印！现实世界从不曾有公平和美好！ 发送 /join 加入！"
        ]
        sessions = self.sessions[ctx.guild.id] = Session(ctx, chaos)
        sessions.join(ctx.author)
        await ctx.reply(random.choice(msg) % ctx.author.mention)
        await ctx.reply(sessions.player_list_string)
        await sessions.main_game_loop()
        self.sessions.pop(ctx.guild.id)
