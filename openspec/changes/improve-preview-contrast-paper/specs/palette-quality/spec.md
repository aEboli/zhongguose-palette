## ADDED Requirements

### Requirement: 预览使用真实选择器复核对比度

系统 MUST 对预览最终计算样式中的正文、说明文字、placeholder、卡片文字、按钮默认／悬停／按下、输入轮廓和焦点环逐项复核；复核必须使用预览与交接共用的最终 tokens，不得只检查抽象 token 配对。

#### Scenario: 卡片辅助文字有视觉余量
- **WHEN** 浅色 UI 在 `surface` 上渲染 `muted` 文字或 placeholder
- **THEN** 普通文字至少达到 `4.5:1`，候选选择优先达到 `5.5:1`
- **AND** 预览报告选择器、最终前景、最终背景和未四舍五入的比值

#### Scenario: 输入边框不是数学临界线
- **WHEN** 输入框出现在页面或卡片中
- **THEN** `border_strong` 优先达到 `3.5:1`，最低不得低于 `3:1`
- **AND** 焦点环对两个相邻背景均不得低于 `3:1`

### Requirement: 古纸层不影响内容可读性

系统 MUST 支持在 UI 预览中展示低透明度纸纹、页边装帧线和小型印章；装饰 MUST 使用现有 CSS 颜色变量，位于非交互背景层，且不能覆盖或改变正文、按钮、输入和焦点的配对。

#### Scenario: 纸纹只在背景层
- **WHEN** 预览启用古纸效果
- **THEN** 纸纹通过伪元素或等效背景层渲染，`pointer-events: none`，透明度不超过 `0.08`
- **AND** 内容层保持可选中、可聚焦，浏览器最终计算的文字和控件颜色仍来自交接 tokens

#### Scenario: 印章遵守面积与色库限制
- **WHEN** 预览显示印章或装帧线
- **THEN** 印章借用已有 `accent` / `accent_fg`，装帧线借用已有 `border` / `border_strong`
- **AND** 印章计入 accent 面积预算，不引入任意 hex 或第四种装饰色
