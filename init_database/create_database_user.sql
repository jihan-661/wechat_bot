#创建业务数据表
create database WeChatBot;
#创建业务用户
create user 'WeChatBot'@'localhost' identified by 'your_password';
#授权
GRANT ALL PRIVILEGES ON WcChatBot TO 'WeChatBot'@'localhost';
#刷新权限
flush privileges;
