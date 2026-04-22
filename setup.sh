#!/usr/bin/env bash
# OpsBrain pre-deployment setup — Linux / macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              OpsBrain — Pre-deployment Setup             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "  ✗  Python 3.8+ is required. Install from https://python.org"
    exit 1
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  ✓  Python $PYTHON_VER found"

# Install minimal setup dependencies
echo "  →  Installing setup dependencies…"
pip3 install anthropic openai boto3 google-cloud-aiplatform azure-identity python-dotenv --quiet 2>/dev/null || true

# Run the wizard
python3 setup.py "$@"
