<?php
/**
 * File Manager Class
 */
class FileManager {
    
    /**
     * Format file size
     */
    public static function formatSize($size) {
        $units = ['B', 'KB', 'MB', 'GB'];
        $unitIndex = 0;
        
        while ($size >= 1024 && $unitIndex < count($units) - 1) {
            $size /= 1024;
            $unitIndex++;
        }
        
        return round($size, 2) . ' ' . $units[$unitIndex];
    }
    
    /**
     * Get file MIME type
     */
    public static function getMimeType($filename) {
        $finfo = finfo_open(FILEINFO_MIME_TYPE);
        $mime = finfo_file($finfo, $filename);
        finfo_close($finfo);
        return $mime;
    }
    
    /**
     * Generate unique filename
     */
    public static function uniqueName($originalName) {
        $ext = pathinfo($originalName, PATHINFO_EXTENSION);
        $base = pathinfo($originalName, PATHINFO_FILENAME);
        $timestamp = time();
        $random = substr(str_shuffle('abcdefghijklmnopqrstuvwxyz0123456789'), 0, 6);
        return "{$base}_{$timestamp}_{$random}.{$ext}";
    }
    
    /**
     * Get file icon based on extension
     */
    public static function getFileIcon($filename) {
        $ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
        
        $icons = [
            'pdf' => 'fa-file-pdf',
            'doc' => 'fa-file-word',
            'docx' => 'fa-file-word',
            'xls' => 'fa-file-excel',
            'xlsx' => 'fa-file-excel',
            'ppt' => 'fa-file-powerpoint',
            'pptx' => 'fa-file-powerpoint',
            'jpg' => 'fa-file-image',
            'jpeg' => 'fa-file-image',
            'png' => 'fa-file-image',
            'gif' => 'fa-file-image',
            'zip' => 'fa-file-archive',
            'rar' => 'fa-file-archive',
            'txt' => 'fa-file-alt',
            'md' => 'fa-file-alt',
        ];
        
        return $icons[$ext] ?? 'fa-file';
    }
    
    /**
     * Analyze file and return details
     */
    public static function analyzeFile($filepath) {
        if (!file_exists($filepath)) {
            return null;
        }
        
        $info = [
            'name' => basename($filepath),
            'size' => filesize($filepath),
            'size_formatted' => self::formatSize(filesize($filepath)),
            'modified' => filemtime($filepath),
            'mime' => self::getMimeType($filepath),
            'extension' => pathinfo($filepath, PATHINFO_EXTENSION),
        ];
        
        // Add hex header for analysis
        $handle = fopen($filepath, 'rb');
        if ($handle) {
            $bytes = fread($handle, 16);
            fclose($handle);
            $info['hex_header'] = bin2hex($bytes);
        }
        
        return $info;
    }
    
    /**
     * Check if file is editable in ONLYOFFICE
     */
    public static function isEditable($filename) {
        global $ONLYOFFICE_FORMATS;
        $ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
        return isset($ONLYOFFICE_FORMATS['.' . $ext]);
    }
}
