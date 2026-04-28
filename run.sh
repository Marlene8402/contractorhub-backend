#!/bin/bash

echo "🚀 Starting ContractorHub Backend..."
echo ""

# Get to the right directory
cd "$(dirname "$0")"

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

echo "✅ Virtual environment activated"
echo ""

# Run migrations
echo "Running database migrations..."
python manage.py migrate

echo ""
echo "✅ Migrations complete!"
echo ""

# Start server
echo "🚀 Starting Django development server..."
echo ""
echo "=========================================="
echo "Server running at: http://localhost:8000"
echo "Admin panel: http://localhost:8000/admin"
echo "API: http://localhost:8000/api"
echo "=========================================="
echo ""

python manage.py runserver
