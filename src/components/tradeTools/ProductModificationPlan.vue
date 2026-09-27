<script setup>
// ── 说明 ──────────────────────────────────────────
// 产品改制「方案讨论稿」：功能尚未开发，先把方案放在外贸工具里，
// 方便和外贸、研发一起确认流程是否可行（2026-09-27）。纯展示，无接口调用。
// 读者是业务同事，文案避免表名/接口等技术细节。

// ── 流程步骤 ──────────────────────────────────────
const STEPS = [
  { who: '外贸', title: '提改制申请', desc: '选内销基准产品，逐项过一遍改制提醒清单，在 BOM 上标出要改的内容；可和研发在线沟通' },
  { who: '系统', title: '生成清单', desc: '定稿后自动生成改制申请清单（Excel）' },
  { who: '外贸', title: '走 OA 审批', desc: '用清单走 OA；审批完在系统里标记通过、填 OA 单号' },
  { who: '研发文员', title: '建码', desc: '按清单在研发系统创建外贸成品号（及需要新码的部件）' },
  { who: '研发文员', title: '生成改制 BOM', desc: '把新编码填回系统，生成改制 BOM，可查询管理' },
  { who: '任何人', title: '导出 ERP', desc: '导出与「PDM转BOM」一致的 BOM 文件，直接录入 ERP' },
]

// ── 改动类型 ──────────────────────────────────────
const CHANGE_TYPES = [
  { op: '删除', top: '可以', inner: '可以（它的上级部件要新建编码）' },
  { op: '新增', top: '可以', inner: '不可以，一律加到最外层' },
  { op: '增加数量', top: '可以', inner: '不改部件内部，在最外层新增差额（如内部螺钉 4→6，最外层加 2 个）' },
  { op: '替换', top: '可以', inner: '拆成两步：内部删除旧物料 + 最外层新增新物料' },
  { op: '文字需求', top: '可以', inner: '可以；研发落实时同样遵守上面的规则' },
]

// ── 状态 ──────────────────────────────────────────
const STATUSES = [
  { name: '草稿', who: '外贸', can: '标改动、写文字需求；研发可查看、逐条留言' },
  { name: '已定稿', who: '外贸', can: '提醒清单每一项都已答复才能定稿；改动锁定，生成清单（Excel）拿去走 OA' },
  { name: 'OA 审批中', who: '外贸 / 研发文员', can: '系统不接 OA，手动标记「通过」并填 OA 单号；驳回则回到草稿' },
  { name: '待建码', who: '研发文员', can: '在研发系统建码后，把新编码填到清单列出的每个节点' },
  { name: '已生效', who: '—', can: '改制 BOM 挂在外贸成品号上，物料库可查，可导出 ERP 文件' },
]

// ── 「哪些部件需要新建编码」示例：depth 为层级缩进，kind 决定行颜色 ──
const NEW_CODE_EXAMPLE = [
  { depth: 0, node: '外贸成品（基于 1108SG07-A01）', note: '要新码（外贸成品号）', kind: 'new' },
  { depth: 1, node: '1208SGZM07-A01 产成品·桌面', note: '要新码（下级删了东西）', kind: 'new' },
  { depth: 2, node: '14PA…… 包装', note: '要新码（下级删了东西）', kind: 'new' },
  { depth: 3, node: '中文说明书', note: '删除', kind: 'del' },
  { depth: 1, node: '钢架（内部螺钉 4 个不动）', note: '沿用原编码', kind: 'keep' },
  { depth: 1, node: '英文说明书 ×1', note: '最外层新增（替换的另一半）', kind: 'add' },
  { depth: 1, node: '螺钉 ×2', note: '最外层新增（增加的差额）', kind: 'add' },
]

// ── 改制提醒清单：示例条目（实际内容由维护人自行增删改）──
const REMINDER_EXAMPLES = [
  { group: '电气', item: '电源插头 / 电压', hint: '目标市场插头制式、电压频率是否与内销不同' },
  { group: '电气', item: '认证标识', hint: 'CE / UL / FCC 等标识、铭牌内容' },
  { group: '文字资料', item: '说明书语言', hint: '是否需要英文或其他语言版本' },
  { group: '文字资料', item: '标签 / 警示贴', hint: '产品标签、警示贴、条码是否需要替换' },
  { group: '包装', item: '外箱唛头', hint: '唛头、客户 LOGO、箱规是否变化' },
  { group: '包装', item: '包装方式', hint: '是否需要加强包装（海运跌落）' },
  { group: '外观', item: '颜色 / 材质', hint: '客户是否指定不同颜色或面料' },
  { group: '配件', item: '赠品 / 配件', hint: '是否去掉内销赠品或增加配件' },
]

// ── 待确认问题 ────────────────────────────────────
const QUESTIONS = [
  {
    q: '部件内部的物料能减少数量吗？',
    a: '已定：部件内部只能删除，新增和增量都放最外层。还需确认：内部物料「减少数量」（如 4 个改 2 个）算不算「部分删除」允许做（上级部件同样要新编码），还是只能整行删除？',
  },
  {
    q: '导出 ERP 时导哪些层？',
    a: '建议只导新编码的那几层（没改的部件 ERP 里已有 BOM，不重复导）；也可以像 PDM转BOM 一样整棵树全导。',
  },
  {
    q: '数量要不要保留小数？',
    a: '现在 PDM转BOM 导出会把数量截成整数（2.5 → 2）。改制导出要和它保持一致，还是保留小数？',
  },
  {
    q: '新编码的物料信息由谁进 ERP？',
    a: 'PDM转BOM 还会出一份「ERP 物料导入」文件。改制的新编码在研发系统建好后是否自然进 ERP，还是需要本系统也生成这份文件？',
  },
  {
    q: 'OA 清单用什么格式？',
    a: 'Excel 就够，还是需要 PDF？要不要带产品图？OA 附件有没有固定格式？',
  },
  {
    q: '新增的物料必须是已有编码吗？',
    a: '建议必须是物料表里已有的编码；全新的物料先走研发建码，外贸用「文字需求」说明。',
  },
  {
    q: '改制提醒清单由谁维护？',
    a: '建议由外贸主管（或指定的外贸管理员）维护条目，研发可以提建议；需要一个单独的维护权限。条目是否需要「必答」和「可选」之分？',
  },
  {
    q: '谁能做什么？',
    a: '外贸：建申请、标改动、定稿；研发：留言、落实文字需求；研发文员：填新编码、生成改制 BOM。具体由哪些人/角色承担需要确认。',
  },
]
</script>

<template>
  <div class="plan">
    <!-- 讨论稿提示 -->
    <div class="plan-banner">
      <b>方案讨论稿</b>
      <span>2026-09-27 · 功能尚未开发，先用于和外贸、研发确认流程是否可行。有意见请反馈给系统负责人。</span>
    </div>

    <h1 class="plan-title">产品改制</h1>
    <p class="plan-lead">
      部分外贸产品是在现有内销产品基础上改制而来：有自己的成品编码，但不会录入研发系统。
      现在用表格传递改制内容，外贸对产品不熟、和研发沟通不顺畅。
      本方案把改制申请搬进系统：<b>外贸对着带图片的 BOM 点选要改的地方，系统生成清单走 OA，
      审批后研发文员建码并生成改制 BOM，直接导出可录入 ERP 的文件。</b>
      申请时还会按一份可维护的「改制提醒清单」逐项确认，避免漏改。
    </p>

    <!-- 一、流程 -->
    <section class="plan-sec">
      <h2>一、整体流程</h2>
      <ol class="steps">
        <li v-for="(s, i) in STEPS" :key="i" class="step">
          <div class="step-no">{{ i + 1 }}</div>
          <div class="step-body">
            <div class="step-head"><span class="step-who">{{ s.who }}</span>{{ s.title }}</div>
            <div class="step-desc">{{ s.desc }}</div>
          </div>
        </li>
      </ol>
    </section>

    <!-- 二、状态 -->
    <section class="plan-sec">
      <h2>二、申请的各个状态</h2>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th style="width:110px">状态</th><th style="width:130px">谁操作</th><th>能做什么</th></tr></thead>
          <tbody>
            <tr v-for="st in STATUSES" :key="st.name">
              <td><b>{{ st.name }}</b></td><td>{{ st.who }}</td><td>{{ st.can }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 三、怎么标改动 -->
    <section class="plan-sec">
      <h2>三、外贸怎么标改动</h2>
      <p>
        选好内销基准产品（例如 1108SG07-A01）后，系统展示它的完整 BOM 树，带物料名称和图片，
        外贸不需要认编码。改动规则：<b>部件内部只能删除；新增的物料、增加的数量一律放到最外层。</b>
      </p>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th style="width:100px">操作</th><th style="width:170px">最外层（成品下一级）</th><th>部件内部</th></tr></thead>
          <tbody>
            <tr v-for="c in CHANGE_TYPES" :key="c.op">
              <td><b>{{ c.op }}</b></td><td>{{ c.top }}</td><td>{{ c.inner }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul class="plan-list">
        <li>「文字需求」用于写不出具体编码的情况，比如「电源要适配欧洲」，由研发落实成具体改动。</li>
        <li>替换、新增的物料从物料表里带图片搜索选择；物料表里没有的，写「文字需求」由研发落实。</li>
        <li>在部件内部点「新增」「替换」「增加数量」时，系统自动换成规则里的做法（放到最外层），不用外贸自己判断。</li>
        <li>每条改动可以留言，来回沟通记录留在系统里，不再靠表格和聊天记录。</li>
        <li>系统只记录「基准 + 改动」，改制后的完整 BOM 随时算出来，改了什么一目了然。</li>
      </ul>
    </section>

    <!-- 四、改制提醒清单 -->
    <section class="plan-sec">
      <h2>四、改制提醒清单</h2>
      <p>
        把以往常见的改制内容整理成一份<b>提醒清单</b>，每次提改制申请时逐项确认，避免漏改、少问。
        清单内容可以<b>自行维护</b>（增删改条目、分组、排序、停用），不用找开发改代码。
      </p>
      <ul class="plan-list">
        <li>新建申请时，系统把当前启用的提醒条目全部带出来，外贸对每一项选：<b>需要改 / 不需要 / 待确认</b>。</li>
        <li>选「需要改」时，直接在 BOM 树上标出对应改动，或写文字需求交给研发落实；条目可以预先关联到常见位置（比如「说明书语言」关联到说明书类物料），系统自动帮忙定位。</li>
        <li>每一项都答复完才能定稿；答复结果会一起写进 OA 清单，审批人能看到「哪些项确认过不改」。</li>
        <li>后面维护清单不影响已经提交的申请：每份申请保存的是当时的条目和答复。</li>
      </ul>
      <p class="plan-sub">示例条目（仅示意，实际以维护的内容为准）：</p>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th style="width:90px">分组</th><th style="width:150px">提醒项</th><th>确认要点</th></tr></thead>
          <tbody>
            <tr v-for="r in REMINDER_EXAMPLES" :key="r.item">
              <td>{{ r.group }}</td><td><b>{{ r.item }}</b></td><td>{{ r.hint }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 五、哪些要新建编码 -->
    <section class="plan-sec">
      <h2>五、哪些部件需要新建编码</h2>
      <p>
        内销部件的 BOM 在 ERP 里是和内销产品共用的，不能直接改。因为部件内部只允许删除，
        新增和增量都放在最外层，所以规则很简单：
      </p>
      <ul class="plan-list">
        <li><b>外贸成品本身</b>：总是要新编码（外贸成品号）。</li>
        <li><b>部件</b>：只有内部删过物料的部件，以及它往上的每一层部件，才要新编码。</li>
        <li><b>其余部件</b>（包括只在最外层加了东西、内部没删的）：沿用原编码。</li>
      </ul>
      <p class="plan-sub">例：中文说明书换成英文说明书，钢架里的螺钉从 4 个增加到 6 个。</p>
      <div class="tbl-wrap">
        <table class="tbl code-tbl">
          <thead><tr><th>结构</th><th style="width:220px">说明</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in NEW_CODE_EXAMPLE" :key="i" :class="r.kind">
              <td :style="{ paddingLeft: 10 + r.depth * 22 + 'px' }">{{ r.node }}</td>
              <td>{{ r.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="plan-sub">系统自动列出所有「要新码」的节点写进清单，研发文员照着建码即可。</p>
    </section>

    <!-- 五、导出 -->
    <section class="plan-sec">
      <h2>六、导出 ERP 文件</h2>
      <ul class="plan-list">
        <li>与研发部工具「PDM转BOM」导出的 BOM 文件<b>格式完全一致</b>（同一模板，工厂 100、标准批量 1、底数 1、供料方式 1）。</li>
        <li>主件品号填新编码，元件品号填 ERP 编码。</li>
        <li>导出前检查：所有物料都必须能对应到 ERP 编码，对应不上的会列出来并阻止导出。</li>
      </ul>
    </section>

    <!-- 六、生效后怎么查 -->
    <section class="plan-sec">
      <h2>七、改制 BOM 生效后在哪里查</h2>
      <ul class="plan-list">
        <li>物料库 → 物料卡片：外贸成品号的「BOM下级」里出现「改制 · 基于 1108SG07-A01」，点「查看」看完整结构，改动的行高亮。</li>
        <li>物料库 → 物料BOM：左侧多一个「改制」分类。</li>
        <li>外贸工具 → 产品改制：按状态查看全部申请及历史沟通记录。</li>
        <li>内销基准以后升版时，系统提示「基准已变化，请复核」，不会悄悄算错。</li>
      </ul>
    </section>

    <!-- 七、待确认 -->
    <section class="plan-sec">
      <h2>八、需要确认的问题</h2>
      <div class="qa-list">
        <div v-for="(item, i) in QUESTIONS" :key="i" class="qa">
          <div class="qa-q"><span class="qa-no">{{ i + 1 }}</span>{{ item.q }}</div>
          <div class="qa-a">{{ item.a }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.plan {
  max-width: 920px; margin: 0 auto; padding: 24px 24px 48px;
  color: #3a3028; font-size: 14px; line-height: 1.75;
}
.plan-banner {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
  padding: 10px 14px; margin-bottom: 20px; border-radius: 10px;
  background: #fff8e6; border: 1px solid #f0d48a; color: #8a5a00; font-size: 13px;
}
.plan-banner b { color: #6b4400; }
.plan-title { font-size: 24px; font-weight: 700; color: #2c2420; margin: 0 0 8px; }
.plan-lead { margin: 0 0 8px; color: #3a3028; }
.plan-lead b { color: #2c2420; }

.plan-sec {
  margin-top: 16px; padding: 18px 20px;
  background: #fff; border: 1px solid #e0d4c0; border-radius: 12px;
}
.plan-sec h2 { font-size: 16px; font-weight: 700; color: #2c2420; margin: 0 0 10px; }
.plan-sec p { margin: 0 0 10px; }
.plan-list { margin: 8px 0 0; padding-left: 20px; }
.plan-list li { margin: 2px 0; }
.plan-sub { margin: 12px 0 6px !important; font-size: 13px; color: #6b5e4e; }

/* 流程步骤 */
.steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.step {
  display: flex; gap: 10px; padding: 10px 12px; border-radius: 10px;
  background: #faf7f2; border: 1px solid #e0d4c0;
}
.step-no {
  flex-shrink: 0; width: 26px; height: 26px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #c4883a; color: #fff; font-size: 13px; font-weight: 700;
}
.step-head { font-weight: 700; color: #2c2420; }
.step-who {
  display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 4px;
  font-size: 11px; font-weight: 600; line-height: 18px;
  color: #4a8fc0; background: rgba(74,143,192,0.12);
}
.step-desc { font-size: 13px; color: #6b5e4e; line-height: 1.6; }

/* 表格 */
.tbl-wrap { overflow-x: auto; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th {
  text-align: left; padding: 7px 10px; background: #f5f0e8; color: #6b5e4e;
  font-weight: 600; border-bottom: 1px solid #e0d4c0;
}
.tbl td { padding: 7px 10px; border-bottom: 1px solid #efe7da; vertical-align: top; }
.tbl tr:last-child td { border-bottom: none; }

/* 新建编码示例：行颜色区分 要新码 / 删除 / 新增 / 沿用 */
.code-tbl tr.new td:last-child { color: #c4883a; font-weight: 600; }
.code-tbl tr.del td { color: #d05a3c; }
.code-tbl tr.del td:first-child { text-decoration: line-through; }
.code-tbl tr.add td { color: #4a8f6a; }
.code-tbl tr.keep td { color: #8a7a6a; }

/* 待确认问题 */
.qa-list { display: flex; flex-direction: column; gap: 10px; }
.qa { padding: 10px 12px; border-radius: 10px; background: #faf7f2; border: 1px solid #e0d4c0; }
.qa-q { font-weight: 700; color: #2c2420; display: flex; align-items: center; gap: 8px; }
.qa-no {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: #e0d4c0; color: #3a3028; font-size: 11px;
}
.qa-a { margin-top: 4px; padding-left: 28px; font-size: 13px; color: #6b5e4e; }

@media (max-width: 768px) {
  .plan { padding: 16px 16px 32px; }
  .plan-sec { padding: 14px; }
}
</style>
