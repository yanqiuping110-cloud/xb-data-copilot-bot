# 报告分析 · 背景图资源说明

请将封面/结尾样例背景图放在本目录下对应子文件夹中。

## 目录结构

```text
backgrounds/
├── cover/     ← 封面背景（A4 竖版首页）
└── ending/    ← 结尾背景（A4 竖版感谢页）
```

## 推荐规格（A4 竖版）

| 项 | 值 |
|----|-----|
| 画幅比例 | **A4 竖版**（宽:高 ≈ **1:1.414**，即 210×297mm） |
| 分辨率（打印清晰） | **2480 × 3508**（300 DPI） |
| 分辨率（体积适中） | **1240 × 1754**（150 DPI，开发/预览够用） |
| 格式 | JPG（推荐）或 PNG |
| 单文件大小 | &lt; 2MB（1240 宽度）/ &lt; 3MB（2480 宽度） |

## 命名建议

- 封面：`cover-sport-01.jpg`、`cover-tech-02.jpg`
- 结尾：`ending-light-01.jpg`、`ending-road-02.jpg`

## 构图建议

### 封面（竖版）
- 全页铺底图，画面主体可偏**下半部或中部**（人物/场景/光效）
- **中上区留白**叠主标题；**中下或底部**放汇报单位、日期
- 标题区避免压在复杂纹理上，可加半透明遮罩（模板 CSS 处理）

### 结尾（竖版）
- 全页铺底图，**垂直居中**放「感谢聆听」
- 其下 2～4 句结语；底部可保留装饰图形（光路、城市线等）

### 从横版样例改竖版时
- 横版「左图右文」可改为竖版「上图下文」或「全底图 + 居中标题」
- 不必保留右侧 40% 留白规则

## API 引用方式

```json
{
  "options": {
    "coverBackground": "cover/cover-sport-01.jpg",
    "endingBackground": "ending/ending-light-01.jpg",
    "pageLayout": "a4-portrait"
  }
}
```

## 默认配置

见 `backend/app/brief_report/themes/presentation.yaml` 中的 `defaultCover` / `defaultEnding`。
