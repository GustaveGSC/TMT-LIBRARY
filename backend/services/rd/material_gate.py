"""研发物料门禁业务规则。"""

from database.repository.rd.material_gate import material_gate_repository


class MaterialGateService:
    LEVELS = {'warn', 'block'}
    DUPLICATE_MESSAGE = '该物料编码已有在架门禁，请先下架旧记录'

    @staticmethod
    def _required_text(payload: dict, key: str, label: str, max_length: int) -> str:
        value = str(payload.get(key) or '').strip()
        if not value:
            raise ValueError(f'{label}不能为空')
        if len(value) > max_length:
            raise ValueError(f'{label}不能超过{max_length}个字符')
        return value

    def _validated(self, payload: dict) -> tuple[str, str, str, str]:
        code = self._required_text(payload, 'code', '物料编码', 64)
        name = self._required_text(payload, 'name', '名称', 200)
        level = self._required_text(payload, 'level', '门禁级别', 16)
        if level not in self.LEVELS:
            raise ValueError('门禁级别只能是 warn 或 block')
        reason = self._required_text(payload, 'reason', '门禁原因', 500)
        return code, name, level, reason

    @staticmethod
    def list_active() -> list[dict]:
        return [item.to_dict() for item in material_gate_repository.list_active()]

    @staticmethod
    def list_all() -> list[dict]:
        return [item.to_dict() for item in material_gate_repository.list_all()]

    def create(self, payload: dict, created_by: str | None) -> dict:
        code, name, level, reason = self._validated(payload)
        if material_gate_repository.get_active_by_code(code):
            raise ValueError(self.DUPLICATE_MESSAGE)
        return material_gate_repository.create(code, name, level, reason, created_by).to_dict()

    def update(self, gate_id: int, payload: dict) -> dict | None:
        gate = material_gate_repository.get(gate_id)
        if not gate:
            return None
        code, name, level, reason = self._validated(payload)
        if gate.is_active and material_gate_repository.get_active_by_code(code, exclude_id=gate.id):
            raise ValueError(self.DUPLICATE_MESSAGE)
        return material_gate_repository.update(gate, code, name, level, reason).to_dict()

    def set_active(self, gate_id: int, is_active: bool) -> dict | None:
        gate = material_gate_repository.get(gate_id)
        if not gate:
            return None
        if is_active and material_gate_repository.get_active_by_code(gate.code, exclude_id=gate.id):
            raise ValueError(self.DUPLICATE_MESSAGE)
        return material_gate_repository.set_active(gate, is_active).to_dict()

    @staticmethod
    def delete(gate_id: int) -> bool:
        gate = material_gate_repository.get(gate_id)
        if not gate:
            return False
        material_gate_repository.delete(gate)
        return True

    @staticmethod
    def check(codes) -> dict:
        normalized = sorted({
            str(code).strip()
            for code in (codes or [])
            if code is not None and str(code).strip()
        })
        result = {'warn': [], 'block': []}
        seen = set()
        for gate in material_gate_repository.find_active_by_codes(normalized):
            if gate.code in seen:
                continue
            seen.add(gate.code)
            result[gate.level].append({'code': gate.code, 'name': gate.name, 'reason': gate.reason})
        return result


material_gate_service = MaterialGateService()
