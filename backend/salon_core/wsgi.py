import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

application = get_wsgi_application()
# Expose 'app' alias for Vercel Python serverless compatibility
app = application
