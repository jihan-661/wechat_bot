"""
严格测试：两次登录之间完全清除凭证，不共享任何状态
"""
import asyncio
import os
from wechatbot import WeChatBot

CRED1 = "./strict_test_1.json"
CRED2 = "./strict_test_2.json"

async def main():
    # 第一次登录
    for f in [CRED1, CRED2]:
        if os.path.exists(f):
            os.remove(f)

    print("=== 第一次登录（干净状态）===")
    bot1 = WeChatBot(cred_path=CRED1)
    creds1 = await bot1.login(force=True)
    print(f"bot_id: {creds1.account_id}")
    print(f"user_id: {creds1.user_id}")

    # 第二次登录：用不同的凭证路径，且不传 local_token_list
    # 因为 CRED2 不存在，stored 为 None，local_token_list = []
    print("\n=== 第二次登录（完全干净，无 local_token_list）===")
    print("请用【同一个微信】扫描第二个二维码")
    bot2 = WeChatBot(cred_path=CRED2)
    creds2 = await bot2.login(force=True)
    print(f"bot_id: {creds2.account_id}")
    print(f"user_id: {creds2.user_id}")

    print("\n" + "=" * 50)
    if creds1.user_id == creds2.user_id:
        print(f"✅ user_id 相同: {creds1.user_id}")
        print("   严格测试确认：全局唯一，无复用干扰")
    else:
        print(f"❌ user_id 不同")
        print(f"   第一次: {creds1.user_id}")
        print(f"   第二次: {creds2.user_id}")

if __name__ == "__main__":
    asyncio.run(main())
