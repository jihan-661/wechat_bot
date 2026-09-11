import asyncio

from wechatbot import WeChatBot
from database.database import Database
from . import ai
from user.user_init import InitUser
from log import logger
from user import user_init
import flask

class Bot:
    def __init__(self, db: Database):
        self.bot = WeChatBot()
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

        # 正常聊天
        logger.info(f"用户ID: {msg.user_id}")
        logger.info(f"接收到信息:{msg.text}")
        ai_res = parm_dict["ai_client"].get_ai_res("user", content=msg.text)
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
    def __init__(self, db: Database):
        self._bots: dict[str, Bot] = {}
        self.db = db
        self._tasks: list[asyncio.Task] = []  # 防 GC
        self._middleware = []

    def register_handler(self, stage: str, handler):
        """注册默认中间件，所有 bot 都会加载"""
        self._middleware.append((stage, handler))


    def _apply_middleware(self, bot: Bot):
        for stage, handler in self._middleware:
            self.register_init_user(bot)
            bot.register_handler(stage, handler)
    def _apply_one_middleware(self,bot:Bot,stage,middleware):
        bot.register_handler(stage,middleware)

    def register_init_user(self,bot:Bot):
        init_user = user_init.InitUser(self.db, bot)
        self._apply_one_middleware(bot, "before_reply", init_user)

    def get_bot(self, bot_id: str) -> Bot | None:
        return self._bots.get(bot_id)

    def add_bot(self, bot_id: str, bot: Bot,):
        self._apply_middleware(bot)
        """加入管理并启动"""
        self._bots[bot_id] = bot
        # 后台启动，不阻塞
        asyncio.create_task(bot.start())

    def del_bot(self, bot_id: str):
        bot = self._bots.pop(bot_id, None)
        if bot:
            bot.bot.stop()

    async def load_from_db(self):
        """启动时从数据库恢复所有 bot"""
        rows = self.db.select("bot", where="status=1")
        for row in rows:
            bot_id = row["name"]
            bot = Bot(self.db)
            bot.bot_id = bot_id
            self._bots[bot_id] = bot
            self._apply_middleware(bot)
            self._tasks.append(asyncio.create_task(bot.start()))

    async def add_new_bot(self) -> str:
        """交互式添加：扫码登录 → 存数据库 → 启动"""
        bot = Bot(self.db)
        wechat_bot = bot.bot
        creds = await wechat_bot.login()  # 弹二维码，等扫码
        bot.bot_id = creds.account_id
        # 存数据库（已存在则忽略）
        #我们没有bot表,数据库已经回退了,需要存的是用户id如果用户不存在的话
        # self.db.insert("bot", {"name": bot.bot_id})
        if not self.db.select("user",["id"]):
            self.db.insert("user",{
                "id": creds.user_id
            })
        self._bots[bot.bot_id] = bot
        await asyncio.create_task(wechat_bot.start())
        return bot.bot_id
    def register_bot_api(self):
        bot = Bot(self.db)
        wechat_bot = bot.bot
        return bot.bot.get_credentials()

class BotRoute:
    def __init__(self):
        self.base_url = "/bot"
        ...

    def register_bot(self):
        ...

    def rm_bot(self,bot_id):
        ...


