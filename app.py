import time

from flask import Flask

import bot.wechat_bot

app = Flask(__name__)
class Route:
    def __init__(self,bot_manager:bot.wechat_bot.BotManager):
        self.bot_manager = bot_manager
        app.add_url_rule("/register_bot", view_func=self.register_bot, methods=["GET"])

    def register_bot(self):
        bot = self.bot_manager.register_bot_api()
        deadline = time.time() + 20
        while time.time() < deadline:  # 必须带超时
            if bot.qr_url:
                return bot.qr_url
            time.sleep(0.1)
        return "二维码生成超时，请重试", 504