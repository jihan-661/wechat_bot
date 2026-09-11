from flask import Flask

import bot.wechat_bot

app = Flask(__name__)
class route:
    def __init__(self,bot_manager:bot.wechat_bot.BotManager):
        self.bot_manager = bot_manager

    @app.get("/register_bot")
    def register_bot(self):
        self.bot_manager.add_new_bot()