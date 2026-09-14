"""命令组：user（用户设置）。

语义：
- /user config -set <键> -value <值>   修改当前用户的 AI 配置（写 user_config 表，改完自动刷新）
- /user update config                  从数据库重新加载配置，覆盖当前 AiClient

只开放用户自己的配置（api_key/base_url/model/prompt），不暴露系统状态。
"""
from .base_command import CommandGroup, command

# 允许用户修改的配置键（白名单，user_id 不可改）
ALLOWED_KEYS = ("api_key", "base_url", "model", "prompt")


def _valid_api_key(value: str) -> bool:
    """api_key 只允许可见 ASCII（sk-xxx 等），拒绝中文/空白/控制字符"""
    if len(value) < 8:
        return False
    return all(0x21 <= ord(c) <= 0x7E for c in value)


class UserCommand(CommandGroup):
    name = "user"
    desc = "用户设置"

    @command("user config -set <键> -value <值>   修改自己的AI配置（api_key/base_url/model/prompt）")
    async def config(self, session, opts, pos):
        key = (opts.get("set") or "").strip()
        value = (opts.get("value") or "").strip()
        if not key:
            key = (pos[0] if pos else "").strip()
        if not key or not value:
            return "用法: /user config -set <键> -value <值>\n可选键: api_key / base_url / model / prompt"
        if key not in ALLOWED_KEYS:
            return f"不允许修改 {key}，可选键: api_key / base_url / model / prompt"
        if value.lower() == "none":
            return "值不能为 None"
        # 格式校验：防非法值入库导致 AI 调用静默失败
        if key == "api_key" and not _valid_api_key(value):
            return "api_key 格式不合法（应为 sk- 开头的 ASCII 字符串，不能含中文/空格）"
        if key == "base_url" and not (value.startswith("http://") or value.startswith("https://")):
            return "base_url 必须以 http:// 或 https:// 开头"

        bot = session.bot
        if bot is None:
            return "命令执行上下文缺失（bot 未注入），请稍后重试"
        # upsert：已有记录则更新，否则插入
        if bot.db.select_one("user_config", where="user_id=%s", params=(session.user_id,)):
            bot.db.update("user_config", {key: value}, "user_id=%s", (session.user_id,))
        else:
            bot.db.insert("user_config", {"user_id": session.user_id, key: value})
        # 改完自动刷新 AI 配置
        bot.refresh_ai(session.user_id)
        return f"已更新 {key}，配置已生效"

    @command("user update config   从数据库重新加载配置")
    async def update(self, session, opts, pos):
        if not pos or pos[0] != "config":
            return "用法: /user update config"
        bot = session.bot
        if bot is None:
            return "命令执行上下文缺失（bot 未注入），请稍后重试"
        if not bot.refresh_ai(session.user_id):
            return "未找到用户配置，请先设置: /user config -set api_key -value <值>"
        return "配置已从数据库重新加载，当前对话生效"


def register_defaults(manager) -> None:
    """注册全部命令组到管理器"""
    manager.register_group(UserCommand())
