import os
from .core import resolve_runtime_path


def get_default_config(base_dir):
    """Return default application configuration."""
    instance_dir = os.path.join(base_dir, 'instance')
    return {
        'UPLOAD_FOLDER': resolve_runtime_path(base_dir, instance_dir, 'uploads', prefer_legacy=True),
        'NOTES_FOLDER': resolve_runtime_path(base_dir, instance_dir, 'notes', prefer_legacy=True),
        'TRASH_FOLDER': resolve_runtime_path(base_dir, instance_dir, 'trash', prefer_legacy=True),
        'DATABASE': resolve_runtime_path(base_dir, instance_dir, 'users.db', prefer_legacy=True),
        'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
    }


# ONLYOFFICE supported formats and their document types
ONLYOFFICE_FORMATS = {
    # Word
    '.docx': 'word', '.doc': 'word', '.odt': 'word', '.rtf': 'word', '.txt': 'word',
    # Cell
    '.xlsx': 'cell', '.xls': 'cell', '.ods': 'cell', '.csv': 'cell',
    # Slide
    '.pptx': 'slide', '.ppt': 'slide', '.odp': 'slide',
    # PDF (usually read-only in ONLYOFFICE Document Server)
    '.pdf': 'pdf'
}
