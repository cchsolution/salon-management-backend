#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Collecting static files for Vercel deployment..."
python3 manage.py collectstatic --noinput --clear
