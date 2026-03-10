import os
import string
import platform
from config import SYSTEM_DRIVES_ONLY

def get_drives():
    """
    Returns a list of available drive letters (e.g., ['C:', 'D:']).
    """
    drives = []
    if platform.system() == "Windows":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1
    else:
        # For Linux/Mac placeholder (project specifies Windows in OS info but logic fits generic)
        drives.append("/")
    
    return drives
