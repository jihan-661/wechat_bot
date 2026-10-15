"""命令管理器、会话路由与中间件的单元测试。

不依赖数据库、也不依赖微信 SDK：命令只需要 CommandContext。
discover() 的"给定包"用例用内存模块 + mock 模块列举，不写磁盘，
因此本套测试在任何环境下都可运行（包括受限沙箱）。
"""
import asyncio
import pkgutil
import sys
import types
import unittest
from unittest import mock

from bot.command.base_command import CommandGroup, command
from bot.command.command_manager import CommandManager, CommandMiddleware


class Msg:
    """最小消息替身：只需要 text 与 user_id。"""

    def __init__(self, text, user_id="u1"):
        self.text = text
        self.user_id = user_id


class EchoGroup(CommandGroup):
    name = "echo"
    desc = "测试用命令组"

    @command("hi <文本...>", help="异步回显位置参数")
    async def hi(self, ctx):
        return " ".join(ctx.pos)

    @command("sync <文本...>", help="同步回显位置参数")
    def sync(self, ctx):
        return " ".join(ctx.pos)

    @command("boom", help="故意抛异常")
    async def boom(self, ctx):
        raise RuntimeError("boom")

    @command("nothing", help="返回 None")
    async def nothing(self, ctx):
        return None

    @command("whoami", help="回显 bot/db 注入情况")
    async def whoami(self, ctx):
        return f"bot={ctx.bot is not None}|db={ctx.db}"

    @command("args", help="回显解析后的参数")
    async def args(self, ctx):
        return f"{sorted(ctx.args.items())}|{ctx.pos}"


class FakeDiscoveredGroup(CommandGroup):
    name = "fake"
    desc = "内存假命令组"

    @command("ping", help="回显")
    async def ping(self, ctx):
        return "pong"


class TestRegistration(unittest.TestCase):
    def test_register_and_duplicate_rejected(self):
        mgr = CommandManager()
        mgr.register_group(EchoGroup())
        self.assertIn("echo", mgr.groups)
        with self.assertRaises(ValueError):
            mgr.register_group(EchoGroup())

    def test_register_rejects_non_group(self):
        mgr = CommandManager()
        with self.assertRaises(TypeError):
            mgr.register_group(object())

    def test_discover_default_package_registers_user(self):
        """扫真实目录：bot/command/commands/user.py 应被自动发现。"""
        mgr = CommandManager()
        names = mgr.discover()
        self.assertIn("user", names)
        self.assertIn("user", mgr.groups)

    def test_discover_scans_given_package(self):
        """给定 package 时同样能发现并注册（用内存模块，不写磁盘）。"""
        pkg_name = "fakepkg_probe"
        module = types.ModuleType(f"{pkg_name}.fake")
        module.GROUPS = [FakeDiscoveredGroup]
        package = types.ModuleType(pkg_name)
        package.__path__ = []

        sys.modules[f"{pkg_name}.fake"] = module
        sys.modules[pkg_name] = package
        self.addCleanup(sys.modules.pop, f"{pkg_name}.fake", None)
        self.addCleanup(sys.modules.pop, pkg_name, None)

        fake_info = types.SimpleNamespace(name="fake")
        with mock.patch.object(pkgutil, "iter_modules", return_value=[fake_info]):
            mgr = CommandManager()
            names = mgr.discover(package)

        self.assertEqual(names, ["fake"])
        self.assertIn("fake", mgr.groups)

    def test_discover_skips_underscore_modules(self):
        pkg_name = "fakepkg_probe2"
        package = types.ModuleType(pkg_name)
        package.__path__ = []
        sys.modules[pkg_name] = package
        self.addCleanup(sys.modules.pop, pkg_name, None)

        fake_info = types.SimpleNamespace(name="_private")
        with mock.patch.object(pkgutil, "iter_modules", return_value=[fake_info]):
            mgr = CommandManager()
            names = mgr.discover(package)

        self.assertEqual(names, [])

    def test_sessions_are_per_user_and_reused(self):
        mgr = CommandManager()
        s1 = mgr.get_command_session("a")
        s2 = mgr.get_command_session("a")
        s3 = mgr.get_command_session("b")
        self.assertIs(s1, s2)
        self.assertIsNot(s1, s3)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.mgr = CommandManager()
        self.mgr.register_group(EchoGroup())

    def handle(self, text, user_id="u1"):
        session = self.mgr.get_command_session(user_id)
        return asyncio.run(session.handle(Msg(text, user_id)))

    def test_non_command_returns_none(self):
        self.assertIsNone(self.handle("你好"))

    def test_blank_returns_none(self):
        self.assertIsNone(self.handle("   "))

    def test_async_command(self):
        self.assertEqual(self.handle("/echo hi a b"), "a b")

    def test_sync_command_is_supported(self):
        self.assertEqual(self.handle("/echo sync x"), "x")

    def test_command_exception_is_caught(self):
        # 回归：命令内部异常曾直接穿透 handle，打断消息处理链
        reply = self.handle("/echo boom")
        self.assertIn("命令执行出错", reply)

    def test_command_returning_none_passes_through(self):
        self.assertIsNone(self.handle("/echo nothing"))

    def test_unknown_group(self):
        self.assertIn("未知命令: /nope", self.handle("/nope"))

    def test_unknown_method(self):
        self.assertIn("未知命令: /echo nosuch", self.handle("/echo nosuch"))

    def test_bare_slash_shows_help(self):
        self.assertIn("可用命令", self.handle("/"))

    def test_group_only_shows_group_help(self):
        reply = self.handle("/echo")
        self.assertIn("【echo】", reply)
        self.assertIn("/echo hi", reply)

    def test_help_all(self):
        self.assertIn("【echo】", self.handle("/help"))

    def test_help_single_group(self):
        self.assertIn("/echo hi", self.handle("/help echo"))

    def test_help_unknown_group(self):
        self.assertIn("未知命令组: nope", self.handle("/help nope"))

    def test_parsed_args_reach_context(self):
        # 位置参数在前、选项在后（选项会吃到末尾，故位置参数必须写在选项之前）
        self.assertEqual(self.handle("/echo args pos1 -k v"), "[('k', 'v')]|['pos1']")


class TestCommandMiddleware(unittest.TestCase):
    def setUp(self):
        self.mgr = CommandManager()
        self.mgr.register_group(EchoGroup())

    def test_command_sets_reply_and_handled(self):
        mw = CommandMiddleware(self.mgr.get_command_session, types.SimpleNamespace(db="FAKE_DB"))
        parm = {"msg": Msg("/echo hi hello")}
        asyncio.run(mw(parm))
        self.assertTrue(parm.get("handled"))
        self.assertEqual(parm.get("reply"), "hello")

    def test_non_command_leaves_parm_untouched(self):
        mw = CommandMiddleware(self.mgr.get_command_session, types.SimpleNamespace(db="X"))
        parm = {"msg": Msg("普通聊天")}
        asyncio.run(mw(parm))
        self.assertNotIn("handled", parm)
        self.assertNotIn("reply", parm)

    def test_bot_and_db_injected_into_ctx(self):
        mw = CommandMiddleware(self.mgr.get_command_session, types.SimpleNamespace(db="MY_DB"))
        parm = {"msg": Msg("/echo whoami")}
        asyncio.run(mw(parm))
        self.assertEqual(parm.get("reply"), "bot=True|db=MY_DB")


if __name__ == "__main__":
    unittest.main()
