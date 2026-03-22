<?php
/**
 * Download File Route
 */

// Require authentication
Auth::requireAuth();

$filename = $_GET['filename'] ?? '';

if (empty($filename)) {
    http_response_code(400);
    die('Filename required');
}

// Sanitize filename
$filename = basename($filename);
$filepath = UPLOAD_FOLDER . '/' . $filename;

if (!file_exists($filepath)) {
    http_response_code(404);
    die('File not found');
}

// Check ONLYOFFICE download token
$token = $_GET['token'] ?? '';
if (!empty($token)) {
    // Validate token
    $expectedToken = hash_hmac('sha256', $filename, SECRET_KEY);
    if (!hash_equals($expectedToken, $token)) {
        http_response_code(403);
        die('Invalid token');
    }
} else {
    // Regular download, check authentication (already done above)
}

// Get MIME type
$finfo = finfo_open(FILEINFO_MIME_TYPE);
$mimeType = finfo_file($finfo, $filepath);
finfo_close($finfo);

// Set headers
header('Content-Type: ' . $mimeType);
header('Content-Disposition: attachment; filename="' . $filename . '"');
header('Content-Length: ' . filesize($filepath));
header('Cache-Control: no-cache, must-revalidate');

// Output file
readfile($filepath);
exit;
