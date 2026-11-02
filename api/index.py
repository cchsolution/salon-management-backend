import os
import sys
from pathlib import Path

# Resolve directory paths
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
backend_dir = root_dir / "backend"

for p in [str(backend_dir), str(root_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_core.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
app = application

