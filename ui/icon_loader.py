from pathlib import Path

import cv2
import pygame

try:
    from PIL import Image
except Exception:  # pragma: no cover - fallback when PIL is unavailable.
    Image = None


ICON_CACHE = {}
ICON_SCALED_CACHE = {}
THUMBNAIL_CACHE = {}
THUMBNAIL_SCALED_CACHE = {}
_THUMBNAIL_MISSING = object()

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

_ROOT_DIR = Path(__file__).resolve().parents[1]
_ICON_PATHS = {
    "folder": _ROOT_DIR / "assets" / "icons" / "folder.png",
    "file": _ROOT_DIR / "assets" / "icons" / "file.png",
    "video": _ROOT_DIR / "assets" / "icons" / "video.png",
    "image": _ROOT_DIR / "assets" / "icons" / "image.png",
}


def resolve_file_type(path, is_folder):
    if is_folder:
        return "folder"

    suffix = Path(str(path)).suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "image"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"
    return "file"


def _safe_convert_alpha(surface):
    if surface is None:
        return None
    if pygame.display.get_surface() is None:
        return surface
    try:
        return surface.convert_alpha()
    except Exception:
        return surface


def _build_fallback_icon(file_type):
    icon_size = 128
    surface = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
    bg_colors = {
        "folder": (32, 150, 255, 210),
        "image": (80, 205, 145, 210),
        "video": (255, 150, 65, 210),
        "file": (140, 180, 245, 210),
    }
    edge_colors = {
        "folder": (165, 225, 255, 255),
        "image": (200, 250, 210, 255),
        "video": (255, 218, 168, 255),
        "file": (218, 236, 255, 255),
    }
    bg = bg_colors.get(file_type, bg_colors["file"])
    edge = edge_colors.get(file_type, edge_colors["file"])

    body = pygame.Rect(18, 22, 92, 84)
    pygame.draw.rect(surface, bg, body, border_radius=14)
    pygame.draw.rect(surface, edge, body, width=3, border_radius=14)

    if file_type == "folder":
        tab = pygame.Rect(26, 12, 40, 22)
        pygame.draw.rect(surface, bg, tab, border_radius=8)
        pygame.draw.rect(surface, edge, tab, width=3, border_radius=8)
    elif file_type == "image":
        mountain = [(32, 94), (58, 62), (78, 82), (98, 50), (98, 98), (32, 98)]
        pygame.draw.polygon(surface, edge, mountain, width=0)
        pygame.draw.circle(surface, edge, (44, 48), 8)
    elif file_type == "video":
        triangle = [(48, 46), (88, 64), (48, 82)]
        pygame.draw.polygon(surface, edge, triangle)
    else:
        line_color = (240, 248, 255, 220)
        for line_idx in range(4):
            y = 44 + (line_idx * 13)
            pygame.draw.line(surface, line_color, (34, y), (94, y), 3)

    return surface


def _load_base_icon(file_type):
    icon_key = file_type if file_type in _ICON_PATHS else "file"
    cached = ICON_CACHE.get(icon_key)
    if cached is not None:
        return cached

    icon_surface = None
    icon_path = _ICON_PATHS[icon_key]
    if icon_path.exists():
        try:
            icon_surface = _safe_convert_alpha(pygame.image.load(str(icon_path)))
        except Exception:
            icon_surface = None
    if icon_surface is None:
        icon_surface = _build_fallback_icon(icon_key)

    ICON_CACHE[icon_key] = icon_surface
    return icon_surface


def get_icon_surface(file_type, size):
    width = max(12, int(size[0]))
    height = max(12, int(size[1]))
    icon_key = file_type if file_type in _ICON_PATHS else "file"
    cache_key = (icon_key, width, height)
    cached = ICON_SCALED_CACHE.get(cache_key)
    if cached is not None:
        return cached

    base_icon = _load_base_icon(icon_key)
    scaled = pygame.transform.smoothscale(base_icon, (width, height))
    ICON_SCALED_CACHE[cache_key] = scaled
    return scaled


def _pil_resample():
    if Image is None:
        return None
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)


def _load_image_thumbnail(path):
    if Image is None:
        return None
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA")
            image.thumbnail((160, 160), _pil_resample())
            size = image.size
            return pygame.image.fromstring(image.tobytes(), size, "RGBA")
    except Exception:
        return None


def _load_video_thumbnail(path):
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        capture.release()
        return None

    try:
        success, frame = capture.read()
        if not success or frame is None:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return None
        rgb_bytes = frame.tobytes()
        surface = pygame.image.frombuffer(rgb_bytes, (w, h), "RGB")
        return surface.copy()
    except Exception:
        return None
    finally:
        capture.release()


def _load_thumbnail(path, file_type):
    if file_type == "image":
        return _load_image_thumbnail(path)
    if file_type == "video":
        return _load_video_thumbnail(path)
    return None


def get_thumbnail_surface(path, file_type, size):
    if file_type not in ("image", "video"):
        return None

    path_key = str(path)
    base_thumb = THUMBNAIL_CACHE.get(path_key)
    if base_thumb is None:
        loaded = _load_thumbnail(path_key, file_type)
        THUMBNAIL_CACHE[path_key] = loaded if loaded is not None else _THUMBNAIL_MISSING
        base_thumb = THUMBNAIL_CACHE[path_key]

    if base_thumb is _THUMBNAIL_MISSING:
        return None

    width = max(12, int(size[0]))
    height = max(12, int(size[1]))
    cache_key = (path_key, width, height)
    cached = THUMBNAIL_SCALED_CACHE.get(cache_key)
    if cached is not None:
        return cached

    scaled = pygame.transform.smoothscale(base_thumb, (width, height))
    THUMBNAIL_SCALED_CACHE[cache_key] = scaled
    return scaled


def get_visual_surface(path, file_type, size):
    thumbnail = get_thumbnail_surface(path, file_type, size)
    if thumbnail is not None:
        return thumbnail
    return get_icon_surface(file_type, size)
