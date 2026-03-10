import os
import platform
import subprocess
from pathlib import Path

try:
    from send2trash import send2trash
except ImportError:  # pragma: no cover - handled at runtime if dependency missing
    send2trash = None

from config import IGNORED_FOLDERS, SAFE_DELETE_MODE


def open_file(path):
    """
    Opens a file or folder using the default OS application.
    """
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        return True, "Opened successfully"
    except Exception as exc:
        return False, str(exc)


def _is_root_path(path):
    absolute = os.path.abspath(path)
    drive, tail = os.path.splitdrive(absolute)
    if drive and tail in ("\\", "/"):
        return True
    return absolute in (os.path.abspath(os.sep), "/")


def _is_protected_path(path):
    path_obj = Path(path)
    parts_lower = {part.lower() for part in path_obj.parts}
    ignored_lower = {name.lower() for name in IGNORED_FOLDERS}
    return any(blocked in parts_lower for blocked in ignored_lower)


def delete_item(path, mode=SAFE_DELETE_MODE):
    """
    Deletes an item in safe mode only.
    mode:
      - recycle_bin: send item to OS recycle bin/trash.
    """
    if mode != "recycle_bin":
        return False, "Unsafe delete mode blocked"

    if not path or not os.path.exists(path):
        return False, "Path not found"

    absolute = os.path.abspath(path)
    if _is_root_path(absolute):
        return False, "Cannot delete drive root"

    if _is_protected_path(absolute):
        return False, "Protected Path"

    try:
        if send2trash is None:
            return False, "send2trash is not installed"
        send2trash(absolute)
        return True, "Moved to Recycle Bin"
    except Exception as exc:
        return False, str(exc)
