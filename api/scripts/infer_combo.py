import argparse
import sys
import json
import zipfile
import shutil
import numpy as np
import cv2
from pathlib import Path

# Add project root to sys.path to import modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import adapter (this script runs in the correct Conda env, so imports should work)
try:
    from api.models.combo_adapter import ComboAdapter
except ImportError as e:
    print(f"Error importing ComboAdapter: {e}")
    sys.exit(1)

def extract_frames(video_path: str) -> list[np.ndarray]:
    cap = cv2.VideoCapture(video_path)
    frames = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
    cap.release()
    return frames

def main():
    parser = argparse.ArgumentParser(description="Run COMBO inference")
    parser.add_argument("--task_id", required=True, help="Task ID")
    parser.add_argument("--file_id", required=True, help="Uploaded file ID")
    parser.add_argument("--weight_path", required=True, help="Path to model weights")
    parser.add_argument("--uploads_dir", required=True, help="Uploads directory")
    parser.add_argument("--results_dir", required=True, help="Results directory")
    parser.add_argument("--masks_dir", required=True, help="Masks directory")
    
    args = parser.parse_args()
    
    uploads_dir = Path(args.uploads_dir)
    results_dir = Path(args.results_dir)
    masks_dir = Path(args.masks_dir)
    
    # Find upload
    matches = list(uploads_dir.glob(f"{args.file_id}__*"))
    if not matches:
        print(f"Error: File {args.file_id} not found")
        sys.exit(1)
    video_path = str(matches[0])
    
    print(f"Loading model from {args.weight_path}...")
    try:
        adapter = ComboAdapter()
        adapter.load_weights(args.weight_path)
    except Exception as e:
        print(f"Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    print(f"Extracting frames from {video_path}...")
    frames = extract_frames(video_path)
    
    # Dummy audio feature
    audio_feat = np.random.rand(len(frames), 128).astype(np.float32)
    
    print(f"Running inference on {len(frames)} frames...")
    masks_bytes = []
    try:
        for i, mask_png in enumerate(adapter.infer(frames, audio_feat)):
            masks_bytes.append(mask_png)
            if i % 10 == 0:
                print(f"Processed {i}/{len(frames)} frames")
    except Exception as e:
        print(f"Inference error: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # Save results
    masks_zip_path = masks_dir / f"{args.task_id}.zip"
    print(f"Saving masks to {masks_zip_path}...")
    with zipfile.ZipFile(masks_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, mask_data in enumerate(masks_bytes):
            zf.writestr(f"mask_{i+1:04d}.png", mask_data)
            
    # Result video (copy for now)
    result_path = results_dir / f"{args.task_id}.mp4"
    shutil.copyfile(video_path, result_path)
    
    print("Done.")

if __name__ == "__main__":
    main()
