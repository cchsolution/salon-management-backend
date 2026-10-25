#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Collecting static files for Vercel deployment..."
if [ -d "backend" ]; then
    python3 backend/manage.py collectstatic --noinput --clear
else
    python3 manage.py collectstatic --noinput --clear
fi
