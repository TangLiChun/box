<?php
/**
 * Delete File Route
 */

// Require authentication
Auth::requireAuth();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    die('Method not allowed');
}

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

// Move to trash instead of deleting
$trashPath = TRASH_FOLDER . '/' . $filename;
$counter = 1;
while (file_exists($trashPath)) {
    $info = pathinfo($filename);
    $trashPath = TRASH_FOLDER . '/' . $info['filename'] . '_' . $counter . '.' . $info['extension'];
    $counter++;
}

if (rename($filepath, $trashPath)) {
    // Store metadata in database
    $db = Database::getInstance()->getPdo();
    $stmt = $db->prepare("INSERT INTO trash_metadata (filename, original_name, deleted_at) VALUES (?, ?, datetime('now'))");
    $stmt->execute([basename($trashPath), $filename]);
    
    header('Location: /?success=文件已删除到回收站');
} else {
    header('Location: /?error=删除失败');
}
exit;
