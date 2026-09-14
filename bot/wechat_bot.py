import asyncio
import threading
import os
from pathlib import Path

from wechatbot import WeChatBot
from wechatbot.auth import save_credentials, clear_credentials
from database.database import Database
from . import ai
from .command.command_manager import CommandManager, CommandMiddleware
from .command.examples import register_defaults
from user.user_init import InitUser
from log import logger
from user import user_init
import flask

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # bot/ 目录
USER_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "user", "user_token"))


class Bot:
    def __init__(self, db: Database, cred_path=None):
        self.bot = WeChatBot(on_qr_url=self.get_qr_url, cred_path=cred_path)
        self.db = db
        #唯一标识符号,不自己管理,由BotManage统一在外部注入

        #不需要Bot本身持有user_init类了,改为中间件注入事件列表,暂时留着直到跑通
        # self.user_init = InitUser(db, self)

        # {user_id: AiClient} 缓存，避免每次消息都新建
        self._ai_clients = {}
        self.bot.on_message(self.on_message)
        # 分阶段注册函数字典方便扩展
        self._handlers = {
            "before_reply": [],  # AI回复前：配置校验、输入过滤、权限检查
            "on_reply": [],  # AI回复时：生成回复
            "after_reply": [],  # AI回复后：对话记录、输出限制
        }
        self.ai_client = None
        self.qr_url = None
        self.user_id = None  # 由 BotManager 注入（恢复时来自 user 表，注册时来自 creds）

    def get_qr_url(self, url: str):
        self.qr_url = url

    def register_handler(self, stage: str, handler):
        try:
            self._handlers[stage].append(handler)
        except ValueError as e:
            logger.error(f"使用了错误的阶段或注册了错误的函数:{e}")
        except Exception as e:
            logger.error(f"函数注册失败:{e}")
    def set_ai(self, ai_client: ai.AiClient):
        """注入全局AI实例（可选，用于默认配置）"""
        self._default_ai = ai_client

    def _get_ai(self, user_id: str) -> ai.AiClient | None:
        """获取用户的AI实例，有缓存用缓存，没有就从数据库加载"""
        if user_id in self._ai_clients:
            return self._ai_clients[user_id]

        config = self.db.select_one("user_config", where="user_id=%s", params=(user_id,))
        if not config:
            return None

        client = ai.AiClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            prompt=config.get("prompt",None)
        )
        self._ai_clients[user_id] = client
        return client

    def refresh_ai(self, user_id: str) -> bool:
        """从数据库重新加载用户配置，覆盖 AiClient 缓存。返回是否成功"""
        config = self.db.select_one("user_config", where="user_id=%s", params=(user_id,))
        if not config:
            self._ai_clients.pop(user_id, None)
            logger.info(f"刷新AI配置失败：用户 {user_id} 无配置")
            return False
        client = ai.AiClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            prompt=config.get("prompt", None)
        )
        self._ai_clients[user_id] = client
        logger.info(f"已刷新用户 {user_id} 的 AI 配置")
        return True

    async def get_ai(self,parm_dict):
        """
        前置中间件,如果不载入此中间件LLM无法正常工作
        :param parm_dict: 参数字典
        :return: None
        """
        logger.info("调用get_ai中间件")
        ai_client = self._get_ai(parm_dict["msg"].user_id)
        if ai_client is None:
            # await self.bot.reply(parm_dict["msg"], "AI服务未初始化，请先完成配置")
            return
        parm_dict["ai_client"] = ai_client

    async def login(self):
        await self.bot.login()

    async def on_message(self, msg):
        #状态驱动的now_role变量,为中间件提供服务,在回复前是用户,回复中是ai,触发工具中间件时由工具中间件内部手动修改为tool
        now_role = "user"
        parm_dict = {"msg": msg,"now_role":now_role}
        user_id = msg.user_id

        #预留字段,将来开发
        tool_list = []

        for i in self._handlers["before_reply"]:
            await i(parm_dict)
            if parm_dict.get("handled"):
                break

        # 命令中间件命中：直接回复，不走 AI
        if parm_dict.get("reply"):
            logger.info(f"命令回复: {parm_dict['reply']}")
            await self.bot.reply(msg, parm_dict["reply"])
            return

        # 正常聊天
        logger.info(f"用户ID: {msg.user_id}")
        logger.info(f"接收到信息:{msg.text}")
        if not parm_dict.get("ai_client"):
            await self.bot.reply(msg,"未配置ai")
            logger.debug("ai_client为空")
            return
        try:
            ai_res = parm_dict["ai_client"].get_ai_res("user", content=msg.text)
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            await self.bot.reply(msg, "AI 服务调用失败，请检查配置（/user config）")
            return
        #向参数字典新增ai回复
        parm_dict["ai_res"] = ai_res
        #修改角色
        parm_dict["now_role"] = "assistant"
        for i in self._handlers["on_reply"]:
            await i(parm_dict)

        logger.info(f"回复信息:{ai_res}")
        await self.bot.reply(msg, ai_res)

        for i in self._handlers["after_reply"]:
            await i(parm_dict)
    async def start(self):
        await self.login()
        await self.bot.start()


class BotManager:
    _instance = None
    _initialized = False
    def __init__(self, db: Database):
        #防止重复初始化
        if BotManager._initialized:
            return
        BotManager._initialized = True
        self._bots: dict[str, Bot] = {}
        self.db = db
        self._tasks: list = []  # 防 GC（run_coroutine_threadsafe 返回的 Future）
        self._middleware = []
        # 命令系统：单例管理器 + 注册 demo 命令组
        self.cmd_manager = CommandManager()
        register_defaults(self.cmd_manager)
        # 常驻后台事件循环：load_from_db / register_bot_api 提交的协程都在这里跑，
        # 不会因 start.py 的 asyncio.run 返回而销毁
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_handler(self, stage: str, handler):
        """注册默认中间件，所有 bot 都会加载"""
        self._middleware.append((stage, handler))


    def _apply_middleware(self, bot: Bot):
        # 默认中间件：InitUser 用户引导（无条件注入，不依赖 _middleware 是否为空）
        self.register_init_user(bot)
        # 命令中间件：命中命令则短路（优先级高于 AI）
        bot.register_handler("before_reply", CommandMiddleware(self.cmd_manager.get_command_session, bot))
        # AI 载入中间件：绑定方法，加载用户 AI 配置
        bot.register_handler("before_reply", bot.get_ai)
        # 自定义中间件
        for stage, handler in self._middleware:
            bot.register_handler(stage, handler)
    def _apply_one_middleware(self,bot:Bot,stage,middleware):
        bot.register_handler(stage,middleware)

    def register_init_user(self,bot:Bot):
        init_user = user_init.InitUser(self.db, bot)
        self._apply_one_middleware(bot, "before_reply", init_user.user_init)

    def get_bot(self, user_id: str) -> Bot | None:
        return self._bots.get(user_id)

    def add_bot(self, user_id: str, bot: Bot,):
        """加入管理并启动"""
        self._apply_middleware(bot)
        self._bots[user_id] = bot
        # 提交到常驻事件循环后台启动，不阻塞
        self._tasks.append(asyncio.run_coroutine_threadsafe(bot.start(), self._loop))

    def del_bot(self, user_id: str):
        bot = self._bots.pop(user_id, None)
        if bot:
            bot.bot.stop()

    def load_from_db(self):
        """启动时从数据库恢复所有已注册用户（status=1）的 bot"""
        rows = self.db.select("user", where="status=1")
        logger.info(f"恢复bot：user(status=1) 共 {len(rows)} 个用户")
        for row in rows:
            user_id = row["id"]
            user_path = os.path.join(USER_DIR, f"{user_id}.json")
            if not os.path.exists(user_path):
                logger.warning(f"用户 {user_id} 无凭证文件，跳过启动（待扫码注册）")
                continue
            bot = Bot(self.db, cred_path=user_path)
            bot.user_id = user_id
            self._bots[user_id] = bot
            self._apply_middleware(bot)
            self._tasks.append(asyncio.run_coroutine_threadsafe(bot.start(), self._loop))
            logger.info(f"已恢复用户 {user_id} 的 bot")

    async def add_new_bot(self) -> str:
        """交互式添加：扫码登录 → 存数据库 → 启动"""
        bot = Bot(self.db)
        creds = await bot.bot.login()  # 弹二维码，等扫码
        bot.user_id = creds.user_id
        # 凭证归档到用户目录（供下次启动恢复）
        os.makedirs(USER_DIR, exist_ok=True)
        await save_credentials(creds, Path(os.path.join(USER_DIR, f"{creds.user_id}.json")))
        # 幂等写 user
        if not self.db.select_one("user", where="id=%s", params=(creds.user_id,)):
            self.db.insert("user", {"id": creds.user_id})
        self._bots[creds.user_id] = bot
        await bot.bot.start()
        return creds.user_id

    def register_bot_api(self) -> Bot:
        """非阻塞注册：创建 Bot，注入中间件，后台跑登录，立即返回实例"""
        bot = Bot(self.db)
        self._apply_middleware(bot)
        self._tasks.append(asyncio.run_coroutine_threadsafe(self._login_and_start(bot), self._loop))
        return bot

    async def _login_and_start(self, bot: Bot):
        try:
            # force=True：强制走二维码流程（否则默认路径残留凭证会让 login 直接返回 stored，qr_url 不填充）
            creds = await bot.bot.login(force=True)  # ① 回调填充 bot.qr_url → 接口轮询到就返回
            # ② confirmed 后 creds.user_id 就绪
            # 凭证归档到用户目录（供下次启动恢复），并清掉默认路径残留防止凭证串用
            os.makedirs(USER_DIR, exist_ok=True)
            await save_credentials(creds, Path(os.path.join(USER_DIR, f"{creds.user_id}.json")))
            await clear_credentials()
            # 幂等写 user（这是最早能拿到 user_id 的点）
            if not self.db.select_one("user", where="id=%s", params=(creds.user_id,)):
                self.db.insert("user", {"id": creds.user_id})
            bot.user_id = creds.user_id
            # 去重：同一用户已有 Bot 实例则停掉旧的，防止一条消息触发多个 on_message
            old = self._bots.get(creds.user_id)
            if old:
                old.bot.stop()
            self._bots[creds.user_id] = bot  # 注册进管理器，消息才会被处理
            await bot.bot.start()  # 长轮询，永不返回
        except Exception as e:
            logger.error(f"登录/启动 bot 失败: {e}")


class BotRoute:
    def __init__(self):
        self.base_url = "/bot"
        ...

    def register_bot(self):
        ...

    def rm_bot(self,bot_id):
        ...
