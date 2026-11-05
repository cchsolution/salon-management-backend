import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
current_dir = Path(__file__).resolve().parent  # salon_core
backend_dir = current_dir.parent  # backend
root_dir = backend_dir.parent

for p in [str(backend_dir), str(current_dir), str(root_dir), '/var/task/backend', '/var/task']:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
app = application
