-- Création base + paramètres
CREATE DATABASE IF NOT EXISTS `SNMP`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `SNMP`;

-- Table des utilisateurs
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(80) NOT NULL,
  `email` VARCHAR(255) DEFAULT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `role` ENUM('admin','operator') NOT NULL DEFAULT 'operator',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_username` (`username`),
  UNIQUE KEY `uq_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Groupes (réutilisables entre hosts)
CREATE TABLE IF NOT EXISTS `groups` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(80) NOT NULL,
  `description` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_groups_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Templates de scan (réutilisables)
CREATE TABLE IF NOT EXISTS `templates` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(80) NOT NULL,
  `description` TEXT DEFAULT NULL,
  -- champs optionnels pour évoluer plus tard
  `snmp_version` ENUM('v1','v2c','v3') DEFAULT NULL,
  `params` JSON DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_templates_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tags (ex: prod, router, snmpv2)
CREATE TABLE IF NOT EXISTS `tags` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tags_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hosts
CREATE TABLE IF NOT EXISTS `hosts` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `hostname` VARCHAR(120) NOT NULL,
  `description` VARCHAR(255) DEFAULT NULL,
  `ip` VARCHAR(45) NOT NULL,
  `port` INT NOT NULL DEFAULT 161,
  `group_id` INT UNSIGNED DEFAULT NULL,
  `template_id` INT UNSIGNED DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hosts_hostname` (`hostname`),
  KEY `idx_hosts_ip_port` (`ip`,`port`),
  KEY `idx_hosts_group_id` (`group_id`),
  KEY `idx_hosts_template_id` (`template_id`),
  CONSTRAINT `fk_hosts_group`
    FOREIGN KEY (`group_id`) REFERENCES `groups` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT `fk_hosts_template`
    FOREIGN KEY (`template_id`) REFERENCES `templates` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Liaison Host <-> Tags (N:N)
CREATE TABLE IF NOT EXISTS `host_tags` (
  `host_id` INT UNSIGNED NOT NULL,
  `tag_id` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`host_id`, `tag_id`),
  KEY `idx_host_tags_tag` (`tag_id`),
  CONSTRAINT `fk_host_tags_host`
    FOREIGN KEY (`host_id`) REFERENCES `hosts` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT `fk_host_tags_tag`
    FOREIGN KEY (`tag_id`) REFERENCES `tags` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- (Optionnel) utilisateur admin par défaut (hash SHA2 pour exemple)
-- ATTENTION : en prod, stocke un hash bcrypt/argon2 géré côté app.
INSERT INTO `users` (`username`,`email`,`password_hash`,`role`)
VALUES ('admin','admin@example.com', UPPER(SHA2('admin', 256)), 'admin')
ON DUPLICATE KEY UPDATE username = username;