"""
语义向量模型管理器（bge-small-zh-v1.5）
- 模型文件存储在 ~/.tmt-library/models/bge-small-zh-v1.5/
- 首次使用前需从 OSS 下载
- 提供下载进度轮询接口
- 提供 encode() 接口供 auto_match 调用
"""
import os
import threading
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────────────
OSS_BASE     = 'https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library/models/bge-small-zh-v1.5'
MODEL_DIR_NAME = 'bge-small-zh-v1.5'

# 模型文件列表及预估大小（bytes），用于进度计算
MODEL_FILES = [
    ('config.json',                        762),
    ('config_sentence_transformers.json',  512),
    ('tokenizer_config.json',              434),
    ('tokenizer.json',                     433_781),
    ('modules.json',                       349),
    ('sentence_bert_config.json',          52),
    ('1_Pooling/config.json',              190),
    ('model.safetensors',                  95_823_472),  # ~91 MB，主权重文件
]

TOTAL_BYTES_APPROX = sum(size for _, size in MODEL_FILES)

# ── 本地路径 ──────────────────────────────────────────────────────────────────
def get_model_dir() -> Path:
    base = Path.home() / '.tmt-library' / 'models' / MODEL_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base

def is_model_installed() -> bool:
    """检查核心模型文件是否存在"""
    model_dir = get_model_dir()
    required = ['config.json', 'tokenizer.json', 'model.safetensors']
    return all((model_dir / f).exists() for f in required)

# ── 下载状态 ──────────────────────────────────────────────────────────────────
_state = {
    'running':          False,
    'done':             False,
    'error':            None,
    'downloaded_bytes': 0,
    'total_bytes':      TOTAL_BYTES_APPROX,
    'current_file':     '',
    'file_index':       0,
    'file_total':       len(MODEL_FILES),
}
_state_lock = threading.Lock()

def get_download_state() -> dict:
    with _state_lock:
        s = dict(_state)
    pct = min(100, int(s['downloaded_bytes'] / s['total_bytes'] * 100)) if s['total_bytes'] else 0
    s['percent'] = pct
    return s

def start_download() -> bool:
    """启动后台下载线程，已在运行则返回 False"""
    with _state_lock:
        if _state['running']:
            return False
        _state.update({
            'running': True, 'done': False, 'error': None,
            'downloaded_bytes': 0, 'current_file': '', 'file_index': 0,
        })
    t = threading.Thread(target=_do_download, daemon=True, name='model-download')
    t.start()
    return True

def _do_download():
    import urllib.request
    model_dir = get_model_dir()
    try:
        for idx, (fname, _) in enumerate(MODEL_FILES):
            with _state_lock:
                _state['current_file'] = fname
                _state['file_index']   = idx + 1

            dest = model_dir / fname
            dest.parent.mkdir(parents=True, exist_ok=True)

            # 已存在则跳过（断点续传：按文件粒度）
            if dest.exists():
                with _state_lock:
                    _state['downloaded_bytes'] += dest.stat().st_size
                continue

            url = f'{OSS_BASE}/{fname}'
            tmp = dest.with_suffix(dest.suffix + '.tmp')
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    with open(tmp, 'wb') as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            with _state_lock:
                                _state['downloaded_bytes'] += len(chunk)
                tmp.rename(dest)   # 原子性重命名，避免写一半的文件
            except Exception:
                if tmp.exists():
                    tmp.unlink()
                raise

        # 2_Normalize/config.json 内容固定为 {}，本地生成无需从 OSS 下载
        normalize_cfg = model_dir / '2_Normalize' / 'config.json'
        normalize_cfg.parent.mkdir(parents=True, exist_ok=True)
        if not normalize_cfg.exists():
            normalize_cfg.write_text('{}', encoding='utf-8')

        with _state_lock:
            _state['done']    = True
            _state['running'] = False

        # 下载完成后立即加载模型
        _load_model()

    except Exception as e:
        with _state_lock:
            _state['error']   = str(e)
            _state['running'] = False

# ── 模型加载 ──────────────────────────────────────────────────────────────────
_model      = None
_model_lock = threading.Lock()

def _load_model():
    global _model
    with _model_lock:
        if _model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(str(get_model_dir()), device='cpu')
        except Exception as e:
            print(f'[model_manager] 模型加载失败: {e}')

def get_model():
    """获取已加载的模型实例，未安装或未加载返回 None"""
    if _model is not None:
        return _model
    if is_model_installed():
        _load_model()
    return _model

# ── 对外接口 ──────────────────────────────────────────────────────────────────
def encode(texts: list[str]):
    """
    对文本列表编码，返回归一化向量矩阵（numpy ndarray）。
    模型未就绪时返回 None。
    """
    model = get_model()
    if model is None:
        return None
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

def cosine_sim(a, b) -> float:
    """两个已归一化向量的余弦相似度（归一化后等于点积）"""
    import numpy as np
    return float(np.dot(a, b))
