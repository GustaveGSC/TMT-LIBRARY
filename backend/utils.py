from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def now_cst() -> datetime:
    """返回当前北京时间（无 tzinfo，兼容 SQLAlchemy DateTime 列）"""
    return datetime.now(CST).replace(tzinfo=None)
