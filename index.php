<?php
/**
 * NexFile - PHP File Management System
 * Entry Point
 */

require_once __DIR__ . '/src/config.php';
require_once __DIR__ . '/src/database.php';
require_once __DIR__ . '/src/auth.php';
require_once __DIR__ . '/src/files.php';
require_once __DIR__ . '/src/onlyoffice.php';

// Initialize session
session_start();

// Initialize database
$db = Database::getInstance();

// Parse URL
$uri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$uri = str_replace('/index.php', '', $uri);
$uri = trim($uri, '/');

// Route handling
if ($uri === '' || $uri === 'index') {
    require __DIR__ . '/src/routes/index.php';
} elseif ($uri === 'login') {
    require __DIR__ . '/src/routes/login.php';
} elseif ($uri === 'logout') {
    require __DIR__ . '/src/routes/logout.php';
} elseif ($uri === 'admin') {
    require __DIR__ . '/src/routes/admin.php';
} elseif (preg_match('/^download\/(.*)$/', $uri, $matches)) {
    $_GET['filename'] = urldecode($matches[1]);
    require __DIR__ . '/src/routes/download.php';
} elseif (preg_match('/^delete\/(.*)$/', $uri, $matches)) {
    $_GET['filename'] = urldecode($matches[1]);
    require __DIR__ . '/src/routes/delete.php';
} elseif (preg_match('/^analyze\/(.*)$/', $uri, $matches)) {
    $_GET['filename'] = urldecode($matches[1]);
    require __DIR__ . '/src/routes/analyze.php';
} elseif (preg_match('/^editor\/(.*)$/', $uri, $matches)) {
    $_GET['filename'] = urldecode($matches[1]);
    require __DIR__ . '/src/routes/editor.php';
} elseif (preg_match('/^callback\/(.*)$/', $uri, $matches)) {
    $_GET['filename'] = urldecode($matches[1]);
    require __DIR__ . '/src/routes/callback.php';
} else {
    // 404 Not Found
    http_response_code(404);
    require __DIR__ . '/src/routes/404.php';
}
?>