<?php
/**
 * Index/Home Route
 */

// Require authentication
Auth::requireAuth();

// Get database instance
$db = Database::getInstance()->getPdo();

// Handle file upload
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['file'])) {
    $file = $_FILES['file'];
    
    if ($file['error'] === UPLOAD_ERR_OK) {
        $filename = basename($file['name']);
        $targetPath = UPLOAD_FOLDER . '/' . $filename;
        
        // Check if file already exists
        if (file_exists($targetPath)) {
            $filename = pathinfo($filename, PATHINFO_FILENAME) . '_' . time() . '.' . pathinfo($filename, PATHINFO_EXTENSION);
            $targetPath = UPLOAD_FOLDER . '/' . $filename;
        }
        
        if (move_uploaded_file($file['tmp_name'], $targetPath)) {
            $success = '文件上传成功';
        } else {
            $error = '文件上传失败';
        }
    } else {
        $error = '文件上传错误: ' . $file['error'];
    }
}

// Get files list
$files = [];
if (is_dir(UPLOAD_FOLDER)) {
    $iterator = new DirectoryIterator(UPLOAD_FOLDER);
    foreach ($iterator as $fileinfo) {
        if ($fileinfo->isFile() && !$fileinfo->isDot()) {
            $files[] = [
                'name' => $fileinfo->getFilename(),
                'size' => $fileinfo->getSize(),
                'modified' => $fileinfo->getMTime()
            ];
        }
    }
}

// Sort files by modified time (newest first)
usort($files, function($a, $b) {
    return $b['modified'] - $a['modified'];
});

// Get settings
$stmt = $db->query("SELECT * FROM settings");
$settings = [];
while ($row = $stmt->fetch()) {
    $settings[$row['key']] = $row['value'];
}

$announcement = $settings['announcement'] ?? '';

// Render view
include __DIR__ . '/../../templates/index.php';
?>