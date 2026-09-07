from database import database


class InitUser:
    """
    初始化用户引导服务
    当用户首次使用时，通过聊天交互收集配置并写入数据库
    """

    CONFIG_FIELDS = ["api_key", "base_url", "model", "prompt"]

    def __init__(self, db: database.Database, bot):
        self.db = db
        self.bot = bot
        # {user_id: 当前等待的字段索引}
        self._user_steps = {}

    def is_handling(self, user_id: str) -> bool:
        """判断用户是否正在配置流程中"""
        return user_id in self._user_steps

    def is_in_database(self, user_id: str) -> bool:
        """查询用户是否已注册"""
        return bool(self.db.select("user", where="id=%s", params=(user_id,)))

    async def handle(self, msg) -> bool:
        """
        处理消息入口
        :return: True=已处理, False=不需要处理
        """
        user_id = msg.user_id

        # 正在配置中的用户，继续收集（不查数据库）
        if self.is_handling(user_id):
            return await self._collect_config(msg)

        # 已注册用户，不处理
        if self.is_in_database(user_id):
            return False

        # 新用户，启动配置流程
        self._user_steps[user_id] = {
            "index": 0,
            "config": {}
        }
        await self.bot.reply(msg, f"请输入{self.CONFIG_FIELDS[0]}")
        return True

    async def _collect_config(self, msg) -> bool:
        """收集一条配置输入"""
        user_id = msg.user_id
        step = self._user_steps[user_id]
        index = step["index"]
        config = step["config"]

        # 把用户输入存到当前字段
        field = self.CONFIG_FIELDS[index]
        config[field] = msg.text
        index += 1

        # 还有下一个字段，继续提示
        if index < len(self.CONFIG_FIELDS):
            step["index"] = index
            await self.bot.reply(msg, f"请输入{self.CONFIG_FIELDS[index]}")
            return True

        # 全部填完，写入数据库
        self.db.insert("user", {"id": user_id})
        self.db.insert("user_config", {"user_id": user_id, **config})
        del self._user_steps[user_id]
        await self.bot.reply(msg, "配置完成！欢迎使用WeChatBot")
        return True
