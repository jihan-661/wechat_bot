import logging
from typing import Optional


class Log:
    _instance: Optional["Log"] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        # 单例：保证整个项目只有一个Log包装实例
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance

    def _setup_logger(self):
        """初始化日志配置，只执行一次"""
        self._logger = logging.getLogger("my_project_logger")
        # 避免重复添加handler
        if self._logger.handlers:
            return

        self._logger.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)s:%(filename)s-%(lineno)d %(funcName)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        self._logger.addHandler(console_handler)

    def get_log(self) -> logging.Logger:
        """对外获取logger实例，全局拿到同一个logger"""
        return self._logger


# 全局快捷实例，项目其他地方直接导入使用
logger = Log().get_log()
