<?php
/**
 * Authentication Manager
 */
class Auth {
    
    /**
     * Check if user is logged in
     */
    public static function isLoggedIn() {
        return isset($_SESSION['user_id']) && $_SESSION['user_id'] > 0;
    }
    
    /**
     * Get current user ID
     */
    public static function getUserId() {
        return $_SESSION['user_id'] ?? null;
    }
    
    /**
     * Get current username
     */
    public static function getUsername() {
        return $_SESSION['username'] ?? null;
    }
    
    /**
     * Check if current user is admin
     */
    public static function isAdmin() {
        if (!self::isLoggedIn()) return false;
        
        $db = Database::getInstance()->getPdo();
        $stmt = $db->prepare("SELECT is_admin FROM users WHERE id = ?");
        $stmt->execute([$_SESSION['user_id']]);
        $result = $stmt->fetch();
        return $result && $result['is_admin'] == 1;
    }
    
    /**
     * Authenticate user
     */
    public static function login($username, $password) {
        $db = Database::getInstance()->getPdo();
        $stmt = $db->prepare("SELECT id, username, password FROM users WHERE username = ?");
        $stmt->execute([$username]);
        $user = $stmt->fetch();
        
        if ($user && password_verify($password, $user['password'])) {
            $_SESSION['user_id'] = $user['id'];
            $_SESSION['username'] = $user['username'];
            return true;
        }
        
        return false;
    }
    
    /**
     * Logout user
     */
    public static function logout() {
        session_destroy();
        $_SESSION = [];
    }
    
    /**
     * Require authentication
     */
    public static function requireAuth() {
        if (!self::isLoggedIn()) {
            header('Location: /login');
            exit;
        }
    }
    
    /**
     * Require admin access
     */
    public static function requireAdmin() {
        self::requireAuth();
        if (!self::isAdmin()) {
            http_response_code(403);
            die('Access denied');
        }
    }
}
