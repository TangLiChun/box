<?php
/**
 * ONLYOFFICE Callback Route
 */

$filename = $_GET['filename'] ?? '';
$token = $_GET['token'] ?? '';

if (empty($filename) || empty($token)) {
    http_response_code(400);
    echo json_encode(['error' => 1, 'message' => 'Missing parameters']);
    exit;
}

// Validate token
$expectedToken = hash_hmac('sha256', $filename . ':callback', SECRET_KEY);
if (!hash_equals($expectedToken, $token)) {
    http_response_code(403);
    echo json_encode(['error' => 1, 'message' => 'Invalid token']);
    exit;
}

// Get JSON input
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!$data || !isset($data['status'])) {
    http_response_code(400);
    echo json_encode(['error' => 1, 'message' => 'Invalid JSON']);
    exit;
}

$status = $data['status'];

// Handle save (status 2 or 6)
if ($status == 2 || $status == 6) {
    $downloadUrl = $data['url'] ?? '';
    
    if (empty($downloadUrl)) {
        http_response_code(400);
        echo json_encode(['error' => 1, 'message' => 'Missing download URL']);
        exit;
    }
    
    // Download and save file
    $ch = curl_init($downloadUrl);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    
    $fileContent = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || $fileContent === false) {
        http_response_code(502);
        echo json_encode(['error' => 1, 'message' => 'Download failed']);
        exit;
    }
    
    // Save file
    $filepath = UPLOAD_FOLDER . '/' . $filename;
    if (file_put_contents($filepath, $fileContent) === false) {
        http_response_code(500);
        echo json_encode(['error' => 1, 'message' => 'Save failed']);
        exit;
    }
    
    echo json_encode(['error' => 0]);
    exit;
}

// Other statuses
header('Content-Type: application/json');
echo json_encode(['error' => 0]);
?>