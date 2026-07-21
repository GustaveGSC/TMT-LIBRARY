from pathlib import Path
import importlib.util

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


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

    assert 'xlrd' in requirements
    assert 'xlwt' not in requirements


def test_production_lock_covers_and_satisfies_all_direct_requirements():
    direct_lines = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    lock_lines = (BACKEND_DIR / 'requirements-lock-py311-linux.txt').read_text(
        encoding='utf-8'
    ).splitlines()

    direct = [
        Requirement(line.strip())
        for line in direct_lines
        if line.strip() and not line.lstrip().startswith('#')
    ]
    locked = {}
    for line in lock_lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        requirement = Requirement(line)
        assert len(requirement.specifier) == 1
        specifier = next(iter(requirement.specifier))
        assert specifier.operator == '=='
        locked[canonicalize_name(requirement.name)] = Version(specifier.version)

    for requirement in direct:
        name = canonicalize_name(requirement.name)
        assert name in locked, f'{requirement.name} is missing from the production lock'
        assert locked[name] in requirement.specifier, (
            f'{requirement.name}=={locked[name]} violates {requirement.specifier}'
        )

    assert 'xlwt' not in locked


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
