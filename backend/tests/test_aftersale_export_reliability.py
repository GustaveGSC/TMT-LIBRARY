from types import SimpleNamespace

import openpyxl

import aftersale_export_tasks as task_store
import services.aftersale as aftersale_module
import routes.aftersale as aftersale_routes


def test_running_file_task_becomes_interrupted_after_worker_is_gone(tmp_path, monkeypatch):
    monkeypatch.setenv('AFTERSALE_EXPORT_DIR', str(tmp_path))
    monkeypatch.setattr(task_store, '_process_alive', lambda _pid: False)
    task_id = '11111111-1111-1111-1111-111111111111'

    task_store.create(task_id)
    task_store.update(task_id, 'running')
    recovered = task_store.get(task_id)

    assert recovered['status'] == 'interrupted'
    assert '重新发起' in recovered['message']


def test_task_id_cannot_escape_export_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('AFTERSALE_EXPORT_DIR', str(tmp_path))

    assert task_store.get('../../outside') is None
    task_store.delete('../../outside')
    assert list(tmp_path.iterdir()) == []


def test_interrupted_task_maps_to_error_for_existing_frontend(monkeypatch):
    from flask import Flask

    monkeypatch.setattr(
        aftersale_routes.export_tasks,
        'get',
        lambda _task_id: {'status': 'interrupted', 'message': 'reload 中断'},
    )
    app = Flask(__name__)
    with app.test_request_context():
        response, status_code = aftersale_routes.export_cases_status(
            '11111111-1111-1111-1111-111111111111'
        )

    assert status_code == 200
    assert response.get_json()['data'] == {
        'status': 'error',
        'message': 'reload 中断',
    }


def test_export_pages_database_rows_and_writes_directly_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv('EXPORT_PAGE_SIZE', '2')
    page_calls = []

    def case(case_id):
        return SimpleNamespace(
            id=case_id,
            ecommerce_order_no=f'ORDER-{case_id}',
            products=[],
            shipped_date=None,
            channel_name='线上',
            province='浙江省',
            buyer_remark=None,
            seller_remark=None,
        )

    pages = {1: [case(1), case(2)], 2: [case(3)]}

    def get_cases(*_args, **kwargs):
        page_calls.append((kwargs['page'], kwargs['page_size'], kwargs['count_total']))
        return pages.get(kwargs['page'], []), (3 if kwargs['count_total'] else None)

    class FakeQuery:
        def filter(self, *_args):
            return self

        def options(self, *_args):
            return self

        def all(self):
            return []

    fake_case_model = SimpleNamespace(
        id=SimpleNamespace(in_=lambda _ids: True),
        case_reasons=object(),
        query=FakeQuery(),
    )
    loader = SimpleNamespace(selectinload=lambda _attribute: loader)
    monkeypatch.setattr(aftersale_module._repo, 'get_cases', get_cases)
    monkeypatch.setattr(aftersale_module, 'AftersaleCase', fake_case_model)
    monkeypatch.setattr(aftersale_module, 'AftersaleCaseReason', SimpleNamespace(
        reason=object(), product_model=object(), shipping_alias=object(),
    ))
    monkeypatch.setattr(aftersale_module, 'AftersaleReason', SimpleNamespace(category_obj=object()))
    monkeypatch.setattr(
        'database.models.product.category.ProductModel',
        SimpleNamespace(series=object()),
    )
    monkeypatch.setattr(
        'database.models.product.category.ProductSeries',
        SimpleNamespace(category=object()),
    )
    monkeypatch.setattr('sqlalchemy.orm.selectinload', lambda _attribute: loader)
    monkeypatch.setattr('database.base.db.session.expunge_all', lambda: None)
    output_path = tmp_path / 'export.xlsx'

    result = aftersale_module.AftersaleService().export_cases_to_file(
        output_path,
        status='confirmed', date_start=None, date_end=None,
        reason_id=None, channel_name=None, province=None, city=None, district=None,
        reason_category=None, reason_name=None, shipping_alias=None,
    )

    assert result == {'exported_cases': 3, 'total': 3}
    assert page_calls == [(1, 2, True), (2, 2, False)]
    workbook = openpyxl.load_workbook(output_path, read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    workbook.close()
    assert rows[1][0] == 'ORDER-1'
    assert rows[3][0] == 'ORDER-3'
