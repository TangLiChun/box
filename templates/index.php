<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件管理 - NexFile</title>
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
    <button id="mobileNavToggle" class="mobile-nav-toggle" aria-label="切换导航">
        <i class="fa-solid fa-bars"></i>
    </button>
    <div id="sidebarBackdrop" class="sidebar-backdrop"></div>
    
    <div class="app-layout">
        <aside class="sidebar" id="appSidebar">
            <div class="sidebar-logo">
                <h1 class="gradient-text"><i class="fa-solid fa-layer-group"></i> NexFile</h1>
            </div>

            <nav class="sidebar-nav">
                <a href="/" class="side-link active"><i class="fa-solid fa-folder-open"></i> <span>文件管理</span></a>
                <a href="/notes" class="side-link"><i class="fa-solid fa-book"></i> <span>笔记管理</span></a>
                <a href="/trash" class="side-link"><i class="fa-solid fa-trash-can"></i> <span>回收站</span></a>
                <a href="/game" class="side-link"><i class="fa-solid fa-dharmachakra"></i> <span>幸运转盘</span></a>
                <a href="/admin" class="side-link"><i class="fa-solid fa-users-gear"></i> <span>后台管理</span></a>
            </nav>

            <div class="sidebar-footer">
                <button id="themeToggle" class="theme-toggle-btn" aria-label="切换深色/浅色主题">
                    <i class="fa-solid fa-moon"></i> <span>深色模式</span>
                </button>
                <div class="muted-note sidebar-user-chip">
                    <i class="fa-solid fa-circle-user"></i> <span><?= htmlspecialchars(Auth::getUsername()) ?></span>
                </div>
                <a href="/logout" class="side-link side-link-danger"><i class="fa-solid fa-sign-out-alt"></i> <span>退出登录</span></a>
            </div>
        </aside>

        <main class="main-content">
            <div class="container">
                <div class="utility-pill btn-auto top-utility-chip">
                    <i class="fa-solid fa-sparkles"></i>
                    <span>更清晰的层次，更顺手的操作流</span>
                </div>
                
                <?php if ($announcement): ?>
                <div class="announcement-banner" id="announcementBanner">
                    <i class="fa-solid fa-bullhorn"></i>
                    <div class="announcement-content" id="announcementContent"><?= htmlspecialchars($announcement) ?></div>
                </div>
                <?php endif; ?>

                <?php if (isset($success)): ?>
                <div class="alert alert-success">
                    <i class="fa-solid fa-check-circle"></i> <?= htmlspecialchars($success) ?>
                </div>
                <?php endif; ?>
                
                <?php if (isset($error)): ?>
                <div class="alert alert-error">
                    <i class="fa-solid fa-circle-exclamation"></i> <?= htmlspecialchars($error) ?>
                </div>
                <?php endif; ?>

                <div class="page-hero-top">
                    <div class="hero-text">
                        <h2><i class="fa-solid fa-folder-open"></i> 文件管理</h2>
                        <p class="muted-note">上传、管理和分享您的文件</p>
                    </div>
                    <div class="hero-actions">
                        <form method="POST" action="/" enctype="multipart/form-data" class="upload-form">
                            <label for="file-upload" class="btn btn-primary">
                                <i class="fa-solid fa-cloud-arrow-up"></i> 上传文件
                            </label>
                            <input type="file" id="file-upload" name="file" style="display: none;" onchange="this.form.submit()">
                        </form>
                    </div>
                </div>

                <div class="toolbar-card">
                    <div class="toolbar-cluster">
                        <span class="muted-note"><i class="fa-solid fa-file"></i> 共 <?= count($files) ?> 个文件</span>
                    </div>
                </div>

                <div class="file-grid">
                    <?php foreach ($files as $file): ?>
                    <div class="file-card">
                        <div class="file-card-preview">
                            <i class="fa-solid <?= FileManager::getFileIcon($file['name']) ?>"></i>
                        </div>
                        <div class="file-card-info">
                            <h4 title="<?= htmlspecialchars($file['name']) ?>"><?= htmlspecialchars($file['name']) ?></h4>
                            <span class="file-meta"><?= FileManager::formatSize($file['size']) ?> • <?= date('Y-m-d H:i', $file['modified']) ?></span>
                        </div>
                        <div class="file-card-actions">
                            <a href="/download/<?= urlencode($file['name']) ?>" class="btn-icon" title="下载">
                                <i class="fa-solid fa-download"></i>
                            </a>
                            <?php if (FileManager::isEditable($file['name'])): ?>
                            <a href="/editor/<?= urlencode($file['name']) ?>" class="btn-icon" title="编辑">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </a>
                            <?php endif; ?>
                            <a href="/analyze/<?= urlencode($file['name']) ?>" class="btn-icon" title="分析">
                                <i class="fa-solid fa-magnifying-glass-chart"></i>
                            </a>
                            <form method="POST" action="/delete/<?= urlencode($file['name']) ?>" style="display: inline;" onsubmit="return confirm('确定要删除此文件吗？');">
                                <button type="submit" class="btn-icon btn-icon-danger" title="删除">
                                    <i class="fa-solid fa-trash"></i>
                                </button>
                            </form>
                        </div>
                    </div>
                    <?php endforeach; ?>
                    
                    <?php if (empty($files)): ?>
                    <div class="empty-state">
                        <i class="fa-regular fa-folder-open"></i>
                        <p>暂无文件</p>
                        <span class="muted-note">点击上方"上传文件"按钮添加文件</span>
                    </div>
                    <?php endif; ?>
                </div>
            </div>
        </main>
    </div>

    <div id="toast-container" class="toast-container"></div>

    <script>
        // Theme Toggle
        const themeToggle = document.getElementById('themeToggle');
        const updateThemeUI = (theme) => {
            const isDark = theme === 'dark';
            const icon = themeToggle.querySelector('i');
            const span = themeToggle.querySelector('span');
            if (icon) icon.className = isDark ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
            if (span) span.innerText = isDark ? '深色模式' : '浅色模式';
            document.documentElement.setAttribute('data-theme', theme);
        };

        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('nexfile-theme', newTheme);
            updateThemeUI(newTheme);
        });

        // Initial UI
        const savedTheme = localStorage.getItem('nexfile-theme') || 'dark';
        updateThemeUI(savedTheme);

        // Mobile Navigation
        const mobileNavToggle = document.getElementById('mobileNavToggle');
        const sidebarBackdrop = document.getElementById('sidebarBackdrop');
        
        function setSidebarOpen(open) {
            document.body.classList.toggle('sidebar-open', open);
            if (mobileNavToggle) {
                const icon = mobileNavToggle.querySelector('i');
                if (icon) icon.className = open ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
            }
        }

        if (mobileNavToggle && sidebarBackdrop) {
            mobileNavToggle.addEventListener('click', () => {
                setSidebarOpen(!document.body.classList.contains('sidebar-open'));
            });
            sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));
            document.querySelectorAll('.sidebar a').forEach((link) => {
                link.addEventListener('click', () => setSidebarOpen(false));
            });
        }
    </script>
</body>
</html>