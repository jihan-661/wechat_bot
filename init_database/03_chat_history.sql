USE wechatbot;

-- 聊天历史表
CREATE TABLE `chat_history` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '消息主键',
  `user_id` VARCHAR(64) NOT NULL COMMENT '关联user.id',
  `session_id` VARCHAR(64) NOT NULL COMMENT '会话ID',
  `role` VARCHAR(32) NOT NULL COMMENT 'user / assistant',
  `content` TEXT NOT NULL COMMENT '消息内容',
  `timestamp` DATETIME NOT NULL COMMENT '消息时间',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1有效，0逻辑删除',
  PRIMARY KEY (`id`),
  INDEX `idx_uid_sid` (`user_id`, `session_id`),
  CONSTRAINT `fk_history_user` FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COMMENT='聊天历史记录表';
