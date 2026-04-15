#!/bin/bash

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SkuuMate Backend Starting..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for database to be ready
echo "▶ Waiting for database..."
python << END
import sys
import time
import MySQLdb

retries = 30
while retries > 0:
    try:
        MySQLdb.connect(
            host="$DB_HOST",
            port=int("$DB_PORT"),
            user="$DB_USER",
            passwd="$DB_PASSWORD",
            db="$DB_NAME",
        )
        print("✔ Database is ready.")
        break
    except Exception as e:
        retries -= 1
        print(f"  Database not ready yet ({30 - retries}/30). Retrying in 2s...")
        time.sleep(2)
else:
    print("✘ Could not connect to database after 30 attempts. Exiting.")
    sys.exit(1)
END

# Run migrations
echo "▶ Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "▶ Collecting static files..."
python manage.py collectstatic --noinput

# Seed database (skips if already seeded)
echo "▶ Seeding database..."
python manage.py seed

# Start server
echo "▶ Starting Gunicorn..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exec gunicorn skuumate.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -