<?php
/**
 * Logout Route
 */

// Clear session
session_destroy();
$_SESSION = [];

// Redirect to login
header('Location: /login');
exit;
?>