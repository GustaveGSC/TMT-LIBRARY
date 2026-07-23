"""PDM 数据到 ERP 物料及 BOM 导入行的纯转换逻辑。"""


MATERIAL_COLUMNS = [
    '快捷码', '品号', '品名', '规格', '图号', '备注', '库存单位', '品号描述', '品号群组', '批号管理',
    '批号编码规则', '生产工厂', '品号类型', '出入仓库', '默认销售域', '默认采购域', '工作中心', '生产部门', '批号管理',
    '制造固定前置天数', '制造变动前置天数', '前置天数计算批量', '工单单据类型', '请购单单据类型', '补货政策',
    '最小补量', '补货倍量', '合并开单', '并单周期', '默认调出工厂', '协同关系',
    '采购域', '采购税分类', '采购人员', '供应策略', '最低补量', '采购倍量', '采购固定前置天数',
    '采购变动前置天数', '批量', '销售域', '销售税分类', '默认发货工厂', '公司', '存货会计分类', '存货成本分类',
]

BOM_COLUMNS = [
    '工厂', '主件品号', '标准批量', '元件品号', '组成用量', '底数', '固定损耗量', '变动损耗', '工艺', '超领率',
    '缺领率', '供料方式', '插件位置',
]


def build_erp_data(columns, table_data):
    """将 PDM 数据按物料模板列顺序提取为 ERP 物料导入行。"""
    result = []
    for row in table_data:
        material_item = []
        for col_name in MATERIAL_COLUMNS:
            if col_name in columns and col_name != '工作中心' and col_name != '生产部门':
                idx = columns.index(col_name)
                material_item.append(row[idx])
            elif col_name == '工单单据类型':
                material_item.append(5101)
            elif col_name == '请购单单据类型':
                material_item.append(3101)
            elif col_name == '工作中心':
                material_item.append(1001)
            elif col_name == '生产部门':
                material_item.append(100802)
            else:
                material_item.append('')
        result.append(material_item)
    return result


def build_bom_data(columns, table_data, total_level):
    """根据 PDM 层级结构构建 BOM 导入行。"""
    code_idx  = columns.index('品号')  if '品号'  in columns else 0
    level_idx = columns.index('层次')  if '层次'  in columns else -1
    count_idx = columns.index('数量')  if '数量'  in columns else -1

    def get_depth(row):
        val = row[level_idx] if level_idx >= 0 else ''
        return len(str(val).split('.'))

    dict_bom = {}
    for depth in range(1, total_level + 1):
        for ri in range(len(table_data)):
            row = table_data[ri]
            if get_depth(row) != depth:
                continue
            code = row[code_idx]
            for nj in range(ri + 1, len(table_data)):
                next_row = table_data[nj]
                next_depth = get_depth(next_row)
                if next_depth <= depth:
                    break
                if next_depth == depth + 1:
                    next_code = next_row[code_idx]
                    raw_count = next_row[count_idx] if count_idx >= 0 else 1
                    try:
                        qty = int(float(raw_count)) if raw_count else 1
                    except (ValueError, TypeError):
                        qty = 1
                    bom_row = []
                    for col_name in BOM_COLUMNS:
                        if col_name == '工厂':
                            bom_row.append(100)
                        elif col_name == '主件品号':
                            bom_row.append(code)
                        elif col_name == '标准批量':
                            bom_row.append(1)
                        elif col_name == '元件品号':
                            bom_row.append(next_code)
                        elif col_name == '组成用量':
                            bom_row.append(qty)
                        elif col_name == '底数':
                            bom_row.append(1)
                        elif col_name == '供料方式':
                            bom_row.append(1)
                        else:
                            bom_row.append('')
                    dict_bom.setdefault(code, []).append(bom_row)
    result = []
    for key in dict_bom:
        result.extend(dict_bom[key])
    return result
