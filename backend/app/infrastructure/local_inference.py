"""Offline float32 inference; one model resident and one worker at a time."""
from contextlib import contextmanager
from functools import lru_cache
import gc
import importlib.util
import json
import os
import threading
from pathlib import Path

from .config import PROJECT_ROOT
from .errors import ModelExecutionError, WorkflowBusyError


def _experiment(name):
    spec = importlib.util.spec_from_file_location('fursah_pilot_' + name,
                                                Path(__file__).parent / 'models' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Preserve the measured adapter bytes while supplying its workspace.
    module.ROOT = PROJECT_ROOT
    return module


class LocalInference:
    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._stage = None

    def warmup(self):
        """Prepare cold imports/checkpoints before accepting pilot HTTP traffic."""
        with self.session():
            self.encode('فحص تحميل محلي')
            self.score_pairs([('فحص تحميل محلي', 'فحص تحميل محلي')])

    @contextmanager
    def session(self):
        # Cancelling the HTTP await must not release a still-running CPU worker.
        if not self._lock.acquire(blocking=False):
            raise WorkflowBusyError()
        try:
            yield self
        finally:
            self._lock.release()

    def _load(self, stage):
        if self._stage == stage:
            return self._model
        self._model = None
        self._stage = None
        gc.collect()
        for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
            os.environ[key] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        try:
            if stage == 'reranker':
                self._model = _experiment('local_reranker').LocalReranker()
            else:
                manifest = json.loads((PROJECT_ROOT / '.local/model-manifest.json').read_text(encoding='utf-8-sig'))
                if (manifest['model_id'] != 'BAAI/bge-m3' or manifest['dimensions'] != 1024
                        or manifest['embedding_mode'] != 'dense'):
                    raise ValueError('Unexpected embedding manifest')
                _experiment('model_integrity').verify_checkpoint(manifest)
                import torch
                from sentence_transformers import SentenceTransformer
                torch.set_num_threads(4)
                self._model = SentenceTransformer(manifest['snapshot_path'], device='cpu',
                                                  local_files_only=True, trust_remote_code=False)
                self._model.max_seq_length = 512
                if self._model.get_sentence_embedding_dimension() != 1024:
                    raise ValueError('Unexpected embedding dimensions')
            self._stage = stage
            return self._model
        except Exception as exc:
            self._model = None
            gc.collect()
            raise ModelExecutionError() from exc

    def encode(self, text):
        try:
            model = self._load('embedding')
            if len(model.tokenizer(text, truncation=False)['input_ids']) > 512:
                raise ValueError('Embedding input exceeds the evaluated token limit')
            return model.encode([text], normalize_embeddings=True, convert_to_numpy=True,
                                show_progress_bar=False)[0].tolist()
        except ModelExecutionError:
            raise
        except Exception as exc:
            raise ModelExecutionError() from exc

    def score_pairs(self, pairs):
        try:
            return self._load('reranker')(pairs)
        except ModelExecutionError:
            raise
        except Exception as exc:
            raise ModelExecutionError() from exc

    def encode_many(self, texts, *, batch_size=4):
        """Offline indexing batch; preserve the same model, normalization and limit."""
        try:
            model = self._load('embedding')
            if not texts or not 1 <= batch_size <= 8:
                raise ValueError('Invalid indexing batch')
            for text in texts:
                if len(model.tokenizer(text, truncation=False)['input_ids']) > 512:
                    raise ValueError('Index document exceeds the explicit 512-token limit')
            return model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                convert_to_numpy=True, show_progress_bar=False).tolist()
        except ModelExecutionError:
            raise
        except Exception as exc:
            raise ModelExecutionError() from exc


@lru_cache(maxsize=1)
def get_local_inference():
    return LocalInference()
