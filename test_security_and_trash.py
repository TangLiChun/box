import tempfile
import unittest
import re
from pathlib import Path
from unittest import mock

import app as app_module


class DummyUrlopenResponse:
    def __init__(self, body):
        self.status = 200
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FileManagerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.uploads = self.base / 'uploads'
        self.notes = self.base / 'notes'
        self.trash = self.base / 'trash'
        self.database = self.base / 'users.db'
        for folder in (self.uploads, self.notes, self.trash):
            folder.mkdir(parents=True, exist_ok=True)

        self.originals = {
            'DATABASE': app_module.DATABASE,
            'UPLOAD_FOLDER': app_module.UPLOAD_FOLDER,
            'NOTES_FOLDER': app_module.NOTES_FOLDER,
            'TRASH_FOLDER': app_module.TRASH_FOLDER,
            'TESTING': app_module.app.config.get('TESTING', False),
            'UPLOAD_FOLDER_CONFIG': app_module.app.config['UPLOAD_FOLDER'],
            'NOTES_FOLDER_CONFIG': app_module.app.config['NOTES_FOLDER'],
            'TRASH_FOLDER_CONFIG': app_module.app.config['TRASH_FOLDER'],
        }

        app_module.DATABASE = str(self.database)
        app_module.UPLOAD_FOLDER = str(self.uploads)
        app_module.NOTES_FOLDER = str(self.notes)
        app_module.TRASH_FOLDER = str(self.trash)
        app_module.app.config['UPLOAD_FOLDER'] = str(self.uploads)
        app_module.app.config['NOTES_FOLDER'] = str(self.notes)
        app_module.app.config['TRASH_FOLDER'] = str(self.trash)
        app_module.app.config['TESTING'] = True

        self._close_cached_db()
        with app_module.app.app_context():
            app_module.init_db()

        self.client = app_module.app.test_client()
        login_response = self.client.post(
            '/login',
            data={'username': 'admin', 'password': 'password123'},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)

    def tearDown(self):
        self._close_cached_db()
        app_module.DATABASE = self.originals['DATABASE']
        app_module.UPLOAD_FOLDER = self.originals['UPLOAD_FOLDER']
        app_module.NOTES_FOLDER = self.originals['NOTES_FOLDER']
        app_module.TRASH_FOLDER = self.originals['TRASH_FOLDER']
        app_module.app.config['UPLOAD_FOLDER'] = self.originals['UPLOAD_FOLDER_CONFIG']
        app_module.app.config['NOTES_FOLDER'] = self.originals['NOTES_FOLDER_CONFIG']
        app_module.app.config['TRASH_FOLDER'] = self.originals['TRASH_FOLDER_CONFIG']
        app_module.app.config['TESTING'] = self.originals['TESTING']
        self.tempdir.cleanup()

    def _close_cached_db(self):
        with app_module.app.app_context():
            db = getattr(app_module.g, '_database', None)
            if db is not None:
                db.close()
                app_module.g._database = None

    def test_share_create_rejects_traversal_and_public_note_share_stays_confined(self):
        (self.notes / 'safe.md').write_text('# safe', encoding='utf-8')
        outside = self.base / 'outside.md'
        outside.write_text('outside secret', encoding='utf-8')

        response = self.client.post('/share/create', json={'type': 'note', 'filename': '../outside.md'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

        valid_response = self.client.post('/share/create', json={'type': 'note', 'filename': 'safe.md'})
        self.assertEqual(valid_response.status_code, 200)
        self.assertTrue(valid_response.get_json()['success'])

        with app_module.app.app_context():
            db = app_module.get_db()
            db.execute(
                'INSERT INTO shares (id, type, target_filename) VALUES (?, ?, ?)',
                ('badshare', 'note', '../outside.md')
            )
            db.commit()

        public_response = self.client.get('/s/n/badshare')
        self.assertEqual(public_response.status_code, 404)
        self.assertNotIn('outside secret', public_response.get_data(as_text=True))

    def test_share_revoke_rejects_non_json_with_json_error(self):
        response = self.client.post('/share/revoke', data='x', content_type='text/plain')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {'success': False, 'message': '请求必须为 JSON'}
        )

    def test_onlyoffice_callback_requires_token_and_existing_target_file(self):
        target = self.uploads / 'report.txt'
        target.write_text('old content', encoding='utf-8')

        forbidden = self.client.post(
            '/callback/report.txt',
            json={'status': 2, 'url': 'https://example.com/file'}
        )
        self.assertEqual(forbidden.status_code, 403)

        with app_module.app.app_context():
            token = app_module.generate_onlyoffice_callback_token('report.txt')
        missing_status = self.client.post(f'/callback/report.txt?token={token}', json={})
        self.assertEqual(missing_status.status_code, 400)

        with app_module.app.app_context():
            new_file_token = app_module.generate_onlyoffice_callback_token('new.txt')
        missing_target = self.client.post(
            f'/callback/new.txt?token={new_file_token}',
            json={'status': 2, 'url': 'https://example.com/file'}
        )
        self.assertEqual(missing_target.status_code, 404)
        self.assertFalse((self.uploads / 'new.txt').exists())

        with mock.patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('93.184.216.34', 0))]):
            with mock.patch('urllib.request.urlopen', return_value=DummyUrlopenResponse(b'updated')):
                success = self.client.post(
                    f'/callback/report.txt?token={token}',
                    json={'status': 2, 'url': 'https://example.com/file'}
                )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.get_json(), {'error': 0})
        self.assertEqual(target.read_bytes(), b'updated')

    def test_admin_settings_store_onlyoffice_jwt_secret_and_editor_emits_signed_config(self):
        response = self.client.post(
            '/admin/settings',
            data={
                'onlyoffice_url': 'https://docs.example.com',
                'onlyoffice_jwt_secret': 'shared-secret'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'success': True, 'message': '设置已更新'})

        with app_module.app.app_context():
            self.assertEqual(app_module.get_setting('onlyoffice_url'), 'https://docs.example.com')
            self.assertEqual(app_module.get_setting('onlyoffice_jwt_secret'), 'shared-secret')

        target = self.uploads / 'report.txt'
        target.write_text('body', encoding='utf-8')

        editor_response = self.client.get('/editor/report.txt')
        self.assertEqual(editor_response.status_code, 200)
        body = editor_response.get_data(as_text=True)
        self.assertIn('"token":', body)
        self.assertNotIn('shared-secret', body)

        match = re.search(r'"token":\s*"([^"]+)"', body)
        self.assertIsNotNone(match)
        payload = app_module.decode_onlyoffice_jwt(match.group(1), 'shared-secret')
        self.assertIsNotNone(payload)
        self.assertEqual(payload['document']['title'], 'report.txt')

    def test_admin_settings_rejects_invalid_onlyoffice_urls_with_4xx(self):
        invalid_url_response = self.client.post(
            '/admin/settings',
            data={
                'onlyoffice_url': 'docs.example.com',
                'onlyoffice_jwt_secret': 'shared-secret',
                'onlyoffice_callback_base': 'https://callback.example.com',
            }
        )
        self.assertGreaterEqual(invalid_url_response.status_code, 400)
        self.assertLess(invalid_url_response.status_code, 500)
        self.assertEqual(
            invalid_url_response.get_json(),
            {'success': False, 'message': '请输入有效的 URL (以 http:// 或 https:// 开头)'}
        )

        invalid_callback_response = self.client.post(
            '/admin/settings',
            data={
                'onlyoffice_url': 'https://docs.example.com',
                'onlyoffice_jwt_secret': 'shared-secret',
                'onlyoffice_callback_base': 'callback.example.com',
            }
        )
        self.assertGreaterEqual(invalid_callback_response.status_code, 400)
        self.assertLess(invalid_callback_response.status_code, 500)
        self.assertEqual(
            invalid_callback_response.get_json(),
            {'success': False, 'message': '回调地址必须以 http:// 或 https:// 开头'}
        )


    def test_download_requires_auth_unless_onlyoffice_download_token_is_provided(self):
        target = self.uploads / 'report.txt'
        target.write_text('download body', encoding='utf-8')

        anon_client = app_module.app.test_client()

        redirect_resp = anon_client.get('/download/report.txt')
        self.assertEqual(redirect_resp.status_code, 302)
        self.assertIn('/login', redirect_resp.headers.get('Location', ''))

        with app_module.app.app_context():
            token = app_module.generate_onlyoffice_download_token('report.txt')

        ok_resp = anon_client.get(f'/download/report.txt?token={token}')
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.data, b'download body')

    def test_editor_uses_ascii_onlyoffice_doc_key_and_signed_download_url(self):
        with app_module.app.app_context():
            app_module.set_setting('onlyoffice_url', 'https://docs.example.com/')

        filename = '男m测评报告.docx'
        target = self.uploads / filename
        target.write_text('body', encoding='utf-8')

        editor_response = self.client.get(f'/editor/{filename}')
        self.assertEqual(editor_response.status_code, 200)
        body = editor_response.get_data(as_text=True)

        self.assertRegex(body, r'"key":\s*"doc_[a-f0-9]{32}"')
        self.assertIn('/download/%E7%94%B7m%E6%B5%8B%E8%AF%84%E6%8A%A5%E5%91%8A.docx?token=', body)
    def test_onlyoffice_callback_requires_valid_jwt_when_secret_is_configured(self):
        target = self.uploads / 'report.txt'
        target.write_text('old content', encoding='utf-8')

        with app_module.app.app_context():
            app_module.set_setting('onlyoffice_jwt_secret', 'shared-secret')
            callback_token = app_module.generate_onlyoffice_callback_token('report.txt')
            body_token = app_module.generate_onlyoffice_jwt(
                {'status': 2, 'url': 'https://example.com/file'},
                'shared-secret'
            )

        missing_jwt = self.client.post(
            f'/callback/report.txt?token={callback_token}',
            json={'status': 2, 'url': 'https://example.com/file'}
        )
        self.assertEqual(missing_jwt.status_code, 403)
        self.assertEqual(
            missing_jwt.get_json(),
            {'error': 1, 'message': 'Invalid ONLYOFFICE token'}
        )

        with mock.patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('93.184.216.34', 0))]):
            with mock.patch('urllib.request.urlopen', return_value=DummyUrlopenResponse(b'jwt-updated')):
                success = self.client.post(
                    f'/callback/report.txt?token={callback_token}',
                    json={'status': 2, 'url': 'https://example.com/file', 'token': body_token}
                )

        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.get_json(), {'error': 0})
        self.assertEqual(target.read_bytes(), b'jwt-updated')

    def test_admin_update_status_reports_unsupported_when_git_repo_is_missing(self):
        with mock.patch.object(app_module, 'find_git_repo_root', return_value=None):
            response = self.client.get('/admin/update/status')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertFalse(payload['supported'])
        self.assertIn('Git 仓库', payload['message'])

    def test_admin_apply_update_returns_helper_result(self):
        mocked_result = {
            'supported': True,
            'repo_detected': True,
            'repo_root': str(self.base),
            'requirements_path': str(self.base / 'requirements.txt'),
            'branch': 'main',
            'current_commit': 'abc1234',
            'upstream': 'origin/main',
            'remote_commit': 'def5678',
            'ahead': 0,
            'behind': 0,
            'has_updates': False,
            'dirty': False,
            'message': '升级完成，请重启应用以加载最新代码。',
            'output': '$ git pull --ff-only\nAlready up to date.',
            'restart_required': True
        }

        with mock.patch.object(app_module, 'apply_incremental_update', return_value=(True, mocked_result, 200)):
            response = self.client.post('/admin/update/apply')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['branch'], 'main')
        self.assertTrue(payload['restart_required'])


    def test_update_status_ignores_runtime_dirty_files(self):
        mocked_results = [
            {'ok': True, 'command': 'git rev-parse --abbrev-ref HEAD', 'stdout': 'main', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --short HEAD', 'stdout': 'abc1234', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git status --porcelain', 'stdout': ' M users.db\n M __pycache__/app.cpython-314.pyc', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --abbrev-ref --symbolic-full-name @{u}', 'stdout': 'origin/main', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-list --left-right --count HEAD...@{u}', 'stdout': '0 2', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --short @{u}', 'stdout': 'def5678', 'stderr': '', 'returncode': 0},
        ]

        with mock.patch.object(app_module, 'find_git_repo_root', return_value=str(self.base)):
            with mock.patch.object(app_module, 'run_update_command', side_effect=mocked_results):
                status = app_module.inspect_incremental_update_status(run_fetch=False)

        self.assertTrue(status['supported'])
        self.assertFalse(status['dirty'])
        self.assertEqual(status['dirty_files'], [])
        self.assertIn('users.db', status['ignored_dirty_files'])
        self.assertTrue(status['has_updates'])

    def test_update_status_blocks_non_runtime_dirty_files(self):
        mocked_results = [
            {'ok': True, 'command': 'git rev-parse --abbrev-ref HEAD', 'stdout': 'main', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --short HEAD', 'stdout': 'abc1234', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git status --porcelain', 'stdout': ' M app.py\n M users.db', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --abbrev-ref --symbolic-full-name @{u}', 'stdout': 'origin/main', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-list --left-right --count HEAD...@{u}', 'stdout': '0 1', 'stderr': '', 'returncode': 0},
            {'ok': True, 'command': 'git rev-parse --short @{u}', 'stdout': 'def5678', 'stderr': '', 'returncode': 0},
        ]

        with mock.patch.object(app_module, 'find_git_repo_root', return_value=str(self.base)):
            with mock.patch.object(app_module, 'run_update_command', side_effect=mocked_results):
                status = app_module.inspect_incremental_update_status(run_fetch=False)

        self.assertTrue(status['dirty'])
        self.assertIn('app.py', status['dirty_files'])
        self.assertIn('users.db', status['ignored_dirty_files'])

    def test_preview_rejects_non_json_with_json_error(self):
        response = self.client.post('/api/preview', data='x', content_type='text/plain')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {'success': False, 'message': '请求必须为 JSON'}
        )

    def test_markdown_upload_restores_to_uploads_instead_of_notes(self):
        upload = self.uploads / 'readme.md'
        upload.write_text('markdown upload', encoding='utf-8')

        delete_response = self.client.post('/delete/readme.md')
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(upload.exists())
        self.assertTrue((self.trash / 'readme.md').exists())

        restore_response = self.client.post('/trash/restore/readme.md')
        self.assertEqual(restore_response.status_code, 200)
        self.assertTrue((self.uploads / 'readme.md').exists())
        self.assertFalse((self.notes / 'readme.md').exists())

        with app_module.app.app_context():
            db = app_module.get_db()
            metadata = db.execute('SELECT * FROM trash_items WHERE trash_name = ?', ('readme.md',)).fetchone()
            self.assertIsNone(metadata)

    def test_legacy_markdown_trash_requires_explicit_restore_type(self):
        legacy = self.trash / 'legacy.md'
        legacy.write_text('legacy', encoding='utf-8')

        ambiguous_restore = self.client.post('/trash/restore/legacy.md')
        self.assertEqual(ambiguous_restore.status_code, 409)
        self.assertEqual(
            ambiguous_restore.get_json(),
            {
                'success': False,
                'message': '旧回收站中的 Markdown 条目缺少来源信息，请选择恢复为文件或笔记'
            }
        )

        explicit_restore = self.client.post('/trash/restore/legacy.md', json={'item_type': 'file'})
        self.assertEqual(explicit_restore.status_code, 200)
        self.assertTrue((self.uploads / 'legacy.md').exists())
        self.assertFalse((self.notes / 'legacy.md').exists())

    def test_batch_delete_removes_share_and_permanent_delete_endpoint_works(self):
        upload = self.uploads / 'batch.txt'
        upload.write_text('payload', encoding='utf-8')

        share_response = self.client.post('/share/create', json={'type': 'file', 'filename': 'batch.txt'})
        self.assertEqual(share_response.status_code, 200)

        delete_response = self.client.post('/api/batch-delete', json={'filenames': ['batch.txt']})
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue((self.trash / 'batch.txt').exists())

        with app_module.app.app_context():
            db = app_module.get_db()
            share = db.execute(
                'SELECT id FROM shares WHERE type = ? AND target_filename = ?',
                ('file', 'batch.txt')
            ).fetchone()
            metadata = db.execute(
                'SELECT item_type FROM trash_items WHERE trash_name = ?',
                ('batch.txt',)
            ).fetchone()
            self.assertIsNone(share)
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata['item_type'], 'file')

        permanent_delete = self.client.post('/trash/delete/batch.txt')
        self.assertEqual(permanent_delete.status_code, 200)
        self.assertFalse((self.trash / 'batch.txt').exists())

        with app_module.app.app_context():
            db = app_module.get_db()
            metadata = db.execute(
                'SELECT item_type FROM trash_items WHERE trash_name = ?',
                ('batch.txt',)
            ).fetchone()
            self.assertIsNone(metadata)


if __name__ == '__main__':
    unittest.main()
