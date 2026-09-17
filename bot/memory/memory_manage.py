from database import database
import time
from log import logger


class Memory_Manage:
    def __init__(self,db:database.Database):
        self.db = db

    async def write_memory(self,parm:dict):
        """
        记忆写入中间件,使用此中间件需要在回复中阶段注册
        :param parm:
        :return:
        """
        content = parm["now_content"]
        role = parm["now_role"]
        session_id= 0
        logger.debug(f"调用记忆写入中间件,写入角色:{role} 写入内容:{content} 会话id{session_id}")
        self.db.insert("chat_history",{
            "user_id": parm["msg"].user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
        })
