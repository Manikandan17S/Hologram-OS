import os
from pathlib import Path

class FolderNavigator:
    def __init__(self):
        self.current_path = None
    
    def set_path(self, path):
        if os.path.exists(path) and os.path.isdir(path):
            self.current_path = path
            return True
        return False
    
    def list_contents(self):
        """
        Returns a list of dictionaries containing file info:
        {'name', 'path', 'type': 'file'|'folder', 'size'}
        """
        if not self.current_path:
            return []
            
        items = []
        try:
            with os.scandir(self.current_path) as entries:
                for entry in entries:
                    try:
                        info = {
                            'name': entry.name,
                            'path': entry.path,
                            'type': 'folder' if entry.is_dir() else 'file',
                            'size': entry.stat().st_size if entry.is_file() else 0
                        }
                        items.append(info)
                    except PermissionError:
                        continue # Skip unreadable
        except Exception as e:
            print(f"Error listing {self.current_path}: {e}")
            return []
            
        return sorted(items, key=lambda item: (item["type"] != "folder", item["name"].lower()))
    
    def go_up(self):
        if self.current_path:
            normalized = os.path.abspath(self.current_path)
            drive, tail = os.path.splitdrive(normalized)
            if drive and tail in ("\\", "/"):
                self.current_path = None
                return True
            parent = os.path.dirname(normalized.rstrip("\\/"))
            if parent and parent != normalized and os.path.exists(parent):
                self.current_path = parent
                return True
        return False
