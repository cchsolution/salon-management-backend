import os
import sys
import traceback
from pathlib import Path

# Resolve directory paths
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
backend_dir = root_dir / "backend"

for p in [str(backend_dir), str(root_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_core.settings")

_init_error = None
_django_app = None

try:
    from django.core.wsgi import get_wsgi_application
    _django_app = get_wsgi_application()
except Exception:
    _init_error = traceback.format_exc()


def app(environ, start_response):
    if _init_error:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain; charset=utf-8")])
        return [f"WSGI Startup Error:\n{_init_error}".encode("utf-8")]
    try:
        return _django_app(environ, start_response)
    except Exception:
        err = traceback.format_exc()
        start_response("500 Internal Server Error", [("Content-Type", "text/plain; charset=utf-8")])
        return [f"WSGI Runtime Error:\n{err}".encode("utf-8")]


# Standard WSGI aliases for Vercel Python runtime
application = app

