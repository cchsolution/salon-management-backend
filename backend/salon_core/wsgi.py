import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')

application = get_wsgi_application()
# Expose 'app' alias for Vercel Python serverless compatibility
app = application

application = get_wsgi_application()

from django.conf import settings

print("DEBUG CORS:", {
    "allowed_origins": settings.CORS_ALLOWED_ORIGINS,
    "allow_all": settings.CORS_ALLOW_ALL_ORIGINS,
    "middleware": settings.MIDDLEWARE[:3],
})
