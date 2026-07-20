from pathlib import Path
import importlib.util


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'capture_requirements_lock.py'


def _load_script():
    spec = importlib.util.spec_from_file_location('capture_requirements_lock', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_direct_requirements_include_runtime_packages_used_by_code_and_deployment():
    requirements = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8').lower()

    for package in ('openpyxl', 'oss2', 'gunicorn', 'packaging'):
        assert package in requirements


def test_lock_renderer_uses_exact_versions_and_records_platform():
    script = _load_script()

    rendered = script.render_lock([('Flask', '3.1.2'), ('gunicorn', '23.0.0')])

    assert 'Flask==3.1.2' in rendered
    assert 'gunicorn==23.0.0' in rendered
    assert '# Python:' in rendered
    assert '# Platform:' in rendered


def test_lock_generator_defaults_to_linux_python311_filename():
    script = _load_script()

    assert script.DEFAULT_OUTPUT.name == 'requirements-lock-py311-linux.txt'
