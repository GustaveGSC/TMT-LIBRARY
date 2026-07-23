"""RD Excel 纯逻辑的行为护栏。"""

import io

from openpyxl import Workbook, load_workbook

import routes.rd as rd_routes
import services.rd.change_documents as change_documents
from services.rd.change_documents import (
    build_ecr_xlsx,
    build_ecn_xlsx,
    compare_bom,
    parse_ecr_rows_xlsx,
)
from services.rd.pdm_to_bom import build_bom_data, build_erp_data


def _write_bom(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['层次', '图号', '品名', '规格', '数量', '单位', '状态'])
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_validate_bom_reports_open_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        change_documents, 'report_internal_error',
        lambda context: 'fixed-error-id' if context == '变更前文件读取失败' else None,
    )

    message = change_documents.validate_bom(tmp_path / 'missing.xlsx', role='before')

    assert message == '变更前文件无法读取（错误编号：fixed-error-id）'


def test_compare_bom_characterizes_version_change(tmp_path):
    assert not hasattr(rd_routes, '_compare_bom')
    assert not hasattr(rd_routes, '_validate_bom')

    before_path = tmp_path / 'before.xlsx'
    after_path = tmp_path / 'after.xlsx'
    root = ['1', 'ROOT-A01', '整机', 'ROOT_A01', 1, 'PCS', '已发布']
    _write_bom(before_path, [
        root,
        ['1.1', 'PART-A01', '零件', 'PART_A01', 2, 'PCS', '已发布'],
    ])
    _write_bom(after_path, [
        root,
        ['1.1', 'PART-A01', '零件', 'PART_A01', 2, 'PCS', '通用变更审核中'],
    ])

    result = compare_bom(before_path, after_path)

    assert result['stats'] == {'version': 1, 'added': 0, 'deleted': 0, 'total': 2}
    assert result['changes'] == [
        {
            'row_type': 'cancel', 'change_kind': '通用变更', 'level': '1.1',
            'main_drawing': 'ROOT-A01', 'drawing': 'PART-A01', 'name': '零件',
            'spec': 'PART_A01', 'qty': 2.0, 'change_method': '取消', 'seq': 1,
        },
        {
            'row_type': 'add', 'change_kind': '通用变更', 'level': '1.1',
            'main_drawing': 'ROOT-A01', 'drawing': 'PART-A02', 'name': '零件',
            'spec': 'PART_A02', 'qty': 2.0, 'change_method': '新增', 'seq': 2,
        },
    ]


def test_ecr_xlsx_round_trip_preserves_key_fields_and_detail():
    assert not hasattr(rd_routes, '_build_ecr_xlsx')
    assert not hasattr(rd_routes, '_parse_ecr_rows_xlsx')
    assert not hasattr(rd_routes, '_parse_ecr_rows_xls')

    fields = {
        'issuing_unit': '研发',
        'date': '2026-07-23',
        'ecr_code': 'ECR-001',
        'project': '测试项目',
        'change_type': '设计变更',
        'distribution': ['研发', '采购'],
        'change_reason': '设计优化',
        'change_subject': '替换零件',
        'change_desc': '验证生成与解析行为',
        'submitter': 'tester',
    }
    changes = [{
        'seq': 1,
        'row_type': 'added',
        'level': '1.1',
        'main_drawing': 'ROOT-A01',
        'drawing': 'PART-A01',
        'name': '零件',
        'spec': '规格A',
        'change_method': '数量变更',
        'qty_desc': '1→2 PCS',
    }]

    workbook = load_workbook(io.BytesIO(build_ecr_xlsx(fields, changes)))
    parsed_fields, parsed_changes = parse_ecr_rows_xlsx(workbook.active)
    workbook.close()

    assert parsed_fields == fields
    assert parsed_changes == [{
        'seq': 1,
        'level': '1.1',
        'main_drawing': 'ROOT-A01',
        'drawing': 'PART-A01',
        'name': '零件',
        'spec': '规格A',
        'change_method': '数量变更',
        'change_kind': '',
        'substitution': '1→2 PCS',
        'handling': '',
        'responsible_person': '',
        'row_type': 'added',
    }]


def test_ecn_xlsx_preserves_document_and_detail_layout():
    assert not hasattr(rd_routes, '_build_ecn_xlsx')

    fields = {
        'issuing_unit': '研发',
        'product': 'TMT-01',
        'responsible': 'tester',
        'date': '2026-07-23',
        'ecn_code': 'ECN-001',
        'import_method': '立即导入',
        'distribution': ['研发'],
        'change_reason': '结构优化',
        'change_desc': 'ECN fixture',
        'affected_files': ['BOM'],
    }
    changes = [{
        'seq': 1,
        'row_type': 'added',
        'level': '1.1',
        'main_drawing': 'ROOT-A01',
        'drawing': 'PART-A02',
        'name': '零件',
        'spec': '规格B',
        'change_method': '新增',
        'change_kind': '通用变更',
        'handling': '立即导入',
        'responsible_person': 'tester',
    }]

    workbook = load_workbook(io.BytesIO(build_ecn_xlsx(fields, changes)))
    sheet = workbook.active

    assert sheet.title == '变更通知单'
    assert [sheet.cell(3, column).value for column in (2, 5, 9, 12, 13)] == [
        '研发', 'TMT-01', 'tester', '2026-07-23', 'ECN-001',
    ]
    assert [sheet.cell(10, column).value for column in (1, 2, 4, 6, 7, 9, 11, 12, 13, 14)] == [
        1, 'ROOT-A01', 'PART-A02', '1.1', '零件', '规格B',
        '新增', '通用变更', '立即导入', 'tester',
    ]
    assert '☑ 立即导入' in sheet.cell(4, 2).value
    assert '☑ BOM' in sheet.cell(8, 2).value
    workbook.close()


def test_pdm_builders_preserve_constants_and_parent_child_relations():
    assert not hasattr(rd_routes, '_ptb_build_erp_data')
    assert not hasattr(rd_routes, '_ptb_build_bom_data')

    columns = ['品号', '层次', '数量', '品名', '工作中心']
    table_data = [
        ['ROOT', '1', '1', '整机', '源工作中心'],
        ['CHILD', '1.1', '2', '子件', ''],
        ['GRAND', '1.1.1', '3', '孙件', ''],
        ['SIBLING', '1.2', '无效数量', '并列子件', ''],
    ]

    erp_rows = build_erp_data(columns, table_data)
    assert len(erp_rows) == 4
    assert len(erp_rows[0]) == 46
    assert erp_rows[0][1:3] == ['ROOT', '整机']
    assert erp_rows[0][16:18] == [1001, 100802]
    assert erp_rows[0][22] == 5101
    assert erp_rows[0][23] == 3101

    bom_rows = build_bom_data(columns, table_data, total_level=3)
    assert bom_rows == [
        [100, 'ROOT', 1, 'CHILD', 2, 1, '', '', '', '', '', 1, ''],
        [100, 'ROOT', 1, 'SIBLING', 1, 1, '', '', '', '', '', 1, ''],
        [100, 'CHILD', 1, 'GRAND', 3, 1, '', '', '', '', '', 1, ''],
    ]
