import os
import sys
from pathlib import Path

# Resolve directory paths
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
backend_dir = root_dir / "backend"

# Ensure backend/ (where salon_core and apps reside) is available on sys.path
if backend_dir.exists() and str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_core.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Vercel WSGI entry point
app = application