#!/bin/bash

# AutoDL Full Stack Deployment Script
# Usage: bash deploy_full_stack.sh

echo "🚀 Starting AVS2 Full Stack Deployment on AutoDL..."

# 1. Check Environment
if ! command -v conda &> /dev/null; then
    echo "❌ Conda not found. Please run this script in AutoDL terminal."
    exit 1
fi

# 2. Setup Conda Environment
ENV_NAME="combo-avs"
echo "📦 Setting up Conda environment: $ENV_NAME"

# Check if env exists
if conda info --envs | grep -q "$ENV_NAME"; then
    echo "✅ Environment $ENV_NAME already exists."
else
    echo "⚠️ Environment $ENV_NAME not found. Please create it first using CONDA_SETUP.md instructions."
    exit 1
fi

# Activate env
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

# 3. Install Dependencies
echo "⬇️ Installing Python dependencies..."
pip install fastapi uvicorn python-multipart opencv-python-headless aiofiles

# 4. Check Frontend Build
if [ -d "dist" ]; then
    echo "✅ Frontend build found in ./dist"
else
    echo "⚠️ Frontend build (./dist) not found!"
    echo "   Please run 'npm run build' locally and upload the 'dist' folder to /root/AVS2/"
    # Optional: Try to build if node is available (usually not on AutoDL default)
    if command -v npm &> /dev/null; then
        echo "   Node.js found, attempting to build..."
        npm install && npm run build
    fi
fi

# 5. Configure Environment Variables
# Create .env for production
echo "⚙️ Configuring environment variables..."
cat > .env <<EOF
AVS_DATA_DIR=/root/autodl-tmp/avs_data
AVS_ENV_COMBO=/root/miniconda3/envs/$ENV_NAME
AVS_ADMIN_PASSWORD=admin
EOF

# Ensure data directories exist
mkdir -p /root/autodl-tmp/avs_data/uploads
mkdir -p /root/autodl-tmp/avs_data/results
mkdir -p /root/autodl-tmp/avs_data/masks
mkdir -p /root/autodl-tmp/avs_data/models
mkdir -p /root/autodl-tmp/avs_data/tasks

# 6. Start Service
echo "🚀 Starting FastAPI Server on port 6006..."
echo "   Access URL: http://<AutoDL-IP>:6006 (via SSH Tunnel or Custom Service)"

# Run with uvicorn
# Using --host 0.0.0.0 to allow external access
python -m uvicorn api.main:app --host 0.0.0.0 --port 6006 --reload
