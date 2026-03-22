<?php
/**
 * NexFile Configuration
 */

// Base directory
define('BASE_DIR', dirname(__DIR__));
define('INSTANCE_DIR', BASE_DIR . '/instance');

// Upload paths
define('UPLOAD_FOLDER', INSTANCE_DIR . '/uploads');
define('NOTES_FOLDER', INSTANCE_DIR . '/notes');
define('TRASH_FOLDER', INSTANCE_DIR . '/trash');

// Database
define('DATABASE', INSTANCE_DIR . '/users.db');

// Security
define('SECRET_KEY', getenv('SECRET_KEY') ?: bin2hex(random_bytes(32)));
define('MAX_FILE_SIZE', 100 * 1024 * 1024); // 100MB

// ONLYOFFICE supported formats
$ONLYOFFICE_FORMATS = [
    '.docx' => 'word', '.doc' => 'word', '.odt' => 'word', '.rtf' => 'word', '.txt' => 'word',
    '.xlsx' => 'cell', '.xls' => 'cell', '.ods' => 'cell', '.csv' => 'cell',
    '.pptx' => 'slide', '.ppt' => 'slide', '.odp' => 'slide',
    '.pdf' => 'pdf'
];

// Ensure directories exist
if (!is_dir(INSTANCE_DIR)) mkdir(INSTANCE_DIR, 0755, true);
if (!is_dir(UPLOAD_FOLDER)) mkdir(UPLOAD_FOLDER, 0755, true);
if (!is_dir(NOTES_FOLDER)) mkdir(NOTES_FOLDER, 0755, true);
if (!is_dir(TRASH_FOLDER)) mkdir(TRASH_FOLDER, 0755, true);
