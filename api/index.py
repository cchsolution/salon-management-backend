import os
import sys
from pathlib import Path

# backend/ directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Make Django project modules available
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_core.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Vercel WSGI entry point
app = application