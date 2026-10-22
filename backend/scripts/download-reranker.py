"""Download one pinned reranker separately from offline inference."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from huggingface_hub import snapshot_download

REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'
WEIGHTS_SHA256 = 'd9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286'


def main():
    print('Downloading pinned BAAI/bge-reranker-v2-m3 (about 2.3 GB); existing files are reused.', flush=True)
    snapshot = Path(snapshot_download(
        'BAAI/bge-reranker-v2-m3', revision=REVISION, token=False,
        cache_dir=ROOT / '.local/reranker-cache', max_workers=2,
        allow_patterns=['model.safetensors', 'config.json', 'tokenizer_config.json',
                        'tokenizer.json', 'sentencepiece.bpe.model', 'special_tokens_map.json'],
    ))
    weights = snapshot / 'model.safetensors'
    with weights.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    if weights.stat().st_size != 2271071852 or checksum != WEIGHTS_SHA256:
        raise RuntimeError('Reranker weights failed size or SHA256 verification; inference is not ready.')
    manifest = {'model_id': 'BAAI/bge-reranker-v2-m3', 'revision': REVISION,
                'snapshot_path': str(snapshot.resolve()), 'weights_sha256': checksum,
                'weights_bytes': weights.stat().st_size, 'status': 'verified'}
    (ROOT / '.local/reranker-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Verified local reranker. Inference needs no network.', flush=True)


if __name__ == '__main__':
    main()
