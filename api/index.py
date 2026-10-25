import os
import sys
from pathlib import Path

# Resolve project paths
# current_dir: /path/to/project_root/api
# root_dir:    /path/to/project_root
# backend_dir: /path/to/project_root/backend
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
backend_dir = root_dir / 'backend'

# Add backend directory to sys.path so salon_core and apps are resolvable
if backend_dir.exists() and str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
elif str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Vercel serverless function expects a WSGI callable named 'app'
app = application
