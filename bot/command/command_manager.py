"""命令管理器与命令会话。

架构：
- CommandManager（单例）：注册命令组、管理 per-user 会话
- CommandSession（每用户一个）：路由消息、/help 特殊处理、多轮状态预留
- CommandMiddleware：接入微信 bot 的 before_reply 中间件，命中命令则短路 AI

命令语义（重要）：
- 仅以 "/" 开头的消息视为命令（/help、/system status、/system config ...）
- 无 "/" 前缀的消息一律放行给 AI（普通聊天）
- "/" 开头但无法解析 → 返回帮助/提示，绝不透传 AI
"""
from log import logger
from .base_command import CommandGroup, parse_args


class CommandManager:
    """全局唯一的命令管理类：注册命令组 + 管理会话表。"""

    _instance = None
    _initialized = False

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.groups: dict[str, CommandGroup] = {}          # 组名 -> 命令组实例
        self.sessions: dict[str, CommandSession] = {}      # user_id -> 会话

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_group(self, group: CommandGroup):
        """注册命令组（重复注册直接报错，防止静默覆盖）"""
        if group.name in self.groups:
            raise ValueError(f"命令组 {group.name} 已注册")
        self.groups[group.name] = group

    def register_command(self, group: CommandGroup):
        """兼容旧命名：注册命令组"""
        self.register_group(group)

    def get_command_session(self, user_id: str) -> "CommandSession":
        """获取用户会话：存在返回，不存在创建（多轮状态靠它持久）"""
        if user_id not in self.sessions:
            self.sessions[user_id] = CommandSession(user_id, self.groups)
        return self.sessions[user_id]


class CommandSession:
    """每用户一个的会话：路由消息 → 执行命令 → 返回回复。"""

    def __init__(self, user_id: str, groups: dict[str, CommandGroup]):
        self.user_id = user_id
        self.groups = groups                 # 引用全局命令表（命令对象共享、无状态）
        self.command = None                  # 预留：当前进行中的多轮命令
        self.state = None                    # 预留：状态机当前值
        self.bot = None                      # 由 CommandMiddleware 每次调用前注入（命令刷新配置用）

    async def handle(self, msg) -> str | None:
        """统一处理入口。返回回复文本；返回 None 表示这不是命令，交给 AI。"""
        text = (msg.text or "").strip()
        if not text:
            return None
        # 仅 "/" 开头视为命令；无前缀一律放行 AI
        if not text.startswith("/"):
            return None

        body = text[1:].strip()              # 去掉前导 "/"
        if not body:                         # 单独一个 "/" → 给帮助，拦截
            return self._manager_help()
        tokens = body.split()
        head = tokens[0]

        # /help 特殊处理
        if head == "help":
            return self._manager_help(tokens[1] if len(tokens) > 1 else "")

        group = self.groups.get(head)
        if not group:                        # /xxx 未知命令 → 拦截并提示
            return f"未知命令: /{head}\n" + self._manager_help()

        if len(tokens) < 2:
            return self._manager_help(head)  # 只输组名 → 返回该组帮助

        method_name = tokens[1]
        fn = getattr(group, method_name, None)
        if not callable(fn) or not getattr(fn, "_is_command", False):
            return f"未知命令: /{head} {method_name}\n" + self._manager_help(head)

        opts, pos = parse_args(tokens[2:])
        result = await fn(self, opts, pos)
        return result if isinstance(result, str) else str(result)

    def _manager_help(self, group_name: str = "") -> str:
        """用本会话持有的 groups 引用生成帮助文本（groups 即全局注册表）"""
        if group_name:
            g = self.groups.get(group_name)
            if not g:
                return f"未知命令组: {group_name}"
            title = f"【{g.name}】{g.desc}".rstrip()
            body = [f"  /{g.name} {m}  {u}" for m, u in g.collect_commands().items()]
            return "\n".join([title] + body)
        lines = ["可用命令："]
        for g in self.groups.values():
            title = f"【{g.name}】{g.desc}".rstrip()
            names = "、".join(g.collect_commands().keys())
            lines.append(f"{title}  [{names}]")
        lines.append("输入 '/help <组名>' 查看单组详细用法")
        return "\n".join(lines)


class CommandMiddleware:
    """AI 回复前的命令中间件。

    命中命令 → 设置 parm_dict["reply"] + ["handled"]，on_message 据此短路 AI。
    未命中（非 "/" 开头）→ 不改动 parm_dict，消息正常走 AI。
    """

    def __init__(self, session_provider, bot=None):
        self.get_session = session_provider   # 注入"按 user_id 拿会话"的能力
        self.bot = bot                        # 注入当前 Bot 实例（命令写库/刷新配置用）

    async def __call__(self, parm_dict):
        msg = parm_dict["msg"]
        user_id = msg.user_id
        session = self.get_session(user_id)
        session.bot = self.bot                # 注入当前 bot 到会话
        reply = await session.handle(msg)
        if reply:
            logger.info(f"命令命中: user={user_id} 输入={msg.text!r} 回复={reply[:60]!r}")
            parm_dict["reply"] = reply
            parm_dict["handled"] = True
        else:
            logger.debug(f"命令放行: user={user_id} 输入={msg.text!r} 交给AI")
