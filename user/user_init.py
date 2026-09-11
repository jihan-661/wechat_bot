import wechatbot.types
import openai
import log
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
        self._user_steps[user_id] = {"config": {}}
        await self.bot.reply(msg, f"请输入{self.CONFIG_FIELDS[0]}")
        return True

    async def _collect_config(self, msg) -> bool:
        """收集一条配置输入"""
        user_id = msg.user_id
        config = self._user_steps[user_id]["config"]

        # 找到第一个空字段，把msg.text存进去
        for field in self.CONFIG_FIELDS:
            if field not in config:
                config[field] = msg.text
                break

        # 检查是否还有空字段
        for field in self.CONFIG_FIELDS:
            if field not in config:
                await self.bot.reply(msg, f"请输入{field}")
                return True

        # 全部填完，验证配置
        invalid_fields = await self._validate_config(config)
        if invalid_fields:
            for field in invalid_fields:
                del config[field]
            await self.bot.reply(msg, f"验证失败，请重新输入{self.CONFIG_FIELDS[0]}")
            return True

        # 验证通过，写入数据库
        self.db.insert("user", {"id": user_id})
        self.db.insert("user_config", {"user_id": user_id, **config})
        del self._user_steps[user_id]
        await self.bot.reply(msg, "配置完成！欢迎使用WeChatBot")
        return True

    async def _validate_config(self, config: dict) -> list[str]:
        """验证配置，返回有问题的字段列表，空列表表示全部通过"""
        invalid = []
        try:
            client = openai.Client(api_key=config["api_key"], base_url=config["base_url"])
            client.models.list()
        except Exception:
            invalid.extend(["api_key", "base_url"])
        return invalid

    #中间件
    async def user_init(self,parm_dict: dict):
        """
        此函数为前置中间件,请将此函数注册到before_stage事件列表中,负责校验数据中是否存在此用户并进行初始化引导
        注:若无此中间件无法正常使用LLM功能,用户注册功能,对话管理功能等
        :param parm_dict:参数字典
        :return: None
        """
        log.logger.info("调用user_init中间件")
        if await self.handle(parm_dict["msg"]):
            return

