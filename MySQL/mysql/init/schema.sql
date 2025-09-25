-- ============================================================================
--  Base de données de supervision SNMP
--  Compatibilité : MySQL 8.x (InnoDB, utf8mb4)
-- ============================================================================

-- Création base + paramètres
CREATE DATABASE IF NOT EXISTS `SNMP`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `SNMP`;

-- ============================================================================
-- Table des utilisateurs
-- ============================================================================
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

-- ============================================================================
-- Groupes (réutilisables entre hosts)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `groups` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(80) NOT NULL,
  `description` VARCHAR(255) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_groups_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Templates de scan (réutilisables)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `templates` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(80) NOT NULL,
  `description` TEXT DEFAULT NULL,
  -- Champs optionnels pour évoluer plus tard
  `snmp_version` ENUM('v1','v2c','v3') DEFAULT NULL,
  `params` JSON DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_templates_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Tags (ex: prod, router, snmpv2)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `tags` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tags_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Hosts (avec champs SNMP v2c : communauté + catégories JSON)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `hosts` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `hostname` VARCHAR(120) NOT NULL,
  `description` VARCHAR(255) DEFAULT NULL,
  `ip` VARCHAR(45) NOT NULL,
  `port` INT NOT NULL DEFAULT 161,

  -- SNMP v2c uniquement
  `snmp_community` VARCHAR(128) DEFAULT 'public',
  `snmp_categories` JSON DEFAULT NULL,  -- ex: ["system","cpu","storage","interfaces"]

  `group_id` INT UNSIGNED DEFAULT NULL,
  `template_id` INT UNSIGNED DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hosts_hostname` (`hostname`),
  KEY `idx_hosts_ip_port` (`ip`,`port`),
  KEY `idx_hosts_group_id` (`group_id`),
  KEY `idx_hosts_template_id` (`template_id`),
  KEY `idx_hosts_snmp_community` (`snmp_community`),

  CONSTRAINT `fk_hosts_group`
    FOREIGN KEY (`group_id`) REFERENCES `groups` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT `fk_hosts_template`
    FOREIGN KEY (`template_id`) REFERENCES `templates` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- (Optionnel) initialiser les catégories à "system" si tu le souhaites :
-- UPDATE `hosts` SET `snmp_categories` = JSON_ARRAY('system') WHERE `snmp_categories` IS NULL;

-- ============================================================================
-- Liaison Host <-> Tags (N:N)
-- ============================================================================
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

-- ============================================================================
-- Alertes (historique des alertes) + ACK / Résolution
-- ============================================================================
CREATE TABLE IF NOT EXISTS `alerts` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `host_id` INT UNSIGNED DEFAULT NULL,
  `severity` ENUM('info','warning','critical') NOT NULL DEFAULT 'info',
  `message` VARCHAR(255) NOT NULL,

  -- Ack / Résolution
  `acknowledged_by` INT UNSIGNED DEFAULT NULL,
  `acknowledged_at` TIMESTAMP NULL DEFAULT NULL,
  `resolved_at` TIMESTAMP NULL DEFAULT NULL,

  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  KEY `idx_alerts_created_at` (`created_at`),
  KEY `idx_alerts_severity` (`severity`),
  KEY `idx_alerts_host_id` (`host_id`),
  KEY `idx_alerts_ack` (`acknowledged_at`),
  KEY `idx_alerts_resolved` (`resolved_at`),

  CONSTRAINT `fk_alerts_host`
    FOREIGN KEY (`host_id`) REFERENCES `hosts` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT `fk_alerts_ack_user`
    FOREIGN KEY (`acknowledged_by`) REFERENCES `users` (`id`)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Mesures brutes (historisation générique)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `measurements` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `host_id` INT UNSIGNED NOT NULL,
  `oid` VARCHAR(200) NOT NULL,
  `metric` VARCHAR(120) DEFAULT NULL,    -- ex: 'hrProcessorLoad', 'ifHCInOctets'
  `value` VARCHAR(255) NOT NULL,         -- stocké en texte pour souplesse
  `ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `meta` JSON DEFAULT NULL,              -- ex: index interface, unit, allocUnit...
  PRIMARY KEY (`id`),
  KEY `idx_meas_host_ts` (`host_id`,`ts`),
  KEY `idx_meas_metric_ts` (`metric`,`ts`),
  CONSTRAINT `fk_meas_host`
    FOREIGN KEY (`host_id`) REFERENCES `hosts` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Dernière valeur par OID (cache "courant" pour affichage rapide)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `current_metrics` (
  `host_id` INT UNSIGNED NOT NULL,
  `oid` VARCHAR(200) NOT NULL,
  `metric` VARCHAR(120) DEFAULT NULL,
  `value` VARCHAR(255) NOT NULL,
  `ts` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `meta` JSON DEFAULT NULL,
  PRIMARY KEY (`host_id`, `oid`),
  KEY `idx_curr_metric` (`metric`),
  CONSTRAINT `fk_curr_host`
    FOREIGN KEY (`host_id`) REFERENCES `hosts` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Journal des runs de poll (traçabilité / debug)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `poll_runs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `started_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `finished_at` TIMESTAMP NULL DEFAULT NULL,
  `status` ENUM('ok','partial','error') NOT NULL DEFAULT 'ok',
  `note` VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_poll_runs_started` (`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `poll_results` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `poll_run_id` BIGINT UNSIGNED NOT NULL,
  `host_id` INT UNSIGNED NOT NULL,
  `duration_ms` INT UNSIGNED DEFAULT NULL,
  `state` ENUM('ok','timeout','snmp_error','unreachable') NOT NULL DEFAULT 'ok',
  `error` VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_poll_results_run` (`poll_run_id`),
  KEY `idx_poll_results_host` (`host_id`),
  CONSTRAINT `fk_pollres_run`
    FOREIGN KEY (`poll_run_id`) REFERENCES `poll_runs` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT `fk_pollres_host`
    FOREIGN KEY (`host_id`) REFERENCES `hosts` (`id`)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Index supplémentaires utiles
-- ============================================================================
CREATE INDEX IF NOT EXISTS `idx_hosts_updated_at` ON `hosts` (`updated_at`);

-- ============================================================================
-- (Optionnel) Utilisateur admin par défaut (hash SHA2 d'exemple)
--   ⚠ En production, stocke un hash fort (pbkdf2/bcrypt/argon2) géré par l'app.
-- ============================================================================
INSERT INTO `users` (`username`,`email`,`password_hash`,`role`)
VALUES ('admin','admin@example.com', UPPER(SHA2('admin', 256)), 'admin')
ON DUPLICATE KEY UPDATE username = username;
