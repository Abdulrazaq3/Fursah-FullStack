"""Verify the pinned checkpoint before any local inference."""
from hashlib import sha256
from pathlib import Path
import os
import shutil
from uuid import uuid4

MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
WEIGHTS_SIZE = 2271145830
WEIGHTS_SHA256 = "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
XET_HASH = "61c2417ef33baa8496de69bd4394784d9b887a9027830afeac7e2ab8b4e1a6f1"


def verify_weights(weights: Path) -> str:
    size = weights.stat().st_size if weights.is_file() else 0
    if size != WEIGHTS_SIZE:
        raise RuntimeError(f"Model weights incomplete: {size} of {WEIGHTS_SIZE} bytes at {weights}")
    digest = sha256()
    with weights.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != WEIGHTS_SHA256:
        raise RuntimeError("Checkpoint checksum does not match the pinned official weights.")
    return digest.hexdigest()


def recover_cached_weights(snapshot: Path, cache: Path) -> bool:
    """Repair a stale snapshot only from checksum-verified project-cache bytes."""
    expected = cache / "models--BAAI--bge-m3" / "snapshots" / MODEL_REVISION
    if snapshot.resolve() != expected.resolve():
        raise RuntimeError("Recovery target is outside the pinned project snapshot.")
    destination = snapshot / "pytorch_model.bin"
    try:
        verify_weights(destination)
        return True
    except RuntimeError:
        pass
    candidates = [
        cache / "models--BAAI--bge-m3" / "blobs" / WEIGHTS_SHA256,
        cache / "blobs" / XET_HASH[:2] / XET_HASH,
    ]
    for candidate in candidates:
        if not candidate.resolve().is_relative_to(cache.resolve()):
            continue
        try:
            verify_weights(candidate)
        except RuntimeError:
            continue
        snapshot.mkdir(parents=True, exist_ok=True)
        temporary = snapshot / (".verified-weights-" + uuid4().hex)
        try:
            try:
                os.symlink(os.path.relpath(candidate, snapshot), temporary)
            except OSError:
                shutil.copyfile(candidate, temporary)
            # Keep the old pointer intact until the verified replacement is ready.
            os.replace(temporary, destination)
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
        verify_weights(destination)
        print("Recovered verified weights from the local cache; no download needed.", flush=True)
        return True
    return False


def verify_checkpoint(manifest: dict) -> str:
    if manifest.get("revision") != MODEL_REVISION:
        raise RuntimeError("Unsupported checkpoint revision; verify its metadata first.")
    return verify_weights(Path(manifest["snapshot_path"]) / "pytorch_model.bin")
