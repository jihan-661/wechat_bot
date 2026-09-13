# 创建业务数据库（统一全小写：Linux 下 MySQL 区分大小写，必须与 USE wechatbot / .env.json 的 db 字段一致）
create database wechatbot;

# 创建业务用户（MySQL 用户名不区分大小写，此处与 .env.json 的 user 字段保持一致）
create user 'WeChatBot'@'localhost' identified by 'your_password';

# 授权（注意：必须写 库名.* ，单独写库名是语法错误）
GRANT ALL PRIVILEGES ON wechatbot.* TO 'WeChatBot'@'localhost';

# 刷新权限
flush privileges;
