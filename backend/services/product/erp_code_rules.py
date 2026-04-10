from database.repository.product.erp_code_rules import ErpCodeRuleRepository
from database.models.product.erp_code_rules import VALID_TYPES, TYPE_LABELS
from result import Result


class ErpCodeRuleService:

    def get_all(self) -> Result:
        rules = ErpCodeRuleRepository.get_all()
        return Result.ok(data=[r.to_dict() for r in rules])

    def create(self, prefix: str, type_: str, description: str = None) -> Result:
        prefix = (prefix or '').strip()
        if not prefix:
            return Result.fail('前缀不能为空')
        if type_ not in VALID_TYPES:
            return Result.fail(f'类型无效，可选值：{", ".join(VALID_TYPES)}')
        if ErpCodeRuleRepository.get_by_prefix_type(prefix, type_):
            return Result.fail(f'前缀 "{prefix}" 的 {TYPE_LABELS[type_]} 规则已存在')

        rule = ErpCodeRuleRepository.create(prefix, type_, description)
        return Result.ok(data=rule.to_dict(), message='规则创建成功')

    def update(self, rule_id: int, **kwargs) -> Result:
        rule = ErpCodeRuleRepository.get_by_id(rule_id)
        if not rule:
            return Result.fail(f'规则 {rule_id} 不存在')

        # 如果修改了 prefix 或 type，检查唯一性
        new_prefix = kwargs.get('prefix', rule.prefix).strip()
        new_type   = kwargs.get('type',   rule.type)
        if new_type not in VALID_TYPES:
            return Result.fail(f'类型无效，可选值：{", ".join(VALID_TYPES)}')
        if (new_prefix != rule.prefix or new_type != rule.type):
            if ErpCodeRuleRepository.get_by_prefix_type(new_prefix, new_type):
                return Result.fail(f'前缀 "{new_prefix}" 的 {TYPE_LABELS[new_type]} 规则已存在')

        if 'prefix' in kwargs:
            kwargs['prefix'] = new_prefix
        rule = ErpCodeRuleRepository.update(rule, **kwargs)
        return Result.ok(data=rule.to_dict(), message='更新成功')

    def toggle_disabled(self, rule_id: int) -> Result:
        rule = ErpCodeRuleRepository.get_by_id(rule_id)
        if not rule:
            return Result.fail(f'规则 {rule_id} 不存在')
        rule = ErpCodeRuleRepository.update(rule, is_disabled=not rule.is_disabled)
        return Result.ok(data=rule.to_dict(), message='已' + ('禁用' if rule.is_disabled else '启用'))

    def delete(self, rule_id: int) -> Result:
        rule = ErpCodeRuleRepository.get_by_id(rule_id)
        if not rule:
            return Result.fail(f'规则 {rule_id} 不存在')
        ErpCodeRuleRepository.delete(rule)
        return Result.ok(message='删除成功')


erp_code_rule_service = ErpCodeRuleService()