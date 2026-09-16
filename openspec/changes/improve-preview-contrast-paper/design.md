# 设计

## 真实配对的修复

现有 `.description`、`.content-card p.muted`、`.tea-row .muted`、`input::placeholder` 和按钮状态要从同一份 token 表取色。引擎新增“推荐余量”和“最低硬闸门”两层结果：

- `muted` 同时对 `bg` 与 `surface` 以 `5.5:1` 选候选；交接仍记录 `4.5:1` 最低线，未达到最低线才进入 `fail`。
- `border_strong` 对 `bg` 与 `surface` 以 `3.5:1` 选候选；`ring` 保持相邻背景至少 `3:1`。候选不足时保留安全回落并把限制写入 `issues`，不静默换掉已选三色。
- `_verify` 增加 `recommended`、`warnings` 和未四舍五入的 `actual`，使“合格”和“有余量”在交接里可分别复核。
- 预览生成器明确标注选择器、背景和实测比值，浏览器端用 `getComputedStyle` 读取最终前景、背景、placeholder、边框和焦点颜色，回归脚本复用同一套计算方法。

## 古纸视觉层

采用“古籍书页”而不是把页面整体染成旧黄：

1. `.demo` 仍使用已选 `bg`，加一层来自 `--color-text-rgb` 与 `--color-border-rgb` 的低透明度 `repeating-linear-gradient`，模拟极细纸纤维与压纹。
2. 纹理通过 `::before` 放在背景层，内容包在相对定位的前景层，`pointer-events: none`；纹理透明度上限 `0.08`，避免改变任何对比度配对。
3. 以 `border` / `border_strong` 画内页边和左侧装帧线，使用 `box-shadow` 做很轻的纸边起伏；不引入阴影黑或任意灰。
4. 导航旁增加一个小型“印”字印章，背景使用现有 `accent`，字使用 `accent_fg`，面积计入 accent 预算；印章只作装饰并标记 `aria-hidden="true"`，不承担信息。
5. 纸纹默认只在 `media=ui` 的预览展示，交接用 `material.paper` 描述实现方式、透明度上限、`must_not` 和面积计费；下游不被强制把纹理带进所有产品。

## 保持色库唯一真源

所有可见颜色继续来自 `references/colors.json` 产出的 token。透明层只引用这些 token 的 RGB 自定义属性；不写新 hex、不用纯黑或纯白、不把 success/warning/error/info 当装饰色。印章借用已有 accent，因此不增加第四种颜色。

## 验证矩阵

| 视图 | 需要检查 |
| --- | --- |
| 默认浅色 | 正文、卡片说明、placeholder、三种按钮状态、输入轮廓、焦点环 |
| 青花浅色 | 蓝色导航、纸纹与卡片说明的实际配对 |
| 水墨深色 | 深底纹理透明度、白字按钮和焦点环 |
| 360px | 纸纹不造成横向溢出，印章和装帧线不遮挡内容 |

装饰层不能被当作文字背景参与配对；验证会同时确认其不改变元素的计算背景色和不拦截指针／键盘操作。
