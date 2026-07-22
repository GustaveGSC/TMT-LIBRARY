"""站点配置业务规则。"""

import json

from database.repository.config import site_config_repository


_MOTTOS_KEY = 'login_mottos'
_DEFAULT_MOTTOS = [
    '享受每一天的好心情',
    '保持你的好奇心',
    '今天也要元气满满',
    '把每件小事做到位',
    '细节决定品质',
    '记录，让知识留存',
]


class ConfigService:
    @staticmethod
    def get_login_mottos() -> list[str]:
        value = site_config_repository.get_value(_MOTTOS_KEY)
        if value:
            try:
                data = json.loads(value)
                if isinstance(data, list) and data:
                    return data
            except (TypeError, ValueError):
                pass
        return list(_DEFAULT_MOTTOS)

    @staticmethod
    def update_login_mottos(payload: dict) -> list[str]:
        mottos = payload.get('mottos', [])
        if not isinstance(mottos, list):
            raise ValueError('格式错误，mottos 须为数组')
        cleaned = [str(motto).strip() for motto in mottos if str(motto).strip()]
        if not cleaned:
            raise ValueError('语句列表不能为空')
        site_config_repository.set_value(
            _MOTTOS_KEY,
            json.dumps(cleaned, ensure_ascii=False),
        )
        return cleaned


config_service = ConfigService()
