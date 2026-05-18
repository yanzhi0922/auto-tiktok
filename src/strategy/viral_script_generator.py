# -*- coding: utf-8 -*-
"""
TikTok 爆款脚本生成器
基于 M2.7 模型，生成具有完整爆款结构的视频脚本
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


# 抖音爆款脚本文案模板（用于 Prompt 构建）
TIKTOK_SCRIPT_EXAMPLES = """
【示例1 - 生活技巧类】
主题：白鞋洗白技巧
类型：生活技巧

【开头 - 必须在前3秒抓住注意力】
「盆友，你还在用牙膏刷白鞋吗？试试这个方法，3分钟白鞋焕然一新！」

【核心内容 - 递进式展示，每5秒一个小高潮】
① 先用温水+白醋打湿脏的地方（5秒）
② 挤一点洗洁精，用旧牙刷顺着纹路刷（8秒）
③ 关键来了——撒点小苏打，套上塑料袋晒2小时（6秒）
④ 拆开冲洗干净，见证奇迹！（5秒）

【结尾 - 强烈行动号召】
「觉得有用就点个赞，关注我，每天一个生活小技巧！」

【话题标签】
#白鞋 #洗鞋技巧 #生活小妙招 #实用生活 #清洁妙招

---

【示例2 - 情感共鸣类】
主题：成年人的崩溃
类型：情感共鸣

【开头 - 情感共鸣型】
「那天加班到凌晨2点，我一个人在空荡荡的办公室，突然就哭了……」

【核心内容 - 讲故事，有起承转合】
① 那天加班改第12版方案（情绪铺垫，5秒）
② 手机还剩1%，没人发消息给我（低落情绪，5秒）
③ 走出公司，外面下起了大雨（情绪转折，5秒）
④ 突然收到妈妈一条语音："儿子，早点回家"（情绪爆发，5秒）

【结尾 - 治愈性收尾 + 互动引导】
「成年人的世界没有容易二字，但你不是一个人。评论区告诉我，你最近一次崩溃是什么时候？」

【话题标签】
#情感共鸣 #治愈 #成年人 #深夜emo #扎心语录 #深夜话题

---

【示例3 - 知识科普类】
主题：身份证隐藏信息
类型：知识科普

【开头 - 震惊好奇型】
「身份证上这个数字，竟然能看出你的出生地！大多数人都不知道……」

【核心内容 - 揭秘式，每句话留悬念】
① 前6位是你的地址码，代表省市区（科普，5秒）
② 第7到14位才是你的出生日期（揭秘，5秒）
③ 但最关键的是最后4位——很多人不知道的秘密（悬念，5秒）

【结尾 - 知识收尾 + 互动】
「现在你知道身份证的秘密了吗？转发给家人看看他们都知不知道！」

【话题标签】
#冷知识 #身份证 #科普 #涨知识 #知识科普 #实用
"""


# 视频生成 Prompt 的英文描述模板（给 Hailuo-2.3 用）
VIDEO_PROMPT_TEMPLATES = {
    "生活技巧": (
        "Close-up of hands demonstrating {action}, "
        "bright clean kitchen background, natural lighting, "
        "cinematic smooth camera push-in, "
        "warm tones, ultra detailed, 4K"
    ),
    "情感共鸣": (
        "Emotional portrait scene, "
        "single person in soft lighting atmosphere, "
        "rain window background or lonely office at night, "
        "cinematic slow motion, emotional mood, "
        "shallow depth of field, film grain, 4K"
    ),
    "知识科普": (
        "Modern clean studio background, "
        "floating text or data visualization graphics, "
        "blue tech color scheme, "
        "smooth camera pan, professional lighting, "
        "ultra sharp, 4K"
    ),
    "娱乐搞笑": (
        "Fun dynamic scene, "
        "bright colorful background, "
        "comedic expression and action timing, "
        "quick cuts montage style, "
        "playful music visual rhythm, 4K"
    ),
    "美食探店": (
        "Gourmet food close-up, "
        "steam rising, appetizing shallow depth, "
        "cozy restaurant warm lighting, "
        "gimbal smooth tracking shot, "
        "golden hour tones, 4K"
    ),
    "旅行vlog": (
        "Breathtaking travel scenery, "
        "golden sunset or blue hour city lights, "
        "wide establishing shot transitioning to detail, "
        "aerial drone perspective, "
        "cinematic color grading, 4K"
    ),
    "萌宠日常": (
        "Cute pet close-up, "
        "soft natural lighting, "
        "adorable expression timing, "
        "shallow depth of field, "
        "warm cozy background, 4K"
    ),
}

CAMERA_MOVEMENTS = [
    "smooth push-in",
    "slow pull-back",
    "gentle pan left",
    "gentle pan right",
    "tracking shot",
    "static wide shot",
    "low angle tilt up",
    "top-down overhead view",
    "shallow DOF close-up",
    "rack focus",
]


class ViralScriptGenerator:
    """
    TikTok 爆款脚本生成器

    核心逻辑：
    1. 构建一个极详细的 Prompt，让 M2.7 生成有情感弧线的完整脚本
    2. 脚本包含：开头(hook) → 铺垫 → 冲突/展示 → 转折 → 收尾/CTA
    3. 每个段落标注时长，方便后续字幕对齐
    4. 生成高质量英文视频描述，用于 Hailuo-2.3
    """

    # 爆款开头类型（影响开头句的写法）
    HOOK_TYPES = {
        "curiosity": "好奇心驱动 - 引发好奇，让用户忍不住看下去",
        "shock": "震惊型 - 颠覆认知，引发强烈情绪",
        "practical": "实用型 - 承诺价值，让用户觉得有用",
        "empathy": "共情型 - 说出用户心声，建立情感连接",
        "mystery": "悬念型 - 留有悬念，让用户想知道结果",
        "conflict": "冲突型 - 制造对立，引发讨论",
    }
    CONTENT_TYPE_HOOK_PRIORITY = {
        "生活技巧": ["practical", "curiosity", "shock"],
        "情感共鸣": ["empathy", "mystery", "conflict"],
        "知识科普": ["curiosity", "shock", "mystery"],
        "娱乐搞笑": ["conflict", "shock", "curiosity"],
        "美食探店": ["shock", "curiosity", "practical"],
        "旅行vlog": ["mystery", "curiosity", "empathy"],
        "萌宠日常": ["empathy", "curiosity", "shock"],
    }

    def __init__(self, text_api):
        """
        Args:
            text_api: TextAPI 实例（用于调用 M2.7）
        """
        self.text_api = text_api

    def generate(
        self,
        topic: str,
        content_type: str = "生活技巧",
        duration: int = 6,
        hook_type: str = "curiosity",
        target_audience: str = "18-35岁年轻人",
    ) -> Dict[str, Any]:
        """
        生成完整爆款脚本

        Args:
            topic: 内容主题
            content_type: 内容类型（7种之一）
            duration: 视频时长（6或10秒）
            hook_type: 开头类型
            target_audience: 目标受众

        Returns:
            包含完整脚本数据的字典
        """
        logger.info(f"生成爆款脚本: {topic} ({content_type}) hook={hook_type}")

        # 构建生成 Prompt
        prompt = self._build_script_prompt(
            topic=topic,
            content_type=content_type,
            duration=duration,
            hook_type=hook_type,
            target_audience=target_audience,
        )

        # 调用 M2.7 生成
        result = self.text_api.generate_text(
            prompt=prompt,
            system_prompt=(
                "你是一位顶级短视频编剧，精通抖音算法和爆款内容创作。"
                "你深度理解以下概念：完播率、互动率、点赞/评论/转发/关注的引导技巧。"
                "你的脚本必须：有画面感、有节奏感、有情绪张力。"
                "请严格按照指定格式输出，不要添加任何解释。"
            ),
            temperature=0.85,
            max_tokens=1200,
        )

        # 解析结果
        parsed = self._parse_script(result, topic, content_type, duration)
        return parsed

    def generate_batch(
        self,
        topics: List[Dict[str, str]],
        duration: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        批量生成多个脚本（不同开头类型增加多样性）

        Args:
            topics: 主题列表，每项包含 topic 和 content_type
            duration: 视频时长

        Returns:
            脚本列表
        """
        hook_types = list(self.HOOK_TYPES.keys())
        scripts = []

        for i, item in enumerate(topics):
            hook_type = hook_types[i % len(hook_types)]
            script = self.generate(
                topic=item["topic"],
                content_type=item.get("content_type", "生活技巧"),
                duration=duration,
                hook_type=hook_type,
            )
            scripts.append(script)

        return scripts

    def get_hook_sequence(self, content_type: str, max_attempts: int = 3) -> List[str]:
        preferred_hooks = self.CONTENT_TYPE_HOOK_PRIORITY.get(
            content_type,
            ["curiosity", "shock", "practical"],
        )
        ordered_hooks: List[str] = []
        for hook in preferred_hooks + list(self.HOOK_TYPES.keys()):
            if hook in self.HOOK_TYPES and hook not in ordered_hooks:
                ordered_hooks.append(hook)
        return ordered_hooks[: max(1, max_attempts)]

    def _build_script_prompt(
        self,
        topic: str,
        content_type: str,
        duration: int,
        hook_type: str,
        target_audience: str,
    ) -> str:
        """构建生成脚本的 Prompt"""

        hook_desc = self.HOOK_TYPES.get(hook_type, "好奇心驱动")

        # 时长分配（6秒 vs 10秒）
        if duration == 6:
            segment_guide = """
· 第0-1秒：黄金开头，必须立刻抓住注意力（{}）
· 第1-4秒：核心内容展示，要有节奏感，每句话留钩子
· 第4-5秒：情绪最高点或转折
· 第5-6秒：快速收尾 + 行动号召（CTA）
            """.format(hook_desc)
        else:  # 10秒
            segment_guide = """
· 第0-1秒：黄金开头，必须立刻抓住注意力（{}）
· 第1-3秒：背景铺垫，建立场景
· 第3-6秒：核心内容展示，要有起承转合
· 第6-8秒：情绪最高点或反转
· 第8-10秒：收尾 + 行动号召（CTA）
            """.format(hook_desc)

        prompt = f"""你是一位精通抖音爆款内容的顶级编剧。

请为以下主题创作一个短视频脚本：

主题：{topic}
类型：{content_type}
时长：{duration}秒
目标受众：{target_audience}
开头风格：{hook_desc}

{segment_guide}

参考优秀脚本结构：
{TIKTOK_SCRIPT_EXAMPLES}

输出要求（严格按以下格式，每一项都不能省略）：

【黄金开头】
（这里写开头第一句话，必须在前3秒产生强烈吸引力，直接开始说，不要"大家好"等铺垫）

【旁白全文】
（这里写完整的旁白文案，要求：口语化、有停顿感、有节奏感、中文、直接可用作语音合成。总字数控制在 {duration * 12} 字以内）

【核心画面描述】
（这里用英文写3-5个具体的视频镜头描述，每个描述要包含：主体动作、环境细节、光线氛围、运镜方式。用句号分隔。例如：Close-up of hands scrubbing white shoes in soapy water. Soft natural lighting from window. Slow push-in camera movement.）

【互动引导文案】
（写一句引导评论的话，要具体、和内容相关，不要泛泛的"评论区告诉我"）

【行动号召文案】
（写一句引导点赞/关注的话，要有感染力）

【话题标签】
（5-8个相关话题标签，格式：#标签名）

注意：
1. 旁白文案要像人在说话，不要像写文章
2. 画面描述必须全部用英文，要具体、有画面感
3. 开头第一句必须有冲击力，让人忍不住看完
4. 不要在开头说"今天给大家分享"、"今天教大家"这类废话
5. 标签要精准，不要泛用#抖音 #视频这类大而空的标签"""

        return prompt

    def _parse_script(
        self,
        raw_result: str,
        topic: str,
        content_type: str,
        duration: int,
    ) -> Dict[str, Any]:
        """解析 M2.7 返回的原始文本"""
        import re

        result = {
            "topic": topic,
            "content_type": content_type,
            "duration": duration,
            "raw_content": raw_result,
            "hook": "",
            "narration": "",
            "video_description": "",
            "engagement_question": "",
            "cta": "",
            "hashtags": [],
        }

        # 用正则提取各段落
        patterns = {
            "hook": r"【黄金开头】\s*\n*(.*?)(?=\n【|$)",
            "narration": r"【旁白全文】\s*\n*(.*?)(?=\n【|$)",
            "video_description": r"【核心画面描述】\s*\n*(.*?)(?=\n【|$)",
            "engagement_question": r"【互动引导文案】\s*\n*(.*?)(?=\n【|$)",
            "cta": r"【行动号召文案】\s*\n*(.*?)(?=\n【|$)",
            "hashtags": r"【话题标签】\s*\n*(.*?)(?=\n\n|$)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, raw_result, re.DOTALL)
            if match:
                value = match.group(1).strip()
                if key == "hashtags":
                    # 提取话题标签
                    tags = re.findall(r"#[\w\u4e00-\u9fff]+", value)
                    result["hashtags"] = tags[:8]
                else:
                    result[key] = value

        # 清理旁白中的语气词标签（如笑声等），避免 TTS 误读
        result["narration"] = re.sub(r"\([^)]*\)", "", result["narration"]).strip()

        # 生成视频描述（确保英文、有画面感）
        if not result["video_description"] or len(result["video_description"]) < 20:
            result["video_description"] = self._generate_fallback_video_desc(
                topic, content_type
            )

        # 验证质量
        result["quality_warnings"] = []
        if len(result.get("narration", "")) < 10:
            result["quality_warnings"].append("旁白内容过短")
        if not result["hashtags"]:
            result["quality_warnings"].append("缺少话题标签")

        logger.info(
            f"脚本解析完成: hook={result['hook'][:20]}..., hashtags={len(result['hashtags'])}"
        )

        return result

    def _generate_fallback_video_desc(self, topic: str, content_type: str) -> str:
        """当解析失败时，生成一个基本可用的英文视频描述"""
        template = VIDEO_PROMPT_TEMPLATES.get(
            content_type,
            "Dynamic scene about {topic}, cinematic style, natural lighting, 4K",
        )
        camera = CAMERA_MOVEMENTS[0]
        return (
            template.format(action=topic, topic=topic) + f", {camera} camera movement"
        )

    def calculate_content_score(self, script: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算脚本爆款潜力评分（比 DouyinStrategy 更严格）

        抖音爆款内容的关键数据指标：
        - 完播率：前3秒决定命运
        - 互动率：点赞/评论/转发
        - 关注转化：看完是否关注
        """
        score = 0
        reasons = []
        warnings = []

        # ── 开头评分（最高35分）─────────────────────────────
        hook = script.get("hook", "")
        hook_len = len(hook)

        if hook_len == 0:
            score += 0
            warnings.append("❌ 缺少开头")
        elif hook_len <= 15:
            score += 35
            reasons.append("✅ 开头极短有力（前3秒杀手级）")
        elif hook_len <= 25:
            score += 28
            reasons.append("✅ 开头简洁有力")
        elif hook_len <= 40:
            score += 18
            reasons.append("⚠️ 开头略长，建议精简")
            warnings.append("开头超过25字，影响完播率")
        else:
            score += 8
            reasons.append("❌ 开头过长，完播率风险高")
            warnings.append("开头超过40字，完播率会显著下降")

        # 开头质量检查
        weak_openers = ["今天", "大家好", "我来", "给大家", "分享", "教你", "这个视频"]
        if any(hook.startswith(w) for w in weak_openers):
            score -= 10
            warnings.append("❌ 开头使用了无效铺垫语（大家好/今天教大家等）")

        # ── 互动引导评分（最高25分）─────────────────────────
        eq = script.get("engagement_question", "")
        if eq and len(eq) > 5:
            score += 25
            reasons.append("✅ 有具体互动引导（引发评论）")
            # 检查是否具体
            generic_q = ["你怎么看", "你们觉得", "评论区", "告诉我"]
            if any(q in eq for q in generic_q) and len(eq) < 15:
                score -= 5
                reasons.append("⚠️ 互动问题稍显泛泛，建议更具体")
        else:
            score += 0
            warnings.append("❌ 缺少互动引导")

        # ── CTA 评分（最高20分）───────────────────────────
        cta = script.get("cta", "")
        if cta and len(cta) > 5:
            score += 20
            reasons.append("✅ 有明确行动号召")
        else:
            score += 0
            warnings.append("⚠️ 缺少行动号召")

        # ── 话题标签评分（最高10分）────────────────────────
        tags = script.get("hashtags", [])
        if len(tags) >= 5:
            score += 10
            reasons.append(f"✅ 话题标签充足（{len(tags)}个）")
        elif len(tags) >= 3:
            score += 6
            reasons.append(f"⚠️ 话题标签偏少（{len(tags)}个）")
        else:
            score += 0
            warnings.append("❌ 话题标签不足")

        # ── 旁白质量评分（最高10分）────────────────────────
        narration = script.get("narration", "")
        if len(narration) >= 20:
            score += 10
            reasons.append("✅ 旁白内容充实")
        elif len(narration) >= 10:
            score += 5
        else:
            score += 0
            warnings.append("❌ 旁白内容不足")

        # ── 评级 ───────────────────────────────────────────
        if score >= 85:
            level = "S级"
            level_desc = "爆款潜力极高，强烈推荐发布"
        elif score >= 70:
            level = "A级"
            level_desc = "爆款潜力高，建议发布"
        elif score >= 55:
            level = "B级"
            level_desc = "有潜力，可优化后发布"
        elif score >= 40:
            level = "C级"
            level_desc = "需要较大优化"
        else:
            level = "D级"
            level_desc = "不建议发布，需重新生成"

        return {
            "score": min(score, 100),
            "level": level,
            "level_desc": level_desc,
            "reasons": reasons,
            "warnings": warnings,
            "max_score": 100,
        }
