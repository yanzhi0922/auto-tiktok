# 抖音内容生成指南 🎵

本指南对应 `douyin_main.py` 与 `src/pipeline/douyin_pipeline.py` 的当前真实行为。

## 1. 这个模块做什么

抖音流水线会在通用素材生成基础上补上：

- 黄金 3 秒开头
- 互动问题与 CTA
- 话题标签
- 爆款潜力评分
- 字幕文件
- 最终成片与封面

它的目标是生成“更适合抖音发布”的内容包。普通 `douyin_main.py` 不会自动发布；如果需要全自动生成并导出发布包/调用发布 API，请使用 `autopilot.py run`。

## 2. 快速开始

### 单条生成

```bash
python douyin_main.py --topic "咖啡文化" --type "生活技巧"
python douyin_main.py --topic "治愈瞬间" --type "情感共鸣"
python douyin_main.py --topic "冷知识" --type "知识科普"
```

### 每日内容

```bash
python douyin_main.py --daily
python douyin_main.py --daily --count 5
```

默认每日数量取自 `config/auto_config.yaml`，当前默认是 `3`。

### 周计划

```bash
python douyin_main.py --weekly
```

## 3. 内容类型

支持：

- `生活技巧`
- `情感共鸣`
- `知识科普`
- `娱乐搞笑`
- `美食探店`
- `旅行vlog`
- `萌宠日常`

## 4. 评分说明

当前评分是**启发式评分**，用于快速筛选，不等于真实平台数据。

主要看：

- 开头吸引力
- CTA 强度
- 互动问题
- 时长是否适合短视频
- 音乐建议是否清晰
- 内容类型是否适合抖音分发

等级大致为：

- `S级`：极强
- `A级`：较强
- `B级`：可发但仍可优化
- `C级`：建议改写
- `D级`：建议重做

相比旧版本，当前评分已不再轻易出现“随手 95/100、100/100”的失真情况。

## 5. 当前默认策略

默认值来自 `config/auto_config.yaml`：

- 每日数量：`3`
- 默认时长：`6`
- 默认音色：`female_tianmei`
- 默认视频：开启
- 默认音乐：关闭
- 默认缩略图：开启

## 6. 视频模型策略

抖音流水线现在严格走 Token Plan 官方支持的视频能力：

1. 优先尝试 `Fast` 图生视频：先生成首帧图，再走 `MiniMax-Hailuo-2.3-Fast`
2. 当 Fast 额度不可用、首帧图不可得或流程不适配时，回退 `MiniMax-Hailuo-2.3` 文生视频
3. 不再默认尝试历史非套餐视频模型

默认应用规格固定为 `768P + 6s`。如果上层请求了更高规格，manifest / report 会保留 `requested/applied` 差异。

现在的错误行为已修正：

- 模型不支持时不会再误切换成 `invalid api key`
- 只有认证失败（`2049/401/403`）才会触发同级鉴权切换
- 配额不足、限流、模型不支持都会按套餐能力处理并保留真实语义

## 7. 字幕与成片

生成顺序大致如下：

1. 生成脚本
2. 生成标题
3. 生成语音
4. 生成视频
5. 生成缩略图
6. 生成字幕
7. 合成最终视频
8. 设置封面

当前字幕会根据**真实音频时长**做语速校准，减少字幕和旁白错位。

## 8. 输出目录

真实输出目录：

```text
output/
└── YYYY-MM-DD/
    └── run_<run_id>/
        ├── 001/
        │   ├── script.json
        │   ├── titles.json
        │   ├── score.json
        │   ├── content_manifest.json
        │   ├── cover.jpg
        │   ├── subtitle.srt
        │   ├── final.mp4 / final_subtitled.mp4
        ├── daily_generation_report.json
        ├── weekly_plan_YYYYMMDD.json
        └── run_manifest.json
```

## 9. 典型命令

### 只做文本 / 语音，不生成视频

```bash
python douyin_main.py --topic "书桌布光技巧" --type "知识科普" --no-video
```

### 指定每日数量

```bash
python douyin_main.py --daily --count 3
```

### 生成计划，不打视频 API

```bash
python douyin_main.py --weekly
```

### 全自动生产与发布包

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
```

## 10. 常见问题

### 为什么每日默认不是 7 条？

因为视频套餐通常有每日上限，默认 `3` 条更稳妥。

### 为什么生成失败但文本和 TTS 额度还是减少了？

因为当前流水线是先生成脚本 / 标题 / TTS，再进入视频链路。  
如果视频模型不支持，前面的文本与语音调用已经真实发生，所以额度会减少。

### 为什么默认不生成音乐？

因为不是所有套餐都支持音乐模型，而且很多抖音发布会直接使用平台曲库。

## 11. 推荐排查命令

```bash
python douyin_main.py --help
python douyin_main.py --weekly
python output_manager.py audit --json
```
