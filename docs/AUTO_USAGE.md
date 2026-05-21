# 自动化使用指南

本文档对应当前代码的**真实自动化行为**。

## 1. 自动化入口

### 立即执行一次

```bash
python auto_scheduler.py --run-now
```

### 指定数量与类型

```bash
python auto_scheduler.py --run-now --count 3 --types 生活技巧,知识科普
```

### 全自动 Autopilot

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
python auto_scheduler.py --run-now --autopilot --count 1 --provider manual
```

Autopilot 会自动选题、生成、评分、修复缺失资产，并在达标后导出发布包；配置 TikTok OAuth 后也可以走官方发布 API。

### 启动内存调度器

```bash
python auto_scheduler.py
```

默认时间来自 `config/auto_config.yaml` 的 `automation.schedule`。

### 安装 Windows 定时任务

```bash
python auto_scheduler.py --install-task --time 09:00 --count 3 --min-score 65
```

### 查看/删除计划任务

```bash
python auto_scheduler.py --list-tasks
python auto_scheduler.py --remove-task
```

## 2. 默认配置来源

自动化默认值来自：

`C:\Users\Yanzh\Desktop\auto-tiktok\config\auto_config.yaml`

当前默认：

- `daily_count: 3`
- `auto_generate_video: true`
- `auto_generate_music: false`
- `auto_generate_thumbnail: true`
- `default_duration: 6`
- `default_voice: female_tianmei`
- `schedule: 0 9 * * *`

## 3. 调度时间格式

`automation.schedule` 现在支持：

```yaml
automation:
  schedule: "09:00"
```

或者：

```yaml
automation:
  schedule: "0 9 * * *"
```

系统会自动解析为每日执行时间。

## 4. 输出结构

自动化任务输出不是旧版平铺目录，而是：

```text
output/
└── YYYY-MM-DD/
    └── run_<run_id>/
        ├── 001/
        ├── 002/
        ├── daily_generation_report.json
        └── run_manifest.json
```

其中：

- 每条内容都会有 `content_manifest.json`
- 每次自动化任务会把 `daily_generation_report.json` 直接写到对应 `run` 根目录

## 5. 评分门槛

自动化支持质量门槛：

```bash
python auto_scheduler.py --run-now --min-score 70
```

低于门槛的内容会被标记为：

- `quality_gate_passed = false`
- 不会进入“达标可发布”列表

## 6. 重要说明

### 普通每日自动化不是自动发布

`auto_scheduler.py --run-now` 的普通模式只负责：

- 生成内容
- 评分
- 保存素材
- 产出报告

如果需要“达标后自动导出发布包/发布”，请使用 `autopilot.py run` 或 `auto_scheduler.py --autopilot`。

### 默认数量为何不是 7？

因为大多数视频套餐每日视频额度有限，默认 `3` 条更安全。  
如果你的套餐足够，可以手动提高：

```bash
python auto_scheduler.py --run-now --count 5
```

### 音乐为什么默认关闭？

因为音乐模型并不一定对当前套餐开放；且很多抖音场景会直接使用平台曲库。

## 7. 排障建议

### 视频模型不支持

如果日志里出现：

```text
API 错误[2061]: your current token plan not support model
```

说明当前套餐不支持当前视频能力。现在系统会按 `Ultra -> Max` 做套餐回退，并把视频规格归一化到 `768P + 6s`；如果两个套餐都失败，需要：

- 关闭视频生成
- 或升级套餐

### Key 无效

如果出现：

```text
API 错误[2049]: invalid api key
```

请检查 `.env` 中的主 Key / 备用 Key。

### 查看自动化日志

日志位于：

```text
logs/YYYY-MM-DD/
```

## 8. 推荐命令

```bash
python auto_scheduler.py --run-now --count 3
python output_manager.py audit --json
python -m pytest -q
```
