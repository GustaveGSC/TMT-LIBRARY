from database.models.account import Permission
from database.repository.account import PermissionRepository


def test_permission_name_is_part_of_model_and_response():
    permission = Permission(code='product:view', name='查看产品', description='读取产品资料')

    assert Permission.__table__.columns['name'].type.length == 255
    assert permission.to_dict()['name'] == '查看产品'


def test_permission_repository_persists_name(monkeypatch):
    captured = {}

    class FakePermission:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr('database.repository.account.Permission', FakePermission)
    monkeypatch.setattr('database.repository.account.db.session.add', lambda _permission: None)
    monkeypatch.setattr('database.repository.account.db.session.commit', lambda: None)

    PermissionRepository.create('product:view', '查看产品', '读取产品资料')

    assert captured == {
        'code': 'product:view',
        'name': '查看产品',
        'description': '读取产品资料',
    }
