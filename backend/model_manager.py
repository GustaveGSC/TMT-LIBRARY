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
# 注意：桌面端（Electron）现在直接在本地下载 ONNX 文件并推理，不再经过服务器。
# 此处仅保留服务端下载路径（供 Web 端将来使用），目前服务端不加载模型。
MODEL_FILES = [
    ('config.json',               762),
    ('tokenizer_config.json',     434),
    ('tokenizer.json',            433_781),
    ('onnx/model_quantized.onnx', 23_000_000),  # ~23 MB，ONNX 量化版
]

TOTAL_BYTES_APPROX = sum(size for _, size in MODEL_FILES)

# ── 本地路径 ──────────────────────────────────────────────────────────────────
def get_model_dir() -> Path:
    base = Path.home() / '.tmt-library' / 'models' / MODEL_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base

def is_model_installed() -> bool:
    """检查核心模型文件是否存在（ONNX 量化版）"""
    model_dir = get_model_dir()
    required = ['tokenizer.json', 'onnx/model_quantized.onnx']
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
# _model 为 (tokenizer, ort.InferenceSession) 元组，未加载时为 None
_model          = None
_model_lock     = threading.Lock()
_model_loading  = False   # 后台加载中标志，避免重复启动线程

def _load_model():
    """在后台线程中加载模型，不阻塞 worker。"""
    global _model, _model_loading
    with _model_lock:
        if _model is not None:
            _model_loading = False
            return
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            model_dir = get_model_dir()
            tok = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
            tok.enable_truncation(max_length=512)
            tok.enable_padding(pad_id=0, pad_token='[PAD]')

            sess = ort.InferenceSession(
                str(model_dir / 'onnx' / 'model_quantized.onnx'),
                providers=['CPUExecutionProvider'],
            )
            _model = (tok, sess)
            print('[model_manager] 语义模型已加载', flush=True)
        except Exception as e:
            print(f'[model_manager] 模型加载失败: {e}', flush=True)
        finally:
            _model_loading = False

def get_model():
    """获取已加载的模型实例。
    未就绪时触发后台加载线程并返回 None（调用方应降级处理）。"""
    global _model_loading
    if _model is not None:
        return _model
    if is_model_installed() and not _model_loading:
        _model_loading = True
        threading.Thread(target=_load_model, daemon=True, name='model-load').start()
    return None  # 加载中或未安装，本次请求降级

# ── 对外接口 ──────────────────────────────────────────────────────────────────
def encode(texts: list[str]):
    """
    对文本列表编码，返回归一化向量矩阵（numpy ndarray，shape=[n, hidden]）。
    模型未就绪时返回 None。
    """
    model = get_model()
    if model is None:
        return None
    import numpy as np
    tok, sess = model
    enc  = tok.encode_batch(texts)
    ids  = np.array([e.ids            for e in enc], dtype=np.int64)
    mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    tids = np.zeros_like(ids)
    # ONNX 推理，取 last_hidden_state（index 0）
    hidden = sess.run(None, {
        'input_ids': ids, 'attention_mask': mask, 'token_type_ids': tids,
    })[0]   # [batch, seq_len, hidden_size]
    # mean pooling（按 attention_mask 加权平均）
    m   = mask[:, :, None].astype(np.float32)
    emb = (hidden * m).sum(axis=1) / m.sum(axis=1).clip(min=1e-9)
    # L2 normalize → 归一化向量，cosine sim = dot product
    norms = np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
    return (emb / norms).astype(np.float32)

def cosine_sim(a, b) -> float:
    """两个已归一化向量的余弦相似度（归一化后等于点积）"""
    import numpy as np
    return float(np.dot(a, b))

# ── 启动时自动触发下载 ────────────────────────────────────────────────────────
def _auto_start_download_if_needed():
    """服务启动后若模型未安装，自动在后台下载；已安装则不预加载（懒加载，首次请求时再加载）"""
    if not is_model_installed() and not _state['running']:
        print('[model_manager] 语义模型未安装，开始后台下载...', flush=True)
        start_download()
