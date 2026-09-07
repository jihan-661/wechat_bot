USE wechatbot;

-- 用户配置表
CREATE TABLE `user_config` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '配置主键',
  `user_id` VARCHAR(64) NOT NULL COMMENT '关联user.id',
  `api_key` VARCHAR(512) NULL COMMENT '大模型API密钥',
  `base_url` VARCHAR(512) NULL COMMENT '接口base地址',
  `model` VARCHAR(128) NULL COMMENT '模型名称',
  `prompt` TEXT NULL COMMENT '系统提示词',
  `extend` JSON NULL COMMENT '扩展参数，temperature、top_p等',
  `last_update` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '配置修改时间',
  PRIMARY KEY (`id`),
  INDEX `idx_user_id` (`user_id`),
  CONSTRAINT `fk_config_user` FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COMMENT='用户LLM配置表';
