#!/usr/bin/env bash
# Exit on error
set -o errexit

# Upgrade pip and install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files into STATIC_ROOT
python manage.py collectstatic --no-input

# Apply database migrations
python manage.py migrate

# Seed demo accounts and salon environment idempotently on deployment
python manage.py seed_demo_data

