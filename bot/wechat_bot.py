from wechatbot import WeChatBot
from . import ai
from log import logger
class Bot:
    def __init__(self,ai:ai.AiClient):
        self.bot = WeChatBot()
        self.ai = ai
        self.bot.on_message(self.on_message)
    async def login(self):
        await self.bot.login()
    async def on_message(self,msg):
        logger.info(f"用户ID: {msg.user_id}")
        logger.info(f"接收到信息:{msg.text}")
        ai_res = self.ai.get_ai_res("user",content=msg.text)
        logger.info(f"回复信息:{ai_res}")
        await self.bot.send_typing(msg.user_id)
        await self.bot.reply(msg, ai_res)
    async def start(self):
        await self.login()
        await self.bot.start()


