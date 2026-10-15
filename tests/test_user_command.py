"""user 命令组的单元测试。

用假 bot/db，不连真实数据库；验证参数校验与 upsert / 刷新逻辑。
"""
import asyncio
import unittest

from bot.command.command_manager import CommandManager
from bot.command.commands.user import UserCommand


class Msg:
    def __init__(self, text, user_id="u1"):
        self.text = text
        self.user_id = user_id


class FakeDB:
    """记录 insert / update 调用，按 existing 决定 select_one 返回。"""

    def __init__(self, existing=False):
        self.existing = existing
        self.inserted = []
        self.updated = []

    def select_one(self, table, where=None, params=None):
        return {"user_id": params[0]} if self.existing else None

    def insert(self, table, data):
        self.inserted.append((table, dict(data)))
        return 1

    def update(self, table, data, where, params):
        self.updated.append((table, dict(data), where, params))
        return 1


class FakeBot:
    def __init__(self, db=None, refresh_ok=True):
        self.db = db or FakeDB()
        self.refresh_ok = refresh_ok
        self.refreshed = []

    def refresh_ai(self, user_id):
        self.refreshed.append(user_id)
        return self.refresh_ok


class TestUserCommand(unittest.TestCase):
    def setUp(self):
        self.mgr = CommandManager()
        self.mgr.register_group(UserCommand())

    def call(self, text, bot):
        session = self.mgr.get_command_session("u1")
        session.bot = bot
        session.db = bot.db
        return asyncio.run(session.handle(Msg(text)))

    # ---------- config 写库 ----------

    def test_config_inserts_when_absent(self):
        bot = FakeBot(db=FakeDB(existing=False))
        reply = self.call("/user config -set model -value gpt-4o", bot)
        self.assertIn("已更新 model", reply)
        self.assertEqual(bot.db.inserted, [("user_config", {"user_id": "u1", "model": "gpt-4o"})])
        self.assertEqual(bot.db.updated, [])
        self.assertEqual(bot.refreshed, ["u1"])

    def test_config_updates_when_present(self):
        bot = FakeBot(db=FakeDB(existing=True))
        reply = self.call("/user config -set model -value gpt-4o", bot)
        self.assertIn("已更新 model", reply)
        self.assertEqual(len(bot.db.updated), 1)
        self.assertEqual(bot.db.inserted, [])

    def test_config_supports_double_dash_options(self):
        bot = FakeBot(db=FakeDB(existing=True))
        reply = self.call("/user config --set model --value gpt-4o", bot)
        self.assertIn("已更新 model", reply)
        self.assertEqual(bot.db.updated[0][1], {"model": "gpt-4o"})

    def test_quoted_value_is_stored_without_quotes(self):
        """带引号的写法应与不带引号等价（parse_args 剥离成对引号）。"""
        bot = FakeBot(db=FakeDB(existing=True))
        reply = self.call('/user config -set prompt -value "你是助手"', bot)
        self.assertIn("已更新 prompt", reply)
        self.assertEqual(bot.db.updated[0][1], {"prompt": "你是助手"})

    # ---------- 参数校验 ----------

    def test_disallowed_key(self):
        reply = self.call("/user config -set evil -value x", FakeBot())
        self.assertIn("不允许修改 evil", reply)

    def test_api_key_format_rejected(self):
        reply = self.call("/user config -set api_key -value 短", FakeBot())
        self.assertIn("api_key 格式不合法", reply)

    def test_base_url_scheme_required(self):
        reply = self.call("/user config -set base_url -value ftp://x", FakeBot())
        self.assertIn("http:// 或 https://", reply)

    def test_none_value_rejected(self):
        reply = self.call("/user config -set model -value None", FakeBot())
        self.assertIn("值不能为 None", reply)

    def test_missing_args_shows_usage(self):
        reply = self.call("/user config", FakeBot())
        self.assertIn("用法", reply)

    def test_missing_bot_returns_hint(self):
        session = self.mgr.get_command_session("u1")
        session.bot = None
        reply = asyncio.run(session.handle(Msg("/user config -set model -value x")))
        self.assertIn("上下文缺失", reply)

    # ---------- update ----------

    def test_update_requires_config_word(self):
        reply = self.call("/user update wrong", FakeBot())
        self.assertEqual(reply, "用法: /user update config")

    def test_update_success(self):
        reply = self.call("/user update config", FakeBot(refresh_ok=True))
        self.assertIn("配置已从数据库重新加载", reply)

    def test_update_without_config(self):
        reply = self.call("/user update config", FakeBot(refresh_ok=False))
        self.assertIn("未找到用户配置", reply)


if __name__ == "__main__":
    unittest.main()
