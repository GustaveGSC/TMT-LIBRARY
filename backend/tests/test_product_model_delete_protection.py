from types import SimpleNamespace

from database.repository.product.category import CategoryRepository
from services.product.category import CategoryService


def test_model_delete_is_blocked_when_business_data_references_it(monkeypatch):
    model = SimpleNamespace(id=7)
    deleted = []
    monkeypatch.setattr(CategoryRepository, 'get_model', lambda _id: model)
    monkeypatch.setattr(
        CategoryRepository,
        'get_model_reference_counts',
        lambda _id: {'finished_products': 0, 'aftersale_reasons': 3},
    )
    monkeypatch.setattr(
        CategoryRepository, 'delete_model', lambda obj: deleted.append(obj),
    )

    result = CategoryService().delete_model(7)

    assert result.success is False
    assert result.message == '型号仍被成品或售后工单引用，不能删除；请先迁移关联数据'
    assert deleted == []


def test_unreferenced_model_can_still_be_deleted(monkeypatch):
    model = SimpleNamespace(id=8)
    deleted = []
    monkeypatch.setattr(CategoryRepository, 'get_model', lambda _id: model)
    monkeypatch.setattr(
        CategoryRepository,
        'get_model_reference_counts',
        lambda _id: {'finished_products': 0, 'aftersale_reasons': 0},
    )
    monkeypatch.setattr(
        CategoryRepository, 'delete_model', lambda obj: deleted.append(obj),
    )

    result = CategoryService().delete_model(8)

    assert result.success is True
    assert deleted == [model]
