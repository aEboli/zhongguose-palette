# 出处

## 色值

526 色的名称、拼音、hex、RGB、CMYK 来自 [中国色 zhongguose.com](https://zhongguose.com/) 的 `colors.json`（抓取副本：`references/source.json`）。网站说明：中国传统颜色的名称与色值，可用于设计参考。

本技能对原始数据做了这些处理，**没有改 hex**：

- 8 条记录的 RGB 字段与 hex 不一致，以 hex 为准，原始 RGB 留在 `rgb_source`
- 7 组拼音重复，输出用的 `pinyin` 加了数字后缀，原始拼音在 `pinyin_source`
- 补了 LCH、对比度、五行、四季、角色等计算字段，算法见 `scripts/`

网站作者署名为 Perchouli。色名本身是对中国传统色彩的整理，属事实性数据。若在产品里展示色名，建议同时注明「色值来自 zhongguose.com」。

## 文学色名

`references/aliases.json` 里的典故释义参考了网络流传的约 161 色文学色卡（常见于 [zerosoul/chinese-colors](https://github.com/zerosoul/chinese-colors)，其 README 指向新浪博客《中国传统颜色》一文）。这些 hex **只作典故，不作为本技能的输出**。若干条（尤其是「石青」）与矿物颜料本义不符，已在别名表里文化校正。

## 配色口诀与理论

- 三色层级配色法：室内设计与穿搭里通行的做法，主场 / 结构 / 点缀视觉分量依次递减
- 荆浩「红间黄秋叶坠，红间绿花簇簇，青间紫不如死，粉笼黄胜增光」
- 《考工记》五色、后素功、钟氏染羽
- WCAG 2.2 对比度；APCA 仅作感知参考
- CIEDE2000（Sharma 测试集）、CIELAB D65

## 本技能

分类、评分、手选方案、脚本与文档由本技能编写。手选方案是对故宫、青花、水墨等既有视觉传统的归纳，不是官方色票。
