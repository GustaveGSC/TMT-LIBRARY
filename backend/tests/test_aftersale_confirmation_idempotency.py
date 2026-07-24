from flask import Flask

from database.base import db
from database.models.aftersale import AftersaleCase, AftersaleDictSuggestion
import database.models.product.category  # noqa: F401 - resolve ORM relationships
import database.models.product.finished  # noqa: F401 - resolve ORM relationships
import database.models.product.resource  # noqa: F401 - resolve ORM relationships
from database.repository.aftersale import AftersaleRepository


def _app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def test_repeated_confirmation_returns_existing_case_without_learning(monkeypatch):
    app = _app()
    with app.app_context():
        AftersaleCase.__table__.create(db.engine)
        existing = AftersaleCase(
            ecommerce_order_no='ORDER-1',
            status='confirmed',
            seller_remark='第一次确认',
        )
        db.session.add(existing)
        db.session.commit()

        repository = AftersaleRepository()

        def unexpected(*_args, **_kwargs):
            raise AssertionError('重复确认不应再次执行学习或写入')

        monkeypatch.setattr(repository, '_auto_update_reason_keywords', unexpected)
        monkeypatch.setattr(repository, '_upsert_reason_alias_affinity', unexpected)
        monkeypatch.setattr(repository, 'upsert_shipping_alias_by_id', unexpected)
        monkeypatch.setattr(repository, '_check_ignore_term_candidates', unexpected)

        result = repository.confirm_case(
            order_no='ORDER-1',
            products=[{'code': 'NEW'}],
            seller_remark='重复请求的新内容',
            buyer_remark=None,
            shipped_date=None,
            operator=None,
            channel_name=None,
            province=None,
            reasons_data=[{'reason_id': 99, 'shipping_alias_id': 88}],
        )

        assert result.id == existing.id
        assert result.seller_remark == '第一次确认'
        assert AftersaleCase.query.count() == 1


def test_dictionary_suggestion_log_context_is_explicit_not_repository_state():
    app = _app()
    with app.app_context():
        AftersaleDictSuggestion.__table__.create(db.engine)
        repository = AftersaleRepository()
        stale_context = {'dict_suggestions': []}
        current_context = {'dict_suggestions': []}
        repository._active_log_ctx = stale_context

        repository._upsert_dict_suggestion(
            'ignore_term', '配件', '测试', log_ctx=current_context,
        )

        assert stale_context['dict_suggestions'] == []
        assert current_context['dict_suggestions'] == [{
            'type': 'ignore_term',
            'value': '配件',
            'reason': '测试',
            'action': 'new',
        }]
