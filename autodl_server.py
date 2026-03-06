
import sys
import shutil
import os
import zipfile
import tempfile
import numpy as np
import cv2
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path

# --- Configuration ---
PROJECT_ROOT = Path(__file__).resolve().parent

# Set the path to COMBO repo
COMBO_ROOT = Path("/root/autodl-tmp/COMBO-AVS")
if str(COMBO_ROOT) not in sys.path:
    sys.path.insert(0, str(COMBO_ROOT))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from api.models.combo_adapter import ComboAdapter
except ImportError:
    print("Warning: Could not import ComboAdapter directly. Checking typical paths...")
    sys.path.append(str(PROJECT_ROOT / "api"))
    try:
        from models.combo_adapter import ComboAdapter
    except ImportError:
         print("Error: Could not find ComboAdapter. Make sure 'api/models/combo_adapter.py' is uploaded.")
         sys.exit(1)

app = FastAPI()

# Model Cache: {"algorithm_name": adapter_instance}
loaded_models = {}

# Paths based on user input
# Structure: /root/autodl-tmp/COMBO-AVS/checkpoints/avs_s4/COMBO_R50_bs8_80k/model_best.pth
CHECKPOINTS_ROOT = COMBO_ROOT / "checkpoints"

def get_model_config(algorithm: str):
    """Return (config_path, weight_path) based on algorithm name"""
    # Mapping logic:
    # "avsegformer" or "combo" -> Default to ResNet50 S4
    # You can extend this logic to support more variants
    
    # Heuristic: Check if algorithm string contains "pvt" or "r50"
    is_pvt = "pvt" in algorithm.lower()
    
    if is_pvt:
        # PVT-v2
        config_path = str(COMBO_ROOT / "configs" / "avs_s4" / "COMBO_PVTV2B5_bs8_90k.yaml")
        weight_path = str(CHECKPOINTS_ROOT / "avs_s4" / "COMBO_PVTV2B5_bs8_80k" / "model_best.pth")
    else:
        # ResNet-50 (Default)
        config_path = str(COMBO_ROOT / "configs" / "avs_s4" / "COMBO_R50_bs8_90k.yaml")
        weight_path = str(CHECKPOINTS_ROOT / "avs_s4" / "COMBO_R50_bs8_80k" / "model_best.pth")
        
    return config_path, weight_path

@app.on_event("startup")
async def startup_event():
    # Preload default model (R50)
    config_path, weight_path = get_model_config("combo_r50")
    if os.path.exists(weight_path):
        print(f"Pre-loading default model from {weight_path}...")
        try:
            adapter = ComboAdapter(config_path=config_path)
            adapter.load_weights(weight_path)
            loaded_models["default"] = adapter
            print("Default model loaded!")
        except Exception as e:
            print(f"Error loading default model: {e}")
    else:
        print(f"Default weight not found at {weight_path}, skipping pre-load.")

@app.post("/predict")
async def predict(file: UploadFile = File(...), task_id: str = Form(...), algorithm: str = Form(...)):
    # Determine which model to use
    config_path, weight_path = get_model_config(algorithm)
    
    if not os.path.exists(weight_path):
        return {"error": f"Weight file not found: {weight_path}"}
        
    # Check cache
    model_key = weight_path
    if model_key not in loaded_models:
        print(f"Loading model for {algorithm}...")
        try:
            adapter = ComboAdapter(config_path=config_path)
            adapter.load_weights(weight_path)
            loaded_models[model_key] = adapter
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to load model: {str(e)}"}
    
    adapter = loaded_models[model_key]

    print(f"Received task {task_id} ({algorithm})")
    
    # Create temp dir for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        video_path = temp_path / file.filename
        
        # Save video
        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        # Extract frames
        print("Extracting frames...")
        frames = []
        cap = cv2.VideoCapture(str(video_path))
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
        cap.release()
        
        if not frames:
            return {"error": "Failed to extract frames"}

        # Dummy audio feature
        audio_feat = np.random.rand(len(frames), 128).astype(np.float32)

        # Inference
        print(f"Running inference on {len(frames)} frames...")
        zip_path = temp_path / "result.zip"
        
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            try:
                for i, mask_bytes in enumerate(adapter.infer(frames, audio_feat)):
                    if mask_bytes:
                        zf.writestr(f"mask_{i+1:04d}.png", mask_bytes)
            except Exception as e:
                print(f"Inference error: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        return FileResponse(
            path=zip_path, 
            filename=f"{task_id}_masks.zip",
            media_type="application/zip"
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6006)
