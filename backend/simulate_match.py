# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app import create_app
app = create_app()

with app.app_context():
    from database.models.aftersale import (
        AftersaleCase, AftersaleCaseReason, AftersaleReason, AftersaleShippingAlias
    )
    from database.repository.aftersale import AftersaleRepository
    from sqlalchemy.orm import selectinload, joinedload

    repo = AftersaleRepository()

    cases = (
        AftersaleCase.query
        .filter_by(status='confirmed')
        .filter(AftersaleCase.seller_remark.isnot(None))
        .options(
            selectinload(AftersaleCase.case_reasons)
            .selectinload(AftersaleCaseReason.reason)
            .joinedload(AftersaleReason.category_obj),
            # no shipping_alias_obj relation
        )
        .order_by(AftersaleCase.id.desc())
        .limit(50)
        .all()
    )

    alias_map = {a.id: a.name for a in AftersaleShippingAlias.query.all()}

    hit_reason = 0; miss_reason = 0; no_reason_pred = 0
    hit_alias  = 0; miss_alias  = 0; no_alias_pred  = 0
    miss_reason_cases = []
    miss_alias_cases  = []
    no_pred_cases     = []

    for c in cases:
        actual_reasons = [
            (cr.reason.category_obj.name if cr.reason and cr.reason.category_obj else '?',
             cr.reason.name if cr.reason else '?',
             cr.reason_id)
            for cr in c.case_reasons if cr.reason_id
        ]
        actual_alias_ids = list({cr.shipping_alias_id for cr in c.case_reasons if cr.shipping_alias_id})

        product_codes = [p['code'] for p in (c.products or [])]
        prod_suggest = repo.suggest_product(
            product_codes, purchase_date_str=None,
            seller_remark=c.seller_remark,
            buyer_remark=c.buyer_remark,
            products=c.products or []
        )

        match_result = repo.auto_match(c.seller_remark or '', buyer_remark=c.buyer_remark)
        matched_items = (match_result or {}).get('items', [])
        cleaned_text  = (match_result or {}).get('cleaned_text', '')

        pred_alias_id  = prod_suggest.get('suggested_shipping_alias_id')  if prod_suggest else None
        pred_alias_src = prod_suggest.get('suggested_shipping_alias_source') if prod_suggest else None
        alias_ok       = (pred_alias_id in actual_alias_ids) if actual_alias_ids else None

        top_reason_id = matched_items[0]['reason_id'] if matched_items else None
        actual_ids    = [r[2] for r in actual_reasons]
        reason_ok     = (top_reason_id in actual_ids) if actual_ids and matched_items else None

        if   alias_ok  is True:  hit_alias  += 1
        elif alias_ok  is False: miss_alias += 1
        else:                    no_alias_pred += 1

        if   reason_ok is True:  hit_reason += 1
        elif reason_ok is False: miss_reason += 1
        else:                    no_reason_pred += 1

        info = {
            'id':          c.id,
            'buyer':      (c.buyer_remark  or '')[:30],
            'seller':     (c.seller_remark or '')[:50],
            'actual_reasons': actual_reasons,
            'pred_items':  matched_items[:3],
            'cleaned':     cleaned_text,
            'actual_alias': [alias_map.get(aid, str(aid)) for aid in actual_alias_ids],
            'pred_alias':  alias_map.get(pred_alias_id, str(pred_alias_id)) if pred_alias_id else None,
            'pred_alias_src': pred_alias_src,
            'reason_ok':   reason_ok,
            'alias_ok':    alias_ok,
        }
        if reason_ok is False: miss_reason_cases.append(info)
        if alias_ok  is False: miss_alias_cases.append(info)
        if reason_ok is None and actual_ids: no_pred_cases.append(info)

    total = len(cases)
    print(f'=== 50条模拟结果 ===')
    print(f'原因匹配: 命中={hit_reason}  未命中={miss_reason}  无预测={no_reason_pred}  合计={total}')
    print(f'简称匹配: 命中={hit_alias}   未命中={miss_alias}   无预测={no_alias_pred}   合计={total}')

    print(f'\n--- 原因未命中 ({len(miss_reason_cases)}条) ---')
    for d in miss_reason_cases:
        acts = [(r[0], r[1]) for r in d['actual_reasons']]
        top  = d['pred_items'][0] if d['pred_items'] else None
        pred_str = f"{top['category_name']}/{top['name']} (kw={top['keyword_score']:.2f} hs={top['history_score']:.2f})" if top else 'None'
        print(f'  [{d["id"]}] buyer={d["buyer"]!r}')
        print(f'          seller={d["seller"]!r}')
        print(f'          cleaned={d["cleaned"]!r}')
        print(f'          实际={acts}')
        print(f'          预测Top1={pred_str}')
        if len(d['pred_items']) > 1:
            for i, it in enumerate(d['pred_items'][1:], 2):
                print(f'          预测Top{i}={it["category_name"]}/{it["name"]} (kw={it["keyword_score"]:.2f} hs={it["history_score"]:.2f})')
        print()

    print(f'--- 简称未命中 ({len(miss_alias_cases)}条) ---')
    for d in miss_alias_cases:
        print(f'  [{d["id"]}] seller={d["seller"]!r}')
        print(f'          实际={d["actual_alias"]}  预测={d["pred_alias"]} (src={d["pred_alias_src"]})')

    print(f'\n--- 无原因预测但有实际原因 ({len(no_pred_cases)}条) ---')
    for d in no_pred_cases:
        acts = [(r[0], r[1]) for r in d['actual_reasons']]
        print(f'  [{d["id"]}] seller={d["seller"]!r}')
        print(f'          cleaned={d["cleaned"]!r}  实际={acts}')
