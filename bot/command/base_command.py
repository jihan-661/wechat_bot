"""命令系统基类。

设计：
- 一个命令组（CommandGroup）= 一个命名空间（如 system），一个方法 = 一条命令（如 config）
- 方法用 @command(usage) 装饰器标记：未标记的方法是内部辅助方法，不会被暴露
- usage 是帮助文本（/help 输出）；不填则退化为方法名（不报错，但 /help 显示难看，建议填写）
- 被标记的方法统一签名：async def xxx(self, session, opts, pos) -> str
  - session: CommandSession（per-user 会话，存状态用）
  - opts: dict，-key value 解析出的选项
  - pos: list，位置参数
"""
from abc import ABC


def command(usage: str = ""):
    """装饰器：把方法标记为命令。usage 为帮助文本。"""
    def deco(fn):
        fn._is_command = True
        fn._usage = usage
        return fn
    return deco


def parse_args(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """解析命令参数。

    -key value 解析为选项（opts），其余为位置参数（pos）。
    选项的值会一直收集到下一个 "-" 开头 token 或末尾（支持长值，自动 join 空格）。
    例: ['-set', 'a', 'x'] -> ({'set': 'a'}, ['x'])
    例: ['-set', 'prompt', '-value', '你是', '一个AI'] -> ({'set': 'prompt', 'value': '你是 一个AI'}, [])
    布尔开关: ['-v'] -> ({'v': ''}, [])
    """
    opts: dict[str, str] = {}
    pos: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-") and len(t) > 1:
            key = t[1:]
            vals: list[str] = []
            j = i + 1
            while j < len(tokens) and not tokens[j].startswith("-"):
                vals.append(tokens[j])
                j += 1
            opts[key] = " ".join(vals)     # 布尔开关无后续值时为空串
            i = j
        else:
            pos.append(t)
            i += 1
    return opts, pos


class CommandGroup(ABC):
    """命令组基类。子类必须覆盖 name；方法用 @command() 标记为命令。"""

    name: str = ""      # 命令组名，如 "system"（子类必须覆盖，否则实例化报错）
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
