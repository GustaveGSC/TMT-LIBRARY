from typing import Optional, List
from database.base import db
from database.models.product.erp_code_rules import ErpCodeRule, VALID_TYPES, now_cst


class ErpCodeRuleRepository:

    @staticmethod
    def get_all() -> List[ErpCodeRule]:
        """获取所有规则，按前缀字母排序"""
        return ErpCodeRule.query.order_by(
            ErpCodeRule.prefix,
            ErpCodeRule.type
        ).all()

    @staticmethod
    def get_by_id(rule_id: int) -> Optional[ErpCodeRule]:
        return db.session.get(ErpCodeRule, rule_id)

    @staticmethod
    def get_by_prefix_type(prefix: str, type_: str) -> Optional[ErpCodeRule]:
        return ErpCodeRule.query.filter_by(prefix=prefix, type=type_).first()

    @staticmethod
    def create(prefix: str, type_: str, description: str = None) -> ErpCodeRule:
        rule = ErpCodeRule(
            prefix      = prefix.strip(),
            type        = type_,
            description = description,
            created_at  = now_cst(),
        )
        db.session.add(rule)
        db.session.commit()
        return rule

    @staticmethod
    def update(rule: ErpCodeRule, **kwargs) -> ErpCodeRule:
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        db.session.commit()
        return rule

    @staticmethod
    def delete(rule: ErpCodeRule) -> None:
        db.session.delete(rule)
        db.session.commit()