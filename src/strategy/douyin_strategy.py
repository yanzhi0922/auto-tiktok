# -*- coding: utf-8 -*-
"""
抖音内容策略模块
针对抖音平台的特性优化内容生成。
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random


logger = logging.getLogger(__name__)


class DouyinContentStrategy:
    """抖音内容策略类"""
    
    # 抖音黄金3秒法则 - 前3秒决定用户是否继续观看
    HOOK_PATTERNS = [
        "你知道吗？{fact}",
        "我赌你不知道{topic}",
        "震惊！{topic}竟然...",
        "这个{topic}技巧太实用了",
        "90%的人都不知道{topic}",
        "今天教你{topic}的正确姿势",
        "别再{wrong_action}了！正确做法是...",
        "只需3秒，学会{skill}",
        "这个{topic}火了！",
        "终于有人把{topic}说清楚了",
    ]
    
    # 高完播率开头模板
    VIRAL_INTROS = [
        "等等，{topic}还能这样？",
        "我忍不住要分享这个{topic}",
        "这个{topic}太绝了",
        "看完这个{topic}你会回来感谢我",
        "关于{topic}，我只说一次",
        "这个{topic}让我惊呆了",
    ]
    
    # 强行动号召结尾
    CTA_PHRASES = [
        "关注我，每天分享{topic}",
        "点赞收藏，下次用得上",
        "评论区告诉我，你还想看什么",
        "转发给需要的朋友",
        "关注我，下期更精彩",
        "双击屏幕，有惊喜",
        "你的点赞是我更新的动力",
    ]
    
    # 热门话题类型（可扩展）
    TRENDING_TOPICS = {
        "生活技巧": ["省钱妙招", "收纳整理", "厨房技巧", "清洁妙招"],
        "情感共鸣": ["治愈瞬间", "暖心故事", "励志分享", "emo时刻"],
        "知识科普": ["冷知识", "科普一下", "涨知识了", "学到了"],
        "娱乐搞笑": ["沙雕日常", "搞笑瞬间", "神评论", "笑死我了"],
        "美食探店": ["隐藏美食", "网红打卡", "家常菜谱", "美食测评"],
        "旅行vlog": ["小众景点", "穷游攻略", "旅行vlog", "城市探索"],
        "萌宠日常": ["猫咪日常", "狗狗萌态", "宠物搞笑", "治愈萌宠"],
    }
    
    # 高互动话题（容易引发评论）
    HIGH_ENGAGEMENT_TOPICS = [
        "你更喜欢A还是B？",
        "你觉得这个对吗？",
        "你会怎么做？",
        "你遇到过吗？",
        "你支持哪一方？",
        "如果是你，你会怎么选？",
    ]
    
    # 音乐风格匹配（根据内容类型）
    MUSIC_STYLE_MAP = {
        "生活技巧": "轻松,明快,节奏感",
        "情感共鸣": "温柔,治愈,钢琴曲",
        "知识科普": "科技感,电子,现代",
        "娱乐搞笑": "搞笑,魔性,洗脑",
        "美食探店": "欢快,美食感,中国风",
        "旅行vlog": "旅行,自由,民谣",
        "萌宠日常": "可爱,轻快,萌系",
    }
    
    # 视频运镜建议（根据内容类型）
    CAMERA_STYLE_MAP = {
        "生活技巧": ["[固定]", "[推进]", "[特写]"],
        "情感共鸣": ["[缓慢推进]", "[固定]", "[拉远]"],
        "知识科普": ["[固定]", "[推进]", "[左移]"],
        "娱乐搞笑": ["[快速切换]", "[晃动]", "[固定]"],
        "美食探店": ["[特写]", "[推进]", "[上摇]"],
        "旅行vlog": ["[左摇]", "[跟随]", "[上升]"],
        "萌宠日常": ["[固定]", "[推进]", "[低角度]"],
    }
    
    def __init__(self):
        """初始化抖音内容策略"""
        self.today_trending = []
        self.post_analytics = []
    
    def generate_hook_intro(self, topic: str, style: str = "好奇") -> str:
        """
        生成吸引眼球的开头（黄金3秒）
        
        Args:
            topic: 主题
            style: 风格（好奇、震惊、实用、共鸣）
            
        Returns:
            开头文案
        """
        if style == "好奇":
            template = random.choice([
                f"你知道吗？{topic}竟然...",
                f"我赌你不知道{topic}",
                f"90%的人都不知道{topic}",
            ])
        elif style == "震惊":
            template = random.choice([
                f"震惊！{topic}竟然...",
                f"这个{topic}火了！",
                f"终于有人把{topic}说清楚了",
            ])
        elif style == "实用":
            template = random.choice([
                f"只需3秒，学会{topic}",
                f"今天教你{topic}的正确姿势",
                f"这个{topic}技巧太实用了",
            ])
        else:  # 共鸣
            template = random.choice([
                f"关于{topic}，我只说一次",
                f"这个{topic}让我惊呆了",
                f"看完这个{topic}你会回来感谢我",
            ])
        
        return template
    
    def generate_viral_script(
        self,
        topic: str,
        content_type: str = "生活技巧",
        duration: int = 6
    ) -> Dict[str, Any]:
        """
        生成爆款视频脚本
        
        Args:
            topic: 主题
            content_type: 内容类型
            duration: 视频时长
            
        Returns:
            包含完整脚本的字典
        """
        # 1. 生成开头（黄金3秒）
        style = random.choice(["好奇", "震惊", "实用", "共鸣"])
        hook = self.generate_hook_intro(topic, style)
        
        # 2. 生成核心内容（根据时长调整）
        if duration <= 6:
            # 短视频：直接展示核心点
            core_content = f"其实{topic}的关键在于..."
            core_points = ["第一点：...", "第二点：..."]
        else:
            # 10秒视频：可以展示更多细节
            core_content = f"关于{topic}，我要告诉你三个秘密..."
            core_points = ["首先...", "其次...", "最后..."]
        
        # 3. 生成行动号召
        cta = random.choice(self.CTA_PHRASES).format(topic=topic)
        
        # 4. 生成视频描述（用于AI生成）
        camera_style = random.choice(self.CAMERA_STYLE_MAP.get(content_type, ["[固定]"]))
        scene_style = random.choice(["阳光明媚", "温馨", "现代", "复古"])
        video_prompt = f"{topic}，{scene_style}场景，{camera_style}"
        
        # 5. 生成音乐风格
        music_style = self.MUSIC_STYLE_MAP.get(content_type, "轻松,明快")
        
        return {
            "hook": hook,  # 开头
            "core_content": core_content,  # 核心内容
            "core_points": core_points,  # 要点列表
            "cta": cta,  # 行动号召
            "full_script": f"{hook}\n\n{core_content}\n\n{cta}",
            "video_prompt": video_prompt,
            "music_style": music_style,
            "style": style,
        }
    
    def generate_ab_test_titles(
        self,
        topic: str,
        count: int = 5
    ) -> List[Dict[str, str]]:
        """
        生成A/B测试标题（用于测试哪个标题效果更好）
        
        Args:
            topic: 主题
            count: 生成数量
            
        Returns:
            标题列表，每个包含类型和文案
        """
        titles = []
        
        # 类型A：好奇心驱动
        titles.append({
            "type": "好奇心",
            "title": f"你知道吗？{topic}竟然...",
            "expected_ctr": "高"
        })
        
        # 类型B：数字驱动
        titles.append({
            "type": "数字型",
            "title": f"90%的人都不知道{topic}",
            "expected_ctr": "中高"
        })
        
        # 类型C：实用型
        titles.append({
            "type": "实用型",
            "title": f"只需3秒，学会{topic}",
            "expected_ctr": "中"
        })
        
        # 类型D：情感型
        titles.append({
            "type": "情感型",
            "title": f"关于{topic}，我只说一次",
            "expected_ctr": "中高"
        })
        
        # 类型E：震惊型
        titles.append({
            "type": "震惊型",
            "title": f"震惊！{topic}竟然...",
            "expected_ctr": "高"
        })
        
        return titles[:count]
    
    def optimize_for_algorithm(
        self,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        针对抖音算法优化内容
        
        抖音算法关键因素：
        1. 完播率（用户是否看完）
        2. 互动率（点赞、评论、转发）
        3. 关注率（是否关注）
        
        Args:
            content: 原始内容
            
        Returns:
            优化后的内容
        """
        optimized = content.copy()
        
        # 1. 确保开头足够吸引（3秒内抓住注意力）
        if "hook" in optimized:
            # 检查开头是否够短
            hook = optimized["hook"]
            if len(hook) > 30:
                optimized["hook"] = hook[:30] + "..."
                optimized["hook_warning"] = "开头过长，已截断"
        
        # 2. 添加互动引导
        if "cta" in optimized:
            # 确保有明确的行动号召
            cta = optimized["cta"]
            if "点赞" not in cta and "关注" not in cta and "评论" not in cta:
                optimized["cta"] = cta + " 记得点赞关注哦！"
        
        # 3. 优化视频描述（添加算法友好关键词）
        if "video_prompt" in optimized:
            # 添加高完播率关键词
            viral_keywords = ["精彩", "必看", "震撼", "治愈"]
            keyword = random.choice(viral_keywords)
            optimized["video_prompt"] = f"{optimized['video_prompt']}，{keyword}"
        
        # 4. 添加算法优化建议
        optimized["algorithm_tips"] = [
            "前3秒是关键，确保开头足够吸引",
            "在视频中间添加小高潮，提高完播率",
            "结尾前引导互动，提高互动率",
            "使用热门BGM，增加推荐权重",
        ]
        
        return optimized
    
    def get_trending_topic(self, category: str = None) -> str:
        """
        获取热门话题（可接入真实数据源）
        
        Args:
            category: 话题类别
            
        Returns:
            热门话题
        """
        if category and category in self.TRENDING_TOPICS:
            topics = self.TRENDING_TOPICS[category]
        else:
            # 随机选择一个类别
            all_topics = []
            for cat_topics in self.TRENDING_TOPICS.values():
                all_topics.extend(cat_topics)
            topics = all_topics
        
        return random.choice(topics)

    def get_trending_topics(
        self,
        count: int,
        categories: Optional[List[str]] = None,
        *,
        unique: bool = True,
    ) -> List[str]:
        """
        获取一组热门话题，默认尽量避免重复。
        """
        if count <= 0:
            return []

        category_list = categories or list(self.TRENDING_TOPICS.keys())
        if not category_list:
            return []

        topic_pool: List[str] = []
        for category in category_list:
            topic_pool.extend(self.TRENDING_TOPICS.get(category, []))

        if not topic_pool:
            return []

        if not unique:
            return [random.choice(topic_pool) for _ in range(count)]

        shuffled_pool = topic_pool[:]
        random.shuffle(shuffled_pool)
        if count <= len(shuffled_pool):
            return shuffled_pool[:count]

        # 话题池不够时，先去重返回，再循环补齐
        results = shuffled_pool[:]
        while len(results) < count:
            results.append(random.choice(topic_pool))
        return results[:count]

    def get_trending_topics_for_types(
        self,
        content_types: List[str],
        *,
        unique: bool = True,
    ) -> List[str]:
        """
        按内容类型逐条选择话题，确保 topic 和 content_type 对齐。
        """
        if not content_types:
            return []

        shuffled_by_type: Dict[str, List[str]] = {}
        for content_type in set(content_types):
            pool = list(self.TRENDING_TOPICS.get(content_type, []))
            random.shuffle(pool)
            shuffled_by_type[content_type] = pool

        used_topics = set()
        results: List[str] = []

        for content_type in content_types:
            pool = shuffled_by_type.get(content_type, [])
            topic: Optional[str] = None

            while pool:
                candidate = pool.pop(0)
                if not unique or candidate not in used_topics:
                    topic = candidate
                    break

            if topic is None:
                fallback_pool = self.TRENDING_TOPICS.get(content_type, [])
                if fallback_pool:
                    topic = random.choice(fallback_pool)
                else:
                    topic = self.get_trending_topic()

            if unique:
                used_topics.add(topic)
            results.append(topic)

        return results
    
    def generate_engagement_question(self, topic: str) -> str:
        """
        生成互动问题（引导评论）
        
        Args:
            topic: 主题
            
        Returns:
            互动问题
        """
        templates = [
            f"关于{topic}，你有什么想说的？",
            f"你觉得{topic}怎么样？评论区告诉我",
            f"你遇到过{topic}吗？分享一下",
            f"关于{topic}，你支持A还是B？",
            f"如果是你，你会怎么处理{topic}？",
        ]
        
        return random.choice(templates)
    
    def calculate_viral_score(
        self,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        计算爆款潜力评分
        
        Args:
            content: 内容字典
            
        Returns:
            评分结果
        """
        score = 0
        reasons = []

        # 1. 开头吸引力（0-30）
        hook = str(content.get("hook", "")).strip()
        hook_len = len(hook)
        weak_openers = ["今天", "大家好", "我来", "给大家", "分享", "教你"]
        if hook_len == 0:
            reasons.append("缺少开头钩子")
        elif hook_len <= 16:
            score += 28
            reasons.append("开头短促，适合前3秒抓人")
        elif hook_len <= 24:
            score += 22
            reasons.append("开头长度适中")
        elif hook_len <= 32:
            score += 14
            reasons.append("开头略长，仍可接受")
        else:
            score += 8
            reasons.append("开头偏长，容易拖累完播率")
        if any(hook.startswith(prefix) for prefix in weak_openers):
            score -= 8
            reasons.append("开头存在常见铺垫语")

        # 2. CTA 强度（0-20）
        cta = str(content.get("cta", "")).strip()
        strong_cta_words = ["点赞", "关注", "评论", "收藏", "转发"]
        cta_hits = sum(word in cta for word in strong_cta_words)
        if cta_hits >= 2:
            score += 18
            reasons.append("CTA 明确且强")
        elif cta_hits == 1:
            score += 12
            reasons.append("CTA 基本到位")
        elif cta:
            score += 6
            reasons.append("CTA 存在但较弱")
        else:
            reasons.append("缺少 CTA")

        # 3. 互动潜力（0-15）
        engagement_question = str(content.get("engagement_question", "")).strip()
        if len(engagement_question) >= 12:
            score += 13
            reasons.append("具备具体互动问题")
        elif engagement_question:
            score += 8
            reasons.append("有互动引导，但较泛")
        else:
            reasons.append("缺少互动问题")

        # 4. 时长优化（0-15）
        duration = int(content.get("duration", 6) or 6)
        if duration == 6:
            score += 15
            reasons.append("6 秒节奏友好")
        elif duration == 10:
            score += 10
            reasons.append("10 秒时长适中")
        else:
            score += 4
            reasons.append("时长不在推荐区间")

        # 5. 音乐匹配（0-10）
        music_style = str(content.get("music_style", "")).strip()
        if len(music_style) >= 4:
            score += 8
            reasons.append("具备音乐风格建议")
        else:
            score += 3
            reasons.append("缺少清晰音乐建议")

        # 6. 内容类型基础盘（0-10）
        content_type = content.get("content_type", "")
        if content_type in ["生活技巧", "情感共鸣"]:
            score += 8
            reasons.append(f"{content_type}更容易形成稳定受众")
        elif content_type in ["娱乐搞笑", "萌宠日常", "美食探店"]:
            score += 7
            reasons.append(f"{content_type}具备较强分发潜力")
        elif content_type:
            score += 5
            reasons.append(f"{content_type}为常见内容类型")

        score = max(0, min(score, 100))

        # 评级
        if score >= 85:
            level = "S级（爆款潜力极高）"
        elif score >= 70:
            level = "A级（爆款潜力高）"
        elif score >= 55:
            level = "B级（有潜力）"
        elif score >= 40:
            level = "C级（需要优化）"
        else:
            level = "D级（需重做）"

        return {
            "score": score,
            "level": level,
            "reasons": reasons,
            "max_score": 100,
        }
    
    def generate_content_calendar(
        self,
        days: int = 7,
        topics: List[str] = None,
        publish_strategy: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        生成内容日历（规划未来几天的发布内容）
        
        Args:
            days: 天数
            topics: 主题列表（如果为None则自动选择）
            
        Returns:
            内容日历
        """
        calendar = []
        
        if topics is None:
            topics = self.get_trending_topics(days, list(self.TRENDING_TOPICS.keys()))
        
        for i, topic in enumerate(topics[:days]):
            # 根据星期几调整内容类型
            weekday = (datetime.now().weekday() + i) % 7
            
            # 周末更适合娱乐内容
            if weekday in [5, 6]:  # 周六日
                content_type = random.choice(["娱乐搞笑", "萌宠日常", "美食探店"])
            # 工作日更适合实用内容
            else:
                content_type = random.choice(["生活技巧", "知识科普", "情感共鸣"])
            
            script = self.generate_viral_script(topic, content_type)
            score = self.calculate_viral_score({
                **script,
                "content_type": content_type,
                "duration": 6
            })
            
            calendar.append({
                "day": i + 1,
                "date": (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d'),
                "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday],
                "topic": topic,
                "content_type": content_type,
                "script": script,
                "viral_score": score,
                "best_post_time": (
                    publish_strategy.weekend_best_time
                    if publish_strategy and weekday in [5, 6]
                    else publish_strategy.weekday_best_time
                    if publish_strategy
                    else "12:00" if weekday in [5, 6] else "18:00"
                ),
            })
        
        return calendar
