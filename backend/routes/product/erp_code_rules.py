from flask import Blueprint, request
from services.product.erp_code_rules import erp_code_rule_service
from result import Result

erp_code_rules_bp = Blueprint('erp_code_rules', __name__)


@erp_code_rules_bp.get('/')
def list_rules():
    return erp_code_rule_service.get_all().to_response()


@erp_code_rules_bp.post('/')
def create_rule():
    body        = request.get_json() or {}
    prefix      = body.get('prefix', '').strip()
    type_       = body.get('type', '').strip()
    description = (body.get('description') or '').strip() or None
    if not prefix or not type_:
        return Result.fail('prefix 和 type 不能为空').to_response()
    return erp_code_rule_service.create(prefix, type_, description).to_response()


@erp_code_rules_bp.put('/<int:rule_id>')
def update_rule(rule_id: int):
    body = request.get_json() or {}
    return erp_code_rule_service.update(rule_id, **body).to_response()


@erp_code_rules_bp.delete('/<int:rule_id>')
def delete_rule(rule_id: int):
    return erp_code_rule_service.delete(rule_id).to_response()