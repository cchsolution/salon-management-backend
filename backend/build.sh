#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Building Django backend..."
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files into STATIC_ROOT
python manage.py collectstatic --no-input --clear
