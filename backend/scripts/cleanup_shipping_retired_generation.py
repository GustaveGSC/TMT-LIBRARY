"""
清理一次已验收全量重算所保留的退役 shipping generation。

python backend/scripts/cleanup_shipping_retired_generation.py \
  --published-task-id <UUID> --confirm-task-id <UUID>
"""

import argparse
import os
import sys


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app import create_app
from database.repository.shipping import ShippingRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--published-task-id', required=True)
    parser.add_argument('--confirm-task-id', required=True)
    args = parser.parse_args()
    if args.published_task_id != args.confirm_task_id:
        raise SystemExit('确认 task_id 不一致，已拒绝清理')

    app = create_app()
    with app.app_context():
        cleaned = ShippingRepository.cleanup_retired_full_generation(
            args.published_task_id
        )
        if not cleaned:
            raise SystemExit(
                '正式代标记不匹配或 standby 正在使用，未执行清理'
            )
        print(
            f'退役代清理完成：task_id={args.published_task_id}',
            flush=True,
        )


if __name__ == '__main__':
    main()
