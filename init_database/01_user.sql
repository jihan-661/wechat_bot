USE wechatbot;

-- 用户表（必须先创建，被其他表引用）
CREATE TABLE `user` (
  `id` VARCHAR(64) NOT NULL COMMENT '微信OpenID，直接当主键',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1正常，0禁用',
  `last_login` DATETIME NULL COMMENT '最后登录时间',
  PRIMARY KEY (`id`)
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
