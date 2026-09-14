from openai import OpenAI
import json
from openai.types.chat import ChatCompletion
from log import logger

# try:
#     with open(".env.json","r") as f:
#         CONFIG = json.loads(f.read())
#         ai_log.info(f"载入配置文件成功")
# except Exception as e:
#     ai_log.error(f"载入配置文件失败:{e}")
# BASE_URL = CONFIG["ai"]["base_url"]
# API_KEY = CONFIG["ai"]["api_key"]
# MODEL = CONFIG["ai"]["model"]


class AiClient:
    def __init__(self,api_key,base_url,model,prompt = None):
        #创建ai客户端
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.ai_client = OpenAI(api_key=self.api_key,base_url=self.base_url)
        #初始化全局记忆列表
        self.message = []
        #如果有提示词,初始化提示词
        if prompt:
            self.add_message(role="system",content=prompt)


    def link_ai(self) -> ChatCompletion:
        """

        :param message: 消息列表
        :return: ChatCompletion对象,可通过访问属性获取ai回复
        """
        ai_handle = self.ai_client.chat.completions.create(
            model=self.model,
            messages=self.message,
            stream=False
        )
        return ai_handle

    def add_message(self,role: str, content: str) -> None:
        """

        :param role: 角色
        :param content: 输入内容
        :return: None
        """
        self.message.append({
            "role": role,
            "content": content
        })
    def get_ai_res(self,role: str, content: str) -> str:
        """

        :param role: 角色
        :param content: 内容
        :return: ai回复
        """
        self.add_message(role, content)
        ai_handle = self.link_ai()
        res = ai_handle.choices[0].message.content
        # 关键：AI 回复写回历史，否则多轮对话里 AI 看不到自己之前说过什么
        self.add_message("assistant", res)
        logger.debug(f"message上下文列表: type={type(self.message).__name__} len={len(self.message)} 内容={self.message}")
        return res

