from database import database

class Memory_Manage:
    def __init__(self,db:database.Database):
        self.db = db
    def write_memory(self,parm:dict):
        """
        记忆写入中间件,使用此中间件需要在回复中阶段注册
        :param parm:
        :return:
        """
        role = parm["now_role"]
