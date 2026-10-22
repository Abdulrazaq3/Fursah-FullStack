"""Download a pinned public checkpoint. Inference is offline in the experiment."""
from __future__ import annotations

import json
import argparse
import os
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"
os.environ["HF_HOME"] = str(LOCAL / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

sys.path.insert(0, str(ROOT / "backend/app/infrastructure/models"))
from model_integrity import MODEL_REVISION, verify_checkpoint, recover_cached_weights
from huggingface_hub import hf_hub_download, snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Validate or recover cached weights without network access')
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    manifest_path = LOCAL / "model-manifest.json"
    model_id = "BAAI/bge-m3"
    revision = MODEL_REVISION
    started = perf_counter()
    cache = LOCAL / 'huggingface' / 'hub'
    snapshot = cache / 'models--BAAI--bge-m3' / 'snapshots' / revision
    ready = recover_cached_weights(snapshot, cache)
    if args.check_only and not ready:
        print('Local checkpoint is incomplete; download required.', flush=True)
        raise SystemExit(1)
    if not ready:
        print(f"Downloading {model_id} at revision {revision}", flush=True)
        cached_weights = snapshot / 'pytorch_model.bin'
        hf_hub_download(
            repo_id=model_id, filename='pytorch_model.bin', revision=revision,
            token=False, cache_dir=cache, force_download=cached_weights.exists(),
        )
        if not recover_cached_weights(snapshot, cache):
            raise RuntimeError('Downloaded weights did not pass integrity checks.')
    required = ['config.json', 'modules.json', 'sentence_bert_config.json', 'tokenizer_config.json', 'tokenizer.json', 'sentencepiece.bpe.model', '1_Pooling/config.json']
    if any(not (snapshot / name).is_file() for name in required):
        if args.check_only:
            print('Local tokenizer or model configuration is incomplete.', flush=True)
            raise SystemExit(1)
        snapshot = Path(snapshot_download(
            repo_id=model_id, revision=revision, token=False, cache_dir=cache,
            allow_patterns=required + ['config_sentence_transformers.json', 'special_tokens_map.json'],
            max_workers=2,
        ))
    manifest = {
        "model_id": model_id,
        "revision": revision,
        "snapshot_path": str(Path(snapshot).resolve()),
        "download_seconds": round(perf_counter() - started, 3),
        "embedding_mode": "dense",
        "dimensions": 1024,
    }
    manifest["weights_sha256"] = verify_checkpoint(manifest)
    manifest["status"] = "verified"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Checkpoint ready locally; manifest written.", flush=True)


if __name__ == "__main__":
    main()
