"""
回切一次已发布的 shipping_order_finished 全量重算代。

仅限维护窗口使用。必须把同一个 task_id 同时传给两个参数，避免误操作：

python backend/scripts/rollback_shipping_generation.py \
  --task-id <UUID> --confirm-task-id <UUID>
"""

import argparse
import os
import sys


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app import create_app
from database.repository.shipping import (
    ShippingRepository,
    _invalidate_chart_options_cache,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--confirm-task-id', required=True)
    args = parser.parse_args()
    if args.task_id != args.confirm_task_id:
        raise SystemExit('确认 task_id 不一致，已拒绝回切')

    app = create_app()
    with app.app_context():
        result = ShippingRepository.rollback_published_full_generation(
            args.task_id
        )
        _invalidate_chart_options_cache()
        print(
            '回切完成：'
            f'task_id={args.task_id}, '
            f'rolled_back_at={result["rolled_back_at"]}',
            flush=True,
        )


if __name__ == '__main__':
    main()
