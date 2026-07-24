from database.base import db
from utils import now_cst


class ProductLifecycleTask(db.Model):
    """可跨 worker 查询的产品生命周期更新任务状态。"""

    __tablename__ = 'product_lifecycle_task'
    __table_args__ = (
        db.Index('ix_product_lifecycle_task_status_updated', 'status', 'updated_at'),
        db.UniqueConstraint('lease_key', name='uq_product_lifecycle_task_lease_key'),
    )

    id          = db.Column(db.String(36), primary_key=True)
    status      = db.Column(db.String(20), nullable=False)
    progress    = db.Column(db.JSON, nullable=True)
    result      = db.Column(db.JSON, nullable=True)
    message     = db.Column(db.Text, nullable=True)
    lease_key   = db.Column(db.String(64), nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at  = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)
    finished_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'task_id': self.id,
            'task_type': 'product_lifecycle',
            'status': self.status,
            'progress': self.progress or {},
            'result': self.result,
            'message': self.message or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'finished_at': self.finished_at.strftime('%Y-%m-%d %H:%M:%S') if self.finished_at else None,
        }
