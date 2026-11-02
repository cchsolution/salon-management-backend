import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path whether Vercel runs from repo root or backend/
current_dir = Path(__file__).resolve().parent  # salon_core
backend_dir = current_dir.parent  # backend
root_dir = backend_dir.parent  # repo root

for p in [str(backend_dir), str(current_dir), str(root_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Expose 'app' alias for Vercel Python serverless WSGI compatibility
app = application
