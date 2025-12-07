DROP TABLE IF EXISTS `account_logs`;
CREATE TABLE `account_logs` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `account_id` int NOT NULL,
  `owner_id` int NOT NULL,
  `transaction_id` int DEFAULT NULL,
  `action` enum('create','update','delete','deposit','withdraw','adjust') NOT NULL,
  `old_balance` decimal(12,2) DEFAULT NULL,
  `new_balance` decimal(12,2) DEFAULT NULL,
  `changed_fields` json DEFAULT NULL,
  `old_data` json DEFAULT NULL,
  `new_data` json DEFAULT NULL,
  `is_global` tinyint(1) DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`),
  KEY `idx_account` (`account_id`),
  KEY `idx_user` (`owner_id`),
  KEY `idx_txn` (`transaction_id`),
  KEY `idx_action` (`action`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `fk_log_account` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_log_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_log_transaction` FOREIGN KEY (`transaction_id`) REFERENCES `transactions` (`transaction_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `accounts`;
CREATE TABLE `accounts` (
  `account_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `account_type` enum('cash','bank','wallet','mobile_money','savings','credit','other') NOT NULL DEFAULT 'mobile_money',
  `balance` decimal(12,2) NOT NULL DEFAULT '0.00',
  `opening_balance` decimal(12,2) NOT NULL DEFAULT '0.00',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `owner_id` int NOT NULL,
  `is_global` tinyint(1) NOT NULL DEFAULT '0',
  `description` text,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`),
  KEY `idx_owner` (`owner_id`),
  KEY `idx_global` (`is_global`),
  KEY `idx_active` (`is_active`),
  KEY `idx_deleted` (`is_deleted`),
  CONSTRAINT `fk_accounts_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `audit_log`;
CREATE TABLE `audit_log` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `target_table` varchar(50) NOT NULL,
  `target_id` int NOT NULL,
  `action` enum('INSERT','UPDATE','DELETE','ACCESS') NOT NULL,
  `changed_fields` json DEFAULT NULL,
  `old_values` json DEFAULT NULL,
  `new_values` json DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `user_agent` varchar(255) DEFAULT NULL,
  `is_global` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`log_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `audit_log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `categories`;
CREATE TABLE `categories` (
  `category_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `parent_id` int DEFAULT NULL,
  `is_global` tinyint(1) NOT NULL DEFAULT '0',
  `owner_id` int NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint(1) DEFAULT '0',
  `updated_by` int DEFAULT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `unique_category_per_parent` (`name`,`parent_id`,`owner_id`),
  KEY `idx_parent` (`parent_id`),
  KEY `idx_owner` (`owner_id`),
  KEY `idx_updated_by` (`updated_by`),
  KEY `idx_owner_global` (`owner_id`,`is_global`),
  CONSTRAINT `fk_categories_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_categories_parent` FOREIGN KEY (`parent_id`) REFERENCES `categories` (`category_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_categories_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `recurring_logs`;
CREATE TABLE `recurring_logs` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `owner_id` int NOT NULL,
  `recurring_id` int NOT NULL,
  `run_date` datetime NOT NULL,
  `status` enum('generated','skipped','failed') NOT NULL,
  `amount_used` decimal(12,2) NOT NULL,
  `override_used` tinyint(1) NOT NULL DEFAULT '0',
  `posted_transaction_id` int DEFAULT NULL,
  `message` text,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`),
  KEY `fk_recurring_log_recurring` (`recurring_id`),
  KEY `fk_recurring_log_user` (`owner_id`),
  CONSTRAINT `fk_recurring_log_recurring` FOREIGN KEY (`recurring_id`) REFERENCES `recurring_transactions` (`recurring_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_recurring_log_user` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `recurring_transactions`;
CREATE TABLE `recurring_transactions` (
  `recurring_id` int NOT NULL AUTO_INCREMENT,
  `owner_id` int NOT NULL,
  `is_global` tinyint(1) DEFAULT '0',
  `name` varchar(120) NOT NULL,
  `description` text,
  `frequency` enum('daily','weekly','monthly','yearly') NOT NULL,
  `interval_value` int DEFAULT '1',
  `next_due` datetime NOT NULL,
  `last_run` datetime DEFAULT NULL,
  `max_missed_runs` int DEFAULT '12',
  `last_run_status` enum('success','failed','skipped') DEFAULT 'success',
  `pause_until` date DEFAULT NULL,
  `skip_next` tinyint(1) DEFAULT '0',
  `override_amount` decimal(12,2) DEFAULT NULL,
  `amount` decimal(12,2) NOT NULL,
  `category_id` int DEFAULT NULL,
  `transaction_type` enum('income','expense','debt','transfer','other') NOT NULL DEFAULT 'expense',
  `payment_method` enum('cash','bank','mobile_money','credit_card','other') NOT NULL DEFAULT 'mobile_money',
  `notes` text,
  `is_active` tinyint(1) DEFAULT '1',
  `is_deleted` tinyint(1) DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`recurring_id`),
  KEY `fk_rec_owner` (`owner_id`),
  CONSTRAINT `fk_rec_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `transactions`;
CREATE TABLE `transactions` (
  `transaction_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `category_id` int DEFAULT NULL,
  `parent_transaction_id` int DEFAULT NULL,
  `title` varchar(150) NOT NULL,
  `description` text,
  `amount` decimal(12,2) NOT NULL,
  `transaction_type` enum('income','expense','transfer','debts') NOT NULL,
  `payment_method` enum('cash','bank','mobile_money','credit_card','other') NOT NULL DEFAULT 'mobile_money',
  `transaction_date` date NOT NULL,
  `is_global` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`transaction_id`),
  KEY `parent_transaction_id` (`parent_transaction_id`),
  KEY `idx_user_date` (`user_id`,`transaction_date`),
  KEY `idx_category` (`category_id`),
  KEY `idx_owner_global` (`user_id`,`is_global`),
  CONSTRAINT `transactions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `transactions_ibfk_2` FOREIGN KEY (`category_id`) REFERENCES `categories` (`category_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `transactions_ibfk_3` FOREIGN KEY (`parent_transaction_id`) REFERENCES `transactions` (`transaction_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `transactions_chk_1` CHECK ((`amount` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `security_question` varchar(255) DEFAULT 'What is your favourite colour?',
  `security_answer_hash` varchar(255) NOT NULL,
  `role` enum('admin','user') NOT NULL DEFAULT 'user',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

