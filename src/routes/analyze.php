<?php
/**
 * File Analysis Route
 */

Auth::requireAuth();

$filename = $_GET['filename'] ?? '';

if (empty($filename)) {
    header('Location: /');
    exit;
}

$filename = basename($filename);
$filepath = UPLOAD_FOLDER . '/' . $filename;

if (!file_exists($filepath)) {
    header('Location: /?error=文件不存在');
    exit;
}

$fileInfo = FileManager::analyzeFile($filepath);

?>
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件分析 - <?= htmlspecialchars($filename) ?></title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        let savedTheme = localStorage.getItem('nexfile-theme');
        if (!savedTheme) {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            savedTheme = prefersDark ? 'dark' : 'light';
        }
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</head>
<body>
    <div class="container" style="padding: 2rem;">
        <div class="glass-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
                <h1><i class="fa-solid fa-magnifying-glass-chart"></i> 文件分析</h1>
                <a href="/" class="btn btn-secondary"><i class="fa-solid fa-arrow-left"></i> 返回</a>
            </div>
            
            <div class="analysis-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-top: 2rem;">
                <div class="glass-card" style="padding: 1.5rem;">
                    <h3><i class="fa-solid fa-file"></i> 基本信息</h3>
                    <table style="width: 100%; margin-top: 1rem;">
                        <tr>
                            <td class="muted-note">文件名</td>
                            <td style="text-align: right;"><?= htmlspecialchars($fileInfo['name']) ?></td>
                        </tr>
                        <tr>
                            <td class="muted-note">扩展名</td>
                            <td style="text-align: right;">.<?= htmlspecialchars($fileInfo['extension']) ?></td>
                        </tr>
                        <tr>
                            <td class="muted-note">文件大小</td>
                            <td style="text-align: right;"><?= $fileInfo['size_formatted'] ?></td>
                        </tr>
                        <tr>
                            <td class="muted-note">MIME类型</td>
                            <td style="text-align: right;"><?= htmlspecialchars($fileInfo['mime']) ?></td>
                        </tr>
                    </table>
                </div>
                
                <div class="glass-card" style="padding: 1.5rem;">
                    <h3><i class="fa-solid fa-clock"></i> 时间信息</h3>
                    <table style="width: 100%; margin-top: 1rem;">
                        <tr>
                            <td class="muted-note">修改时间</td>
                            <td style="text-align: right;"><?= date('Y-m-d H:i:s', $fileInfo['modified']) ?></td>
                        </tr>
                        <tr>
                            <td class="muted-note">相对时间</td>
                            <td style="text-align: right;"><?= human_time_diff($fileInfo['modified']) ?></td>
                        </tr>
                    </table>
                </div>
                
                <div class="glass-card" style="padding: 1.5rem; grid-column: 1 / -1;">
                    <h3><i class="fa-solid fa-fingerprint"></i> 文件头 (Hex)</h3>
                    <pre style="margin-top: 1rem; padding: 1rem; background: rgba(0,0,0,0.3); border-radius: 8px; font-family: monospace; overflow-x: auto;"><?= chunk_split(strtoupper($fileInfo['hex_header']), 2, ' ') ?></pre>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Theme Toggle
        const themeToggle = document.getElementById('themeToggle');
        const updateThemeUI = (theme) => {
            document.documentElement.setAttribute('data-theme', theme);
        };
    </script>
</body>
</html>
<?php
// Helper function for human-readable time diff
function human_time_diff($timestamp) {
    $diff = time() - $timestamp;
    
    if ($diff < 60) return '刚刚';
    if ($diff < 3600) return floor($diff / 60) . '分钟前';
    if ($diff < 86400) return floor($diff / 3600) . '小时前';
    if ($diff < 604800) return floor($diff / 86400) . '天前';
    
    return date('Y-m-d', $timestamp);
}
