"""Lazy offline CrossEncoder adapter; never loaded by the base API."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'
SHA256 = 'd9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286'


class LocalReranker:
    def __init__(self):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        manifest = json.loads((ROOT / '.local/reranker-manifest.json').read_text(encoding='utf-8-sig'))
        if manifest['revision'] != REVISION or manifest['model_id'] != 'BAAI/bge-reranker-v2-m3':
            raise RuntimeError('Unexpected reranker checkpoint')
        snapshot = Path(manifest['snapshot_path'])
        weights = snapshot / 'model.safetensors'
        with weights.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if checksum != SHA256 or weights.stat().st_size != 2271071852:
            raise RuntimeError('Reranker checkpoint integrity failed')
        import torch
        from sentence_transformers import CrossEncoder
        torch.set_num_threads(4)
        self.model = CrossEncoder(str(snapshot), device='cpu', max_length=512,
                                 activation_fn=torch.nn.Sigmoid(), local_files_only=True,
                                 trust_remote_code=False)
        self.manifest = manifest

    def __call__(self, pairs):
        if not pairs:
            return []
        # Refuse silent truncation of the request or the supporting activity.
        lengths = self.model.tokenizer([q for q, _ in pairs], [p for _, p in pairs],
                                       truncation=False, return_length=True)['length']
        if max(lengths) > 512:
            raise ValueError('Reranker pair exceeds the 512-token experiment limit')
        return self.model.predict(pairs, batch_size=2, show_progress_bar=False).reshape(-1).tolist()
