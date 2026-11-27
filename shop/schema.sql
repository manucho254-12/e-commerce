CREATE DATABASE IF NOT EXISTS shop_db CHARACTER SET utf8mb4;
USE shop_db;
CREATE TABLE IF NOT EXISTS users(
  id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), email VARCHAR(120) UNIQUE,
  phone VARCHAR(20), password VARCHAR(255), is_admin TINYINT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products(
  id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150), description TEXT,
  price DECIMAL(10,2), stock INT DEFAULT 0, image VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS orders(
  id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, total DECIMAL(10,2),
  phone VARCHAR(20), address VARCHAR(255),
  status ENUM('pending','approved','rejected','payment_submitted','paid','payment_rejected') DEFAULT 'pending',
  pay_instructions TEXT, mpesa_code VARCHAR(30) UNIQUE, admin_note VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS order_items(
  id INT AUTO_INCREMENT PRIMARY KEY, order_id INT, product_id INT,
  name VARCHAR(150), price DECIMAL(10,2), qty INT,
  FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE);
