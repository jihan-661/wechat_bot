from database import database
import time

class Memory_Manage:
    def __init__(self,db:database.Database):
        self.db = db

    def write_memory(self,parm:dict):
        """
        记忆写入中间件,使用此中间件需要在回复中阶段注册
        :param parm:
        :return:
        """
        content = parm["now_content"]
        role = parm["now_role"]
        self.db.insert("chat_history",{
            "user_id":parm["msg"].user_id,
            "session_id":0,
            "role":role,
            "content": content,
        })
