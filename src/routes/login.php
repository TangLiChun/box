<?php
/**
 * Login Route
 */

$error = null;

// If already logged in, redirect to home
if (Auth::isLoggedIn()) {
    header('Location: /');
    exit;
}

// Handle POST request
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = $_POST['username'] ?? '';
    $password = $_POST['password'] ?? '';
    
    if (Auth::login($username, $password)) {
        header('Location: /');
        exit;
    } else {
        $error = '账号或密码错误。请重试。';
    }
}

// Render login page
?>
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - NexFile</title>
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
<body class="login-page">
    <div class="login-container">
        <div class="login-card glass-panel">
            <div class="login-header">
                <h1 class="gradient-text"><i class="fa-solid fa-layer-group"></i> NexFile</h1>
                <p>文件管理与协作平台</p>
            </div>
            
            <?php if ($error): ?>
            <div class="alert alert-error">
                <i class="fa-solid fa-circle-exclamation"></i>
                <?= htmlspecialchars($error) ?>
            </div>
            <?php endif; ?>
            
            <form method="POST" action="/login" class="login-form">
                <div class="form-group">
                    <label for="username"><i class="fa-solid fa-user"></i> 用户名</label>
                    <input type="text" id="username" name="username" required 
                           placeholder="输入用户名" class="form-control" autofocus>
                </div>
                
                <div class="form-group">
                    <label for="password"><i class="fa-solid fa-lock"></i> 密码</label>
                    <input type="password" id="password" name="password" required 
                           placeholder="输入密码" class="form-control">
                </div>
                
                <button type="submit" class="btn btn-primary btn-block">
                    <i class="fa-solid fa-sign-in-alt"></i> 登录
                </button>
            </form>
        </div>
    </div>
</body>
</html>