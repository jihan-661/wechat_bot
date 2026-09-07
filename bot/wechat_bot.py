from wechatbot import WeChatBot
from database.database import Database
from . import ai
from user.user_init import InitUser
from log import logger


class Bot:
    def __init__(self, db: Database):
        self.bot = WeChatBot()
        self.db = db
        self.user_init = InitUser(db, self)
        # {user_id: AiClient} 缓存，避免每次消息都新建
        self._ai_clients = {}
        self.bot.on_message(self.on_message)

    def set_ai(self, ai_client: ai.AiClient):
        """注入全局AI实例（可选，用于默认配置）"""
        self._default_ai = ai_client

    def _get_ai(self, user_id: str) -> ai.AiClient:
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
        )
        self._ai_clients[user_id] = client
        return client

    async def login(self):
        await self.bot.login()

    async def on_message(self, msg):
        # 配置流程优先处理
        if await self.user_init.handle(msg):
            return

        # 获取用户的AI实例
        ai_client = self._get_ai(msg.user_id)
        if ai_client is None:
            await self.bot.reply(msg, "AI服务未初始化，请先完成配置")
            return

        # 正常聊天
        logger.info(f"用户ID: {msg.user_id}")
        logger.info(f"接收到信息:{msg.text}")
        ai_res = ai_client.get_ai_res("user", content=msg.text)
        logger.info(f"回复信息:{ai_res}")
        await self.bot.reply(msg, ai_res)

    async def start(self):
        await self.login()
        await self.bot.start()
