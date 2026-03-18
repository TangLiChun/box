import os
import subprocess


def find_git_repo_root(start_dir):
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def run_update_command(command, cwd, timeout=120):
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            'ok': False,
            'command': ' '.join(command),
            'stdout': '',
            'stderr': 'Command timed out',
            'returncode': None,
        }
    except OSError as exc:
        return {
            'ok': False,
            'command': ' '.join(command),
            'stdout': '',
            'stderr': str(exc),
            'returncode': None,
        }

    return {
        'ok': completed.returncode == 0,
        'command': ' '.join(command),
        # Preserve leading spaces because `git status --porcelain` uses them
        # as part of the status format.
        'stdout': completed.stdout.rstrip(),
        'stderr': completed.stderr.rstrip(),
        'returncode': completed.returncode,
    }


def inspect_incremental_update_status(
    base_dir,
    run_update_command_func,
    find_git_repo_root_func,
    parse_dirty_paths_from_porcelain,
    is_runtime_generated_git_path,
    summarize_update_step,
    run_fetch=True,
):
    repo_root = find_git_repo_root_func(base_dir)
    requirements_path = os.path.join(base_dir, 'requirements.txt')
    status = {
        'supported': False,
        'repo_detected': bool(repo_root),
        'repo_root': repo_root,
        'requirements_path': requirements_path if os.path.isfile(requirements_path) else None,
        'branch': None,
        'current_commit': None,
        'upstream': None,
        'remote_commit': None,
        'ahead': 0,
        'behind': 0,
        'has_updates': False,
        'dirty': False,
        'dirty_files': [],
        'ignored_dirty_files': [],
        'message': '',
    }

    if not repo_root:
        status['message'] = '当前部署目录不是 Git 仓库，无法执行增量更新。'
        return status

    branch_result = run_update_command_func(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo_root)
    commit_result = run_update_command_func(['git', 'rev-parse', '--short', 'HEAD'], repo_root)
    dirty_result = run_update_command_func(['git', 'status', '--porcelain'], repo_root)
    upstream_result = run_update_command_func(
        ['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
        repo_root,
    )

    if branch_result['ok']:
        status['branch'] = branch_result['stdout']
    if commit_result['ok']:
        status['current_commit'] = commit_result['stdout']

    if dirty_result['ok']:
        dirty_paths = parse_dirty_paths_from_porcelain(dirty_result['stdout'])
        status['ignored_dirty_files'] = [path for path in dirty_paths if is_runtime_generated_git_path(path)]
        status['dirty_files'] = [path for path in dirty_paths if not is_runtime_generated_git_path(path)]
        status['dirty'] = bool(status['dirty_files'])
    else:
        status['dirty'] = False

    if not upstream_result['ok'] or not upstream_result['stdout']:
        status['message'] = '检测到 Git 仓库，但当前分支没有配置上游，无法执行增量更新。'
        return status

    status['upstream'] = upstream_result['stdout']
    remote_name = upstream_result['stdout'].split('/')[0]

    if run_fetch:
        fetch_result = run_update_command_func(['git', 'fetch', '--quiet', remote_name], repo_root, timeout=180)
        if not fetch_result['ok']:
            status['message'] = '获取远端更新失败，请检查网络或 Git 访问权限。'
            status['last_error'] = summarize_update_step(fetch_result)
            return status

    divergence_result = run_update_command_func(['git', 'rev-list', '--left-right', '--count', 'HEAD...@{u}'], repo_root)
    remote_commit_result = run_update_command_func(['git', 'rev-parse', '--short', '@{u}'], repo_root)

    if divergence_result['ok'] and divergence_result['stdout']:
        try:
            ahead_str, behind_str = divergence_result['stdout'].split()
            status['ahead'] = int(ahead_str)
            status['behind'] = int(behind_str)
        except (ValueError, TypeError):
            pass

    if remote_commit_result['ok']:
        status['remote_commit'] = remote_commit_result['stdout']

    status['has_updates'] = status['behind'] > 0
    status['supported'] = True

    if status['dirty']:
        status['message'] = '检测到本地未提交改动，已禁用自动升级。请先备份或提交本地修改。'
    elif status['has_updates']:
        status['message'] = f"检测到 {status['behind']} 个远端更新，可以执行增量升级。"
        if status['ignored_dirty_files']:
            status['message'] += '（已自动忽略运行时文件变更）'
    else:
        status['message'] = '当前已经是最新版本。'

    return status


def apply_incremental_update(
    base_dir,
    inspect_incremental_update_status_func,
    run_update_command_func,
    summarize_update_step,
    python_executable,
):
    status = inspect_incremental_update_status_func(run_fetch=True)
    if not status['supported']:
        return False, status, 400

    if status['dirty']:
        return False, status, 409

    if not status['has_updates']:
        status['message'] = '当前已经是最新版本，无需升级。'
        return True, status, 200

    repo_root = status['repo_root']
    steps = []

    pull_result = run_update_command_func(['git', 'pull', '--ff-only'], repo_root, timeout=240)
    steps.append(summarize_update_step(pull_result))
    if not pull_result['ok']:
        status['message'] = '增量升级失败，Git 拉取未完成。'
        status['output'] = '\n\n'.join(steps)
        return False, status, 500

    if status.get('requirements_path'):
        pip_result = run_update_command_func(
            [python_executable, '-m', 'pip', 'install', '-r', status['requirements_path']],
            base_dir,
            timeout=600,
        )
        steps.append(summarize_update_step(pip_result))
        if not pip_result['ok']:
            status['message'] = '代码已更新，但依赖安装失败，请检查输出日志。'
            status['output'] = '\n\n'.join(steps)
            return False, status, 500

    refreshed_status = inspect_incremental_update_status_func(run_fetch=False)
    refreshed_status['supported'] = status['supported']
    refreshed_status['message'] = '升级完成，请重启应用以加载最新代码。'
    refreshed_status['output'] = '\n\n'.join(steps)
    refreshed_status['restart_required'] = True
    return True, refreshed_status, 200
