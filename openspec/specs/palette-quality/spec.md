# palette-quality Specification

## Purpose
TBD - created by archiving change improve-palette-coherence. Update Purpose after archive.

## Requirements

### Requirement: 同一方案交付颜色一致

系统 MUST 在文字说明、预览、CSS 与交接数据中保持已选三色一致，且 MUST 保留场景明确允许的强调色破色。

#### Scenario: 江南允许小面积红色
- **WHEN** 已选方案为粉白、瓦松绿、苋菜红，场景为江南
- **THEN** 导出的强调色仍为苋菜红，不被场景主色族过滤成绿色
- **AND** 悬停与按下颜色沿用强调色的色相方向

#### Scenario: 用户指定的色不适合某用途
- **WHEN** 用户指定的颜色无法在色库内满足普通文字对比要求
- **THEN** 系统保留该颜色并报告用途限制，不将不达标配对标记为通过，也不静默换掉指定颜色

### Requirement: 检查真实组件背景

系统 MUST 对正文、说明文字、按钮默认及交互状态的实际背景检查至少 4.5:1；必要的输入轮廓与焦点指示 MUST 对页面与卡片背景检查至少 3:1。判断 MUST 使用未四舍五入的计算值。

#### Scenario: 卡片说明文字
- **WHEN** 生成青花或宋瓷 UI 并在 surface 上显示 muted 文字
- **THEN** muted 同时对 bg 与 surface 达到 4.5:1

#### Scenario: 按钮悬停与按下
- **WHEN** 按钮沿用 accent_fg 并切换到 accent_hover 或 accent_active
- **THEN** 同一个 accent_fg 在每种状态背景上都达到 4.5:1

#### Scenario: 卡片内输入和焦点
- **WHEN** 输入框或焦点轮廓显示在 bg 或 surface 上
- **THEN** 对应 border_strong 或 ring 相对其相邻背景达到 3:1

#### Scenario: 亮暗主题均接受验证
- **WHEN** 交接文件同时导出浅色与深色主题
- **THEN** 两套实际导出的颜色均执行相同配对检查，并报告各自的问题

### Requirement: 派生颜色保持连贯

系统 MUST 为素雅 UI 优先选择连贯的中性色面层、低彩说明文字和同色相交互状态；不得为了让每个 token 都不同而引入无关色相。

#### Scenario: 库内无安全交互变体
- **WHEN** 强调色在色库中找不到同时满足色相连续性与文字对比的不同变体
- **THEN** 沿用安全颜色，并通过其他已有交互提示区分状态，而不是输出不合格或跳色的变体

#### Scenario: 普通卡片与显式浓烈主题
- **WHEN** 用户要求普通、素雅或阅读型界面
- **THEN** 普通内容卡片使用中性面层，有彩区域有明确的主次与用途，状态色不充当装饰
- **AND** 用户明确要求的浓烈或多彩主题仍按其主题处理

### Requirement: 可复核的配色交付

技能 MUST 审核脚本结果后交付，并通过已有预览展示实际文字、卡片、输入及按钮状态；前端交接 MUST 包含实际使用的前景与背景配对。

#### Scenario: 从色卡进入前端实现
- **WHEN** 下游将一套配色应用于 UI
- **THEN** 下游可以读取背景、面层、文字、彩色块上的文字和按钮状态的完整配对及校验结果
- **AND** 预览与交接使用同一套最终颜色
