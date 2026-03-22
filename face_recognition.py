"""
Face Recognition using Gemini Multimodal Embeddings.

Captures a photo from the webcam, generates an embedding with
gemini-embedding-2-preview, and matches it against stored faces
using cosine similarity.

Usage:
    uv run face_recognition.py register    # Capture + name a new face
    uv run face_recognition.py recognize   # Identify who's in front of the camera
    uv run face_recognition.py list        # List all registered faces
    uv run face_recognition.py delete      # Remove a registered face
"""

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

EMBEDDING_MODEL = "gemini-embedding-2-preview"
FACES_DIR = Path(__file__).parent / "faces"
FACES_DB = FACES_DIR / "faces_db.json"
SIMILARITY_THRESHOLD = 0.75


def get_client() -> genai.Client:
    return genai.Client()


def capture_photo() -> np.ndarray:
    """Open the webcam, show a preview, and capture a photo on spacebar press."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("  Error: Could not open webcam.")
        sys.exit(1)

    print("\n  Camera is open. Press SPACE to capture, ESC to cancel.")

    frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            print("  Error: Could not read from webcam.")
            break

        display = frame.copy()
        h, w = display.shape[:2]
        cv2.putText(display, "SPACE = capture | ESC = cancel", (10, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("Face Capture", display)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            cap.release()
            cv2.destroyAllWindows()
            print("  Cancelled.")
            sys.exit(0)
        elif key == 32:  # SPACE
            break

    cap.release()
    cv2.destroyAllWindows()

    if frame is None:
        print("  Error: No frame captured.")
        sys.exit(1)

    return frame


def image_to_bytes(image: np.ndarray) -> bytes:
    """Encode an OpenCV image as JPEG bytes."""
    success, buffer = cv2.imencode(".jpg", image)
    if not success:
        raise RuntimeError("Failed to encode image")
    return buffer.tobytes()


def get_face_embedding(client: genai.Client, image_bytes: bytes) -> list[float]:
    """Generate an embedding for a face image using Gemini's multimodal model."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
    )
    return result.embeddings[0].values


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    dot = np.dot(a_np, b_np)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def load_faces_db() -> dict:
    """Load the faces database from disk."""
    if not FACES_DB.exists():
        return {"faces": []}
    with open(FACES_DB) as f:
        return json.load(f)


def save_faces_db(db: dict):
    """Save the faces database to disk."""
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    with open(FACES_DB, "w") as f:
        json.dump(db, f, indent=2)


def register_face():
    """Capture a photo, name it, and store the embedding."""
    name = input("  Enter name for this person: ").strip()
    if not name:
        print("  Name cannot be empty.")
        return

    print(f"\n  Registering face for: {name}")
    image = capture_photo()

    photo_path = FACES_DIR / f"{name.lower().replace(' ', '_')}.jpg"
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(photo_path), image)
    print(f"  Photo saved to {photo_path}")

    print("  Generating face embedding...")
    client = get_client()
    image_bytes = image_to_bytes(image)
    embedding = get_face_embedding(client, image_bytes)

    db = load_faces_db()

    # Update existing entry or add new one
    existing = next((f for f in db["faces"] if f["name"].lower() == name.lower()), None)
    if existing:
        existing["embedding"] = embedding
        existing["photo"] = str(photo_path)
        print(f"  Updated existing entry for {name}.")
    else:
        db["faces"].append({
            "name": name,
            "embedding": embedding,
            "photo": str(photo_path),
        })
        print(f"  Registered new face: {name}")

    save_faces_db(db)
    print(f"  Done! {len(db['faces'])} face(s) in database.")


def recognize_face():
    """Capture a photo and find the closest match in the database."""
    db = load_faces_db()
    if not db["faces"]:
        print("  No faces registered yet. Run with 'register' first.")
        return

    print(f"\n  {len(db['faces'])} face(s) in database. Capturing photo...")
    image = capture_photo()

    print("  Generating embedding...")
    client = get_client()
    image_bytes = image_to_bytes(image)
    embedding = get_face_embedding(client, image_bytes)

    print("  Comparing against registered faces...\n")

    results = []
    for face in db["faces"]:
        similarity = cosine_similarity(embedding, face["embedding"])
        results.append((face["name"], similarity))

    results.sort(key=lambda x: x[1], reverse=True)

    print(f"  {'Name':<20} {'Similarity':>10}")
    print(f"  {'─'*20} {'─'*10}")
    for name, sim in results:
        marker = " <-- MATCH" if sim >= SIMILARITY_THRESHOLD else ""
        print(f"  {name:<20} {sim:>10.4f}{marker}")

    best_name, best_sim = results[0]
    print()
    if best_sim >= SIMILARITY_THRESHOLD:
        print(f"  Hello, {best_name}! (confidence: {best_sim:.2%})")
    else:
        print(f"  Unknown face. Best guess: {best_name} ({best_sim:.2%}), below threshold ({SIMILARITY_THRESHOLD:.0%}).")
        print("  Try registering this face with 'register'.")


def list_faces():
    """List all registered faces."""
    db = load_faces_db()
    if not db["faces"]:
        print("  No faces registered yet.")
        return

    print(f"\n  Registered faces ({len(db['faces'])}):\n")
    for i, face in enumerate(db["faces"], 1):
        emb_len = len(face["embedding"])
        print(f"  {i}. {face['name']} (embedding: {emb_len}d, photo: {face['photo']})")


def delete_face():
    """Remove a face from the database."""
    db = load_faces_db()
    if not db["faces"]:
        print("  No faces registered.")
        return

    list_faces()
    name = input("\n  Enter name to delete: ").strip()

    original_count = len(db["faces"])
    db["faces"] = [f for f in db["faces"] if f["name"].lower() != name.lower()]

    if len(db["faces"]) < original_count:
        save_faces_db(db)
        print(f"  Deleted {name}. {len(db['faces'])} face(s) remaining.")
    else:
        print(f"  No face found with name '{name}'.")


def main():
    print(r"""
    ╔══════════════════════════════════════════════════════════╗
    ║          Face Recognition (Gemini Embeddings)           ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    if len(sys.argv) < 2:
        print("  Usage:")
        print("    uv run face_recognition.py register   - Capture and name a face")
        print("    uv run face_recognition.py recognize   - Identify a face")
        print("    uv run face_recognition.py list        - List registered faces")
        print("    uv run face_recognition.py delete      - Remove a face")
        return

    command = sys.argv[1].lower()

    commands = {
        "register": register_face,
        "recognize": recognize_face,
        "list": list_faces,
        "delete": delete_face,
    }

    if command not in commands:
        print(f"  Unknown command: {command}")
        print(f"  Available: {', '.join(commands.keys())}")
        return

    commands[command]()


if __name__ == "__main__":
    main()
