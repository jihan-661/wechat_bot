import asyncio
import json
import sys
import getopt
from bot import ai,wechat_bot
from log import logger  # 导入全局单例日志实例

# 全局配置对象：所有下级业务模块导入此变量使用
config: dict = {}


def setting_config(path: str) -> None:
    """加载指定路径的JSON配置文件，结果写入全局config"""
    global config
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"配置文件不存在: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"配置文件JSON格式错误: {e}")
        sys.exit(1)


# 参数映射表：支持长短选项扩展
argv_handler = {
    ("--config_path", "-c"): setting_config
}


def main():
    """程序唯一入口：仅在此处解析命令行"""
    short_opts = "c:"
    long_opts = ["config_path="]

    try:
        opts, _ = getopt.getopt(sys.argv[1:], short_opts, long_opts)
    except getopt.GetoptError as e:
        logger.error(f"参数错误: {e}")
        logger.error("示例: python start.py -c ./config/prod.json")
        sys.exit(1)

    # 匹配参数处理函数
    for opt, value in opts:
        for (long_opt, short_opt), handler in argv_handler.items():
            if opt in (long_opt, short_opt):
                handler(value)
                break

    # 校验必填配置
    if not config:
        logger.error("未指定配置文件，请使用 -c/--config_path 传入")
        sys.exit(1)

    # ========== 启动核心业务 ==========
    logger.info("配置加载完成，服务启动中...")
    # 此处调用你的核心服务启动逻辑

    #注册Ai实例
    logger.info("初始化AI服务")
    ai_client = ai.AiClient(api_key=config["ai"]["api_key"],base_url=config["ai"]["base_url"],model=config["ai"]["model"])
    #初始化bot服务
    logger.info("初始化bot客户端")
    bot_client = wechat_bot.Bot(ai_client)
    #启动bot
    logger.info("正在启动bot")
    asyncio.run(bot_client.start())
    logger.info("初始化完成")


if __name__ == "__main__":
    main()
