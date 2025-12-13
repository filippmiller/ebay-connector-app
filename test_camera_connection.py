"""
Diagnostic script to test DJI Osmo Pocket 3 camera connection
Run this to check if OpenCV can detect and connect to the camera
"""

import sys

try:
    import cv2
    print(f"✓ OpenCV installed: version {cv2.__version__}")
except ImportError:
    print("✗ OpenCV not installed!")
    sys.exit(1)

print("\n" + "=" * 60)
print("SCANNING FOR CAMERAS (UVC/DirectShow)")
print("=" * 60 + "\n")

# Test DirectShow backend (Windows)
backend = cv2.CAP_DSHOW
backend_name = "DirectShow (CAP_DSHOW)"

cameras_found = []

for i in range(10):
    print(f"Testing camera index {i}...", end=" ")
    cap = cv2.VideoCapture(i, backend)
    
    if cap.isOpened():
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Try to read one frame to make sure it works
        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"✓ FOUND - {width}x{height} @ {fps}fps")
            cameras_found.append({
                "index": i,
                "width": width,
                "height": height,
                "fps": fps,
                "frame_readable": True
            })
        else:
            print(f"⚠ Found but cannot read frames")
            cameras_found.append({
                "index": i,
                "width": width,
                "height": height,
                "fps": fps,
                "frame_readable": False
            })
        cap.release()
    else:
        print("✗ Not found")

print("\n" + "=" * 60)
print(f"SUMMARY: Found {len(cameras_found)} camera(s)")
print("=" * 60 + "\n")

if cameras_found:
    for cam in cameras_found:
        status = "✓ WORKING" if cam["frame_readable"] else "⚠ NOT READABLE"
        print(f"Camera {cam['index']}: {cam['width']}x{cam['height']} @ {cam['fps']}fps - {status}")
    
    # Test connection to first camera
    print("\n" + "=" * 60)
    print(f"TESTING CONNECTION TO CAMERA {cameras_found[0]['index']}")
    print("=" * 60 + "\n")
    
    test_cam = cv2.VideoCapture(cameras_found[0]['index'], backend)
    if test_cam.isOpened():
        print("✓ Camera opened successfully")
        
        # Try to read multiple frames
        success_count = 0
        for i in range(5):
            ret, frame = test_cam.read()
            if ret and frame is not None:
                success_count += 1
                print(f"  Frame {i+1}: ✓ Read successfully ({frame.shape})")
            else:
                print(f"  Frame {i+1}: ✗ Failed to read")
        
        test_cam.release()
        print(f"\nResult: {success_count}/5 frames read successfully")
        
        if success_count == 5:
            print("✓ Camera is working correctly!")
        else:
            print("⚠ Camera connection is unstable")
    else:
        print("✗ Failed to open camera")
else:
    print("✗ No cameras detected!")
    print("\nTroubleshooting:")
    print("1. Ensure DJI Osmo Pocket 3 is connected via USB")
    print("2. Check that the camera is in webcam/UVC mode")
    print("3. Check Windows Device Manager for 'DJI Osmo Pocket 3' under 'Cameras'")
    print("4. Try a different USB port or cable")
    print("5. Restart the camera or computer")

print("\n" + "=" * 60)
print("Diagnostic complete!")
print("=" * 60)
