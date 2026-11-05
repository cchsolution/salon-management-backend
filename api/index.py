import os
import sys
import json
import traceback
from pathlib import Path

# Resolve directory paths
current_dir = Path(__file__).resolve().parent  # project root/api
root_dir = current_dir.parent  # project root
backend_dir = root_dir / "backend"

possible_paths = [
    str(backend_dir),
    str(root_dir),
    str(current_dir),
    "/var/task/backend",
    "/var/task",
    os.path.join(os.getcwd(), "backend"),
    os.getcwd(),
]

for p in possible_paths:
    if p not in sys.path and (os.path.isdir(p) or p == str(backend_dir) or p.startswith("/var/task")):
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_core.settings")

_django_app = None
_init_error = None


def get_django_app():
    global _django_app, _init_error
    if _django_app is None and _init_error is None:
        try:
            from django.core.wsgi import get_wsgi_application
            _django_app = get_wsgi_application()
        except BaseException:
            _init_error = traceback.format_exc()
    return _django_app, _init_error


def app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    
    # Fast diagnostic health check (does not hit database)
    if path in ("/api/test/", "/test/", "/api/diag/"):
        start_response("200 OK", [("Content-Type", "application/json; charset=utf-8")])
        payload = json.dumps({
            "status": "ok",
            "service": "LuxeSalon API",
            "entrypoint": "api/index.py",
            "python_version": sys.version,
            "sys_path": sys.path[:5]
        })
        return [payload.encode("utf-8")]

    django_app, init_err = get_django_app()
    if init_err:
        start_response("500 Internal Server Error", [("Content-Type", "application/json; charset=utf-8")])
        payload = json.dumps({
            "error": "WSGI Initialization Error on Vercel deployment.",
            "entrypoint": "api/index.py",
            "detail": init_err
        })
        return [payload.encode("utf-8")]

    try:
        return django_app(environ, start_response)
    except BaseException:
        err = traceback.format_exc()
        start_response("500 Internal Server Error", [("Content-Type", "application/json; charset=utf-8")])
        payload = json.dumps({
            "error": "WSGI Runtime Error during request processing.",
            "entrypoint": "api/index.py",
            "detail": err
        })
        return [payload.encode("utf-8")]


# Standard WSGI entrypoints for @vercel/python
application = app

