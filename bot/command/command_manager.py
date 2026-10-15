"""命令管理器、命令会话与命令中间件。

架构：
- CommandManager：注册命令组、自动发现 commands 包、管理 per-user 会话
- CommandSession：每个用户一个，负责路由消息、生成 /help、调用命令
- CommandMiddleware：接入 bot 的 before_reply 阶段，命中命令则短路 AI

命令语义：
- 仅以 "/" 开头的消息视为命令
- 无 "/" 前缀的消息一律放行给 AI（返回 None）
- "/" 开头但无法解析 → 返回帮助/提示，绝不透传 AI

扩展方式：
- 在 bot/command/commands/ 下新建模块，暴露 GROUPS = [YourGroup]
- 不需要修改本文件，也不需要任何手工登记（discover 自动扫描）
"""
import importlib
import inspect
import pkgutil

from log import logger
from .base_command import CommandContext, CommandGroup, parse_args


class CommandManager:
    """命令组注册表 + per-user 会话表。

    非单例：由调用方（BotManager）创建并持有，便于测试时造独立实例。
    """

    def __init__(self):
        self.groups: dict[str, CommandGroup] = {}
        self.sessions: dict[str, "CommandSession"] = {}

    def register_group(self, group: CommandGroup):
        """注册命令组（重复注册直接报错，防止静默覆盖）"""
        if not isinstance(group, CommandGroup):
            raise TypeError(f"只能注册 CommandGroup 实例，收到 {type(group).__name__}")
        if group.name in self.groups:
            raise ValueError(f"命令组 {group.name} 已注册")
        self.groups[group.name] = group

    def discover(self, package=None) -> list[str]:
        """自动发现并注册 commands 包下的所有命令组。

        约定：每个命令模块在顶层暴露 GROUPS 列表（元素为 CommandGroup 子类）。
        跳过以 "_" 开头的模块。

        :param package: 要扫描的包，默认 bot.command.commands
        :return: 本次实际注册的组名列表（按模块名排序）
        """
        if package is None:
            from . import commands
            package = commands

        registered: list[str] = []
        for mod_info in pkgutil.iter_modules(package.__path__):
            if mod_info.name.startswith("_"):
                continue
            module = importlib.import_module(f"{package.__name__}.{mod_info.name}")
            for group_cls in getattr(module, "GROUPS", []):
                group = group_cls()
                self.register_group(group)
                registered.append(group.name)
                logger.info(f"已注册命令组 /{group.name}（来自 {mod_info.name}.py）")
        return registered

    def get_command_session(self, user_id: str) -> "CommandSession":
        """获取用户会话：存在返回，不存在创建（多轮状态靠它持久）"""
        if user_id not in self.sessions:
            self.sessions[user_id] = CommandSession(user_id, self.groups)
        return self.sessions[user_id]


class CommandSession:
    """每用户一个的会话：路由消息 → 执行命令 → 返回回复。"""

    def __init__(self, user_id: str, groups: dict[str, CommandGroup]):
        self.user_id = user_id
        self.groups = groups          # 引用全局命令表（命令对象共享、无状态）
        self.bot = None               # 由 CommandMiddleware 每次调用前注入
        self.db = None                # 同上（取自 bot.db）

    async def handle(self, msg) -> str | None:
        """统一处理入口。返回回复文本；返回 None 表示这不是命令，交给 AI。"""
        text = (msg.text or "").strip()
        # 非 "/" 开头一律放行给 AI
        if not text or not text.startswith("/"):
            return None

        body = text[1:].strip()               # 去掉前导 "/"
        if not body:                          # 单独一个 "/" → 给帮助，拦截
            return self._manager_help()

        tokens = body.split()
        head = tokens[0]

        # /help 特殊处理
        if head == "help":
            return self._manager_help(tokens[1] if len(tokens) > 1 else "")

        group = self.groups.get(head)
        if not group:                         # /xxx 未知命令 → 拦截并提示
            return f"未知命令: /{head}\n" + self._manager_help()
        if len(tokens) < 2:                   # 只输组名 → 返回该组帮助
            return self._manager_help(head)

        method_name = tokens[1]
        fn = getattr(group, method_name, None)
        if not callable(fn) or not getattr(fn, "_is_command", False):
            return f"未知命令: /{head} {method_name}\n" + self._manager_help(head)

        opts, pos = parse_args(tokens[2:])
        ctx = CommandContext(
            user_id=self.user_id,
            args=opts,
            pos=pos,
            bot=self.bot,
            db=self.db,
            msg=msg,
            session=self,
        )

        # 命令内部异常不能让整条消息处理链崩掉：兜底记录并返回提示
        try:
            result = fn(ctx)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            logger.exception(f"命令 /{head} {method_name} 执行失败")
            return "命令执行出错，已记录日志（请查看日志定位）"

        # 返回 None 表示该命令不产出回复，交给后续流程 / AI
        if result is None:
            return None
        return result if isinstance(result, str) else str(result)

    def _manager_help(self, group_name: str = "") -> str:
        """用本会话持有的 groups 引用生成帮助文本（groups 即全局注册表）"""
        if group_name:
            group = self.groups.get(group_name)
            if not group:
                return f"未知命令组: {group_name}"
            title = f"【{group.name}】{group.desc}".rstrip()
            usages = group.collect_commands()
            helps = group.collect_help()
            lines = [title]
            for method, usage in usages.items():
                desc = helps.get(method, "")
                suffix = f"    {desc}" if desc else ""
                lines.append(f"  /{group.name} {usage}{suffix}")
            return "\n".join(lines)

        lines = ["可用命令："]
        for group in self.groups.values():
            title = f"【{group.name}】{group.desc}".rstrip()
            names = "、".join(group.collect_commands().keys())
            lines.append(f"{title}  [{names}]")
        lines.append("输入 '/help <组名>' 查看单组详细用法")
        return "\n".join(lines)


class CommandMiddleware:
    """AI 回复前的命令中间件。

    命中命令 → 设置 parm_dict["reply"] + ["handled"]，on_message 据此短路 AI；
    未命中（非 "/" 开头）→ 不改动 parm_dict，消息正常走 AI。
    """

    def __init__(self, session_provider, bot=None):
        self.get_session = session_provider   # 注入"按 user_id 拿会话"的能力
        self.bot = bot                        # 注入当前 Bot 实例（命令写库/刷新配置用）

    async def __call__(self, parm_dict):
        msg = parm_dict["msg"]
        user_id = msg.user_id
        session = self.get_session(user_id)
        # 注入当前 bot 与数据库句柄，命令通过 ctx.bot / ctx.db 使用
        session.bot = self.bot
        session.db = getattr(self.bot, "db", None)
        reply = await session.handle(msg)
        if reply:
            logger.info(f"命令命中: user={user_id} 输入={msg.text!r} 回复={reply[:60]!r}")
            parm_dict["reply"] = reply
            parm_dict["handled"] = True
        else:
            logger.debug(f"命令放行: user={user_id} 输入={msg.text!r} 交给AI")
