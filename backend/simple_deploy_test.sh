#!/bin/bash
echo "=== Testing Backend Deployment Prerequisites ==="
echo "1. Checking if this is a FastAPI app..."
if [ -f "pyproject.toml" ] && grep -q "fastapi" pyproject.toml; then
  echo "   ✓ FastAPI detected"
else
  echo "   ✗ Not a FastAPI app"
fi

echo "2. Checking for main.py..."
if [ -f "app/main.py" ]; then
  echo "   ✓ app/main.py exists"
  grep -q "app = FastAPI" app/main.py && echo "   ✓ FastAPI instance named 'app' found"
else
  echo "   ✗ app/main.py not found"
fi

echo "3. Checking pyproject.toml dependencies..."
poetry export -f requirements.txt 2>&1 | head -5
