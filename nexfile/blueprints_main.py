from flask import Blueprint, current_app


main_bp = Blueprint('main', __name__)

_deps = {}


def configure_main_blueprint(**deps):
    _deps.clear()
    _deps.update(deps)


def dep(name):
    return _deps[name]


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    return dep('handle_login')(dep('is_authenticated'), dep('get_db'))


@main_bp.route('/logout')
def logout():
    return dep('handle_logout')()


@main_bp.route('/', methods=['GET', 'POST'])
def index():
    return dep('handle_index')(
        dep('is_authenticated'),
        dep('secure_filename'),
        dep('get_db'),
        dep('format_size'),
        dep('get_setting'),
        current_app.logger,
        current_app.config['UPLOAD_FOLDER'],
        tuple(dep('onlyoffice_formats').keys()),
    )


@main_bp.route('/download/<filename>')
def download_file(filename):
    return dep('handle_download_file')(
        filename,
        dep('resolve_item_path'),
        dep('is_authenticated'),
        dep('is_valid_onlyoffice_download_token'),
        current_app.config['UPLOAD_FOLDER'],
    )


@main_bp.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    return dep('handle_delete_file')(filename, dep('is_authenticated'), dep('move_item_to_trash'))


@main_bp.route('/analyze/<filename>')
def analyze_file(filename):
    return dep('handle_analyze_file')(filename, dep('is_authenticated'), dep('resolve_item_path'))


@main_bp.route('/game')
def game():
    return dep('handle_game')(dep('is_authenticated'), dep('get_setting'))


@main_bp.route('/public/game')
def public_game():
    return dep('handle_public_game')(dep('get_setting'))


@main_bp.route('/game/share', methods=['POST'])
def create_game_share():
    return dep('handle_create_game_share')(dep('is_authenticated'), dep('get_db'), dep('generate_short_id'))


@main_bp.route('/g/<share_id>')
def public_share_game(share_id):
    return dep('handle_public_share_game')(share_id, dep('get_db'), dep('get_setting'))


@main_bp.route('/notes')
def notes():
    return dep('handle_notes_index')(
        dep('is_authenticated'),
        dep('get_db'),
        dep('get_setting'),
        current_app.logger,
        current_app.config['NOTES_FOLDER'],
    )


@main_bp.route('/notes/create', methods=['GET', 'POST'])
def create_note():
    return dep('handle_create_note')(
        dep('is_authenticated'),
        dep('normalize_note_input'),
        dep('secure_filename'),
        dep('get_setting'),
        current_app.config['NOTES_FOLDER'],
    )


@main_bp.route('/notes/edit/<filename>', methods=['GET', 'POST'])
def edit_note(filename):
    return dep('handle_edit_note')(
        filename,
        dep('is_authenticated'),
        dep('resolve_item_path'),
        dep('normalize_note_input'),
        dep('secure_filename'),
        dep('get_db'),
        dep('get_setting'),
        current_app.logger,
        current_app.config['NOTES_FOLDER'],
    )


@main_bp.route('/notes/view/<filename>')
def view_note(filename):
    return dep('handle_view_note')(filename, dep('is_authenticated'), dep('resolve_item_path'), dep('get_setting'))


@main_bp.route('/notes/delete/<filename>', methods=['POST'])
def delete_note(filename):
    return dep('handle_delete_note')(filename, dep('is_authenticated'), dep('move_item_to_trash'))


@main_bp.route('/admin')
def admin():
    return dep('admin_required')(lambda: dep('render_admin_dashboard')(dep('get_db'), dep('get_setting'), dep('is_admin_password_change_required')))()


@main_bp.route('/admin/settings', methods=['POST'])
def update_settings():
    return dep('admin_required')(lambda: dep('handle_update_settings')(dep('set_setting')))()


@main_bp.route('/admin/onlyoffice/test')
def test_onlyoffice_connection():
    return dep('admin_required')(lambda: dep('handle_test_onlyoffice_connection')(dep('get_setting')))()


@main_bp.route('/admin/update/status')
def admin_update_status():
    return dep('admin_required')(lambda: dep('handle_update_status')(dep('inspect_incremental_update_status')))()


@main_bp.route('/admin/update/apply', methods=['POST'])
def admin_apply_update():
    return dep('admin_required')(lambda: dep('handle_apply_update')(dep('apply_incremental_update')))()


@main_bp.route('/admin/users/add', methods=['POST'])
def add_user():
    return dep('admin_required')(lambda: dep('handle_add_user')(dep('get_db')))()


@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    return dep('admin_required')(lambda: dep('handle_delete_user')(user_id, dep('get_db')))()


@main_bp.route('/admin/password', methods=['POST'])
def change_password():
    return dep('handle_change_password')(dep('is_authenticated'), dep('get_db'))


@main_bp.route('/share/create', methods=['POST'])
def create_share():
    return dep('handle_create_share')(dep('is_authenticated'), dep('resolve_item_path'), dep('get_item_label'), dep('get_db'), dep('generate_short_id'))


@main_bp.route('/share/revoke', methods=['POST'])
def revoke_share():
    return dep('handle_revoke_share')(dep('is_authenticated'), dep('get_db'))


@main_bp.route('/s/f/<share_id>')
def public_share_file(share_id):
    return dep('handle_public_share_file')(share_id, dep('get_db'), dep('resolve_item_path'))


@main_bp.route('/s/n/<share_id>')
def public_share_note(share_id):
    return dep('handle_public_share_note')(share_id, dep('get_db'), dep('resolve_item_path'), dep('get_setting'))


@main_bp.route('/api/batch-delete', methods=['POST'])
def batch_delete():
    return dep('handle_batch_delete')(dep('is_authenticated'), dep('move_item_to_trash'))


@main_bp.route('/trash')
def view_trash():
    return dep('handle_view_trash')(
        dep('is_authenticated'),
        dep('get_db'),
        dep('format_size'),
        dep('get_setting'),
        current_app.logger,
        current_app.config['TRASH_FOLDER'],
    )


@main_bp.route('/trash/restore/<filename>', methods=['POST'])
def restore_item(filename):
    return dep('handle_restore_item')(filename, dep('is_authenticated'), dep('restore_item_from_trash'))


@main_bp.route('/trash/delete/<filename>', methods=['POST'])
def permanent_delete_item(filename):
    return dep('handle_permanent_delete_item')(filename, dep('is_authenticated'), dep('permanently_delete_trash_item'))


@main_bp.route('/trash/clear', methods=['POST'])
def clear_trash():
    return dep('handle_clear_trash')(dep('is_authenticated'), dep('get_db'), current_app.config['TRASH_FOLDER'])


@main_bp.route('/editor/<filename>')
def onlyoffice_editor(filename):
    return dep('handle_onlyoffice_editor')(
        filename,
        dep('is_authenticated'),
        dep('get_setting'),
        dep('resolve_item_path'),
        dep('onlyoffice_formats'),
        dep('generate_onlyoffice_download_token'),
        dep('generate_onlyoffice_callback_token'),
        dep('get_onlyoffice_jwt_secret'),
        dep('generate_onlyoffice_jwt'),
    )


@main_bp.route('/callback/<filename>', methods=['POST'])
def onlyoffice_callback(filename):
    return dep('handle_onlyoffice_callback')(
        filename,
        dep('normalize_managed_filename'),
        dep('is_valid_onlyoffice_callback_token'),
        dep('get_onlyoffice_jwt_secret'),
        dep('extract_onlyoffice_jwt_token'),
        dep('decode_onlyoffice_jwt'),
        dep('resolve_item_path'),
        dep('get_setting'),
        current_app.logger,
    )


@main_bp.route('/api/preview', methods=['POST'])
def render_preview():
    return dep('handle_render_preview')(dep('is_authenticated'))
