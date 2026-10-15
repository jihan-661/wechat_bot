"""命令系统基类、上下文与参数解析。

设计：
- 一个命令组（CommandGroup）= 一个命名空间（如 user），一个方法 = 一条命令（如 config）
- 方法用 @command(usage, help=...) 装饰器标记；未标记的方法不暴露
- 被标记的方法统一签名：async def xxx(self, ctx) -> str | None
  - ctx: CommandContext，由派发层注入，含 bot / db / msg / 已解析的参数
  - 返回 str  → 作为回复发给用户
  - 返回 None → 视为"不处理"，交给 AI（与"不是命令"一致）
  - 抛异常    → 由派发层捕获并记录，不会打断消息循环
- parse_args 同时支持 -key value 与 --key value；负数与单独的 "-" 视为位置参数

注意：命令方法的第一个参数名固定为 self，第二个为 ctx。命令内部通过 ctx.bot /
ctx.db 访问当前 Bot 与数据库，不要自己持有全局实例。
"""
from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandContext:
    """派发层注入给每条命令的运行时上下文。

    命令通过它拿到当前用户、当前 Bot 实例、数据库句柄，以及解析后的参数。
    多 bot 场景下这是唯一正确的 Bot 来源，禁止使用全局 Bot。
    """
    user_id: str
    args: dict = field(default_factory=dict)      # -key value 解析出的选项
    pos: list = field(default_factory=list)       # 位置参数
    bot: Any = None                               # 当前 Bot 实例
    db: Any = None                                # Database 实例
    msg: Any = None                               # 原始消息对象
    session: Any = None                           # 当前 CommandSession


def command(usage: str = "", *, help: str = ""):
    """装饰器：把方法标记为一条命令。

    :param usage: 帮助正文，通常形如 "config -set <键> -value <值>"（不含组名）
    :param help: 一句话描述（可选，会附在 /help 的用法后面）
    """
    def deco(fn):
        fn._is_command = True
        fn._usage = usage
        fn._help = help
        return fn
    return deco


def _is_number(token: str) -> bool:
    """token 是否是数字。用于把负数（如 -1）当位置参数而不是选项。"""
    try:
        float(token)
        return True
    except (ValueError, TypeError):
        return False


def _is_option(token: str) -> bool:
    """token 是否应被当作选项开关。

    以下都算位置参数，不当选项：
    - 不以 "-" 开头，或只有单个 "-"
    - 负数（如 -1、-3.5）
    - 纯横线（-、--）
    """
    if not token.startswith("-") or len(token) < 2:
        return False
    if _is_number(token):
        return False
    if token.strip("-") == "":
        return False
    return True


def parse_args(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """解析命令参数。

    -key value 或 --key value 解析为选项（opts），键统一去掉前导横线；
    其余为位置参数（pos）。选项的值会一直收集到下一个选项或末尾（支持长值、可含空格）。

    例: ['-set', 'a', 'x']         -> ({'set': 'a'}, ['x'])
    例: ['--set', 'prompt', '你是'] -> ({'set': 'prompt'}, ['你是'])
    例: ['-1']                     -> ({}, ['-1'])       # 负数当位置参数
    例: ['-v']                     -> ({'v': ''}, [])    # 布尔开关
    """
    opts: dict[str, str] = {}
    pos: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        token = tokens[i]
        if _is_option(token):
            key = token.lstrip("-")
            vals: list[str] = []
            j = i + 1
            while j < n and not _is_option(tokens[j]):
                vals.append(tokens[j])
                j += 1
            opts[key] = " ".join(vals)
            i = j
        else:
            pos.append(token)
            i += 1
    return opts, pos


class CommandGroup(ABC):
    """命令组基类。子类必须覆盖 name；方法用 @command() 标记为命令。"""

    name: str = ""      # 命令组名，如 "user"（子类必须覆盖，否则实例化报错）
    desc: str = ""      # 组的一句话描述（/help 显示）

    def __init__(self):
        if not self.name:
            raise ValueError(f"命令组 {type(self).__name__} 必须设置 name 属性")

    @classmethod
    def collect_commands(cls) -> dict[str, str]:
        """收集所有被 @command 标记的方法: {方法名: usage文本}"""
        result: dict[str, str] = {}
        for attr in dir(cls):
            fn = getattr(cls, attr)
            if callable(fn) and getattr(fn, "_is_command", False):
                result[attr] = getattr(fn, "_usage", "") or attr
        return result

    @classmethod
    def collect_help(cls) -> dict[str, str]:
        """收集命令的一句话描述: {方法名: help文本}（未填 help 的不出现）"""
        result: dict[str, str] = {}
        for attr in dir(cls):
            fn = getattr(cls, attr)
            if callable(fn) and getattr(fn, "_is_command", False):
                text = getattr(fn, "_help", "")
                if text:
                    result[attr] = text
        return result
