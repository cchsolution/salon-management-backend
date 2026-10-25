import os
import sys
from pathlib import Path

# Resolve project paths when root directory is set to 'backend'
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Vercel serverless function expects a WSGI callable named 'app'
app = application
