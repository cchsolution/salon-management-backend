import os
import sys
import json
import traceback
from pathlib import Path

# Resolve directory paths
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
backend_dir = root_dir / "backend"

possible_paths = [
    str(backend_dir),
    str(root_dir),
    str(current_dir),
    "/var/task/backend",
    "/var/task",
]

for p in possible_paths:
    if p not in sys.path and (os.path.isdir(p) or p == str(backend_dir)):
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
        start_response("500 Internal Server Error", [("Content-Type", "application/json; charset=utf-8")])
        payload = json.dumps({
            "error": "WSGI Initialization Error on Vercel deployment.",
            "detail": _init_error
        })
        return [payload.encode("utf-8")]
    try:
        return _django_app(environ, start_response)
    except Exception:
        err = traceback.format_exc()
        start_response("500 Internal Server Error", [("Content-Type", "application/json; charset=utf-8")])
        payload = json.dumps({
            "error": "WSGI Runtime Error during request processing.",
            "detail": err
        })
        return [payload.encode("utf-8")]


# WSGI handler aliases
application = app
handler = app
