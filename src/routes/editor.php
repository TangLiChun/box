<?php
/**
 * ONLYOFFICE Editor Route
 */

Auth::requireAuth();

$filename = $_GET['filename'] ?? '';

if (empty($filename)) {
    header('Location: /');
    exit;
}

// Sanitize filename
$filename = basename($filename);
$filepath = UPLOAD_FOLDER . '/' . $filename;

if (!file_exists($filepath)) {
    header('Location: /?error=文件不存在');
    exit;
}

// Check if file is editable
if (!FileManager::isEditable($filename)) {
    header('Location: /?error=该文件格式不支持在线编辑');
    exit;
}

// Get ONLYOFFICE settings
$db = Database::getInstance()->getPdo();
$stmt = $db->query("SELECT * FROM settings WHERE key LIKE 'onlyoffice%'");
$ooSettings = [];
while ($row = $stmt->fetch()) {
    $ooSettings[$row['key']] = $row['value'];
}

$onlyofficeUrl = $ooSettings['onlyoffice_url'] ?? '';

if (empty($onlyofficeUrl)) {
    header('Location: /?error=ONLYOFFICE未配置');
    exit;
}

// Generate document key
$stat = stat($filepath);
$keySeed = $filename . ':' . $stat['mtime'];
$docKey = 'doc_' . substr(hash('sha256', $keySeed), 0, 32);

// Generate tokens
$downloadToken = hash_hmac('sha256', $filename, SECRET_KEY);
$callbackToken = hash_hmac('sha256', $filename . ':callback', SECRET_KEY);

// Get file extension
$ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));

// Build ONLYOFFICE config
$config = [
    'document' => [
        'fileType' => $ext,
        'key' => $docKey,
        'title' => $filename,
        'url' => '/download/' . urlencode($filename) . '?token=' . $downloadToken,
    ],
    'documentType' => $ONLYOFFICE_FORMATS['.' . $ext] ?? 'word',
    'editorConfig' => [
        'callbackUrl' => '/callback/' . urlencode($filename) . '?token=' . $callbackToken,
        'user' => [
            'id' => (string)Auth::getUserId(),
            'name' => Auth::getUsername(),
        ],
        'lang' => 'zh-CN',
        'customization' => [
            'forcesave' => true,
        ],
    ],
];

// JWT secret
$jwtSecret = $ooSettings['onlyoffice_jwt_secret'] ?? '';
if (!empty($jwtSecret)) {
    // Generate JWT token
    $header = json_encode(['typ' => 'JWT', 'alg' => 'HS256']);
    $payload = json_encode($config);
    $base64Header = str_replace(['+', '/', '='], ['-', '_', ''], base64_encode($header));
    $base64Payload = str_replace(['+', '/', '='], ['-', '_', ''], base64_encode($payload));
    $signature = hash_hmac('sha256', $base64Header . '.' . $base64Payload, $jwtSecret, true);
    $base64Signature = str_replace(['+', '/', '='], ['-', '_', ''], base64_encode($signature));
    $config['token'] = $base64Header . '.' . $base64Payload . '.' . $base64Signature;
}

// Render editor
include __DIR__ . '/../../templates/editor.php';
