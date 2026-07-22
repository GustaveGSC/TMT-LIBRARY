import importlib
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_semantic_model_has_single_canonical_service_module():
    first = importlib.import_module('services.semantic_model')
    second = importlib.import_module('services.semantic_model')

    assert first is second
    assert not (BACKEND_DIR / 'model_manager.py').exists()
    assert first.get_download_state()['running'] is False


def test_runtime_code_no_longer_imports_root_model_manager():
    sources = [
        (BACKEND_DIR / 'app.py').read_text(encoding='utf-8'),
        (
            BACKEND_DIR / 'database' / 'repository' / 'aftersale' / '__init__.py'
        ).read_text(encoding='utf-8'),
    ]

    assert all('import model_manager' not in source for source in sources)
    assert all('from services import semantic_model' in source for source in sources)
