
import cv2
import time

print("Testing camera indices...")
for idx in range(4):
    print(f"\nTrying index {idx}...")
    cap = cv2.VideoCapture(idx)

    if cap.isOpened():
        # Set buffer size
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Try to read frames
        success_count = 0
        for i in range(10):
            ret, frame = cap.read()
            if ret and frame is not None:
                success_count += 1
                if success_count == 1:
                    print(f"  SUCCESS at index {idx}!")
                    print(f"  Frame shape: {frame.shape}")
                    cv2.imwrite(f"camera_test_idx{idx}.jpg", frame)

        if success_count > 0:
            print(f"  Index {idx}: {success_count}/10 successful reads")
            with open("working_camera_index.txt", "w") as f:
                f.write(str(idx))
        else:
            print(f"  Index {idx}: No frames captured")

        cap.release()
    else:
        print(f"  Index {idx}: Failed to open")

# Also test with different backends
print("\nTesting with V4L2 backend...")
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        print("V4L2 backend works!")
        cv2.imwrite("v4l2_test.jpg", frame)
    cap.release()
