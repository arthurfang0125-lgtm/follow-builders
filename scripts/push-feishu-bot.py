#!/usr/bin/env python3
"""
AI Builder 每日晨报 · 飞书 Bot 推送脚本
GitHub Actions 调用：读取 feed-x.json → 翻译 + 生成中文摘要 → 发飞书 Bot 消息
"""
import json, urllib.request, re, urllib.error, sys, time
from datetime import datetime

# ===== 配置 =====
FEISHU_APP_ID = "cli_a94a1f9fd17b5bd3"
FEISHU_APP_SECRET = "coUNvdJ5LfyqsJksUM3kDgbnxaOGV4gH"
FEISHU_USER_OPEN_ID = "ou_250a5418c3b3dc01342906ced15621e6"
FEED_URL = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json"

# ===== Builder 中文名 & 角色映射 =====
BUILDER_NAMES = {
    "swyx": ("Swyx", "AI 产品顾问 / Latent Space"),
    "petergyang": ("Peter Yang", "AI 投资人 / Roblox 产品"),
    "trq212": ("Thariq", "Vercel"),
    "rauchg": ("Guillermo Rauch", "Vercel CEO"),
    "levie": ("Aaron Levie", "Box CEO"),
    "garrytan": ("Garry Tan", "YC CEO"),
    "mattturck": ("Matt Turck", "FirstMark Capital"),
    "zarazhangrui": ("Zara Zhang", "D2iQ / 华人 Builder"),
    "nikunj": ("Nikunj Kothari", "转型 VC 的前 Googler"),
    "steipete": ("Peter Steinberger", "PSPDFKit 创始人"),
    "adityaag": ("Aditya Agarwal", "Coriell Capital"),
    "amasad": ("Amjad Masad", "Replit CEO"),
    "sama": ("Sam Altman", "OpenAI CEO"),
    "sama2": ("Sam Altman", "OpenAI CEO"),
}

# ===== 质量评分函数 =====
QUALITY_SIGNALS = [
    # 具体观点/分析
    "because", "means", "suggests", "reveals", "proves", "demonstrates",
    "insight", "pattern", "trend", "mistake", "wrong", "actually",
    "the key", "the problem", "the issue", "the reason", "the truth",
    "realize", "learned", "figured out", "discovered",
    # 数据/数字
    "x ", "%", "billion", "million", "$", "10x", "100x",
    # 方法论
    "instead of", "rather than", "focus on", "the right way",
    "stop", "start", "do this", "don't do", "rule", "principle",
    # 具体实体
    "we built", "we launched", "we shipped", "we made",
    "just released", "just launched", "open sourced",
    "introducing", "announcing", "launching",
]

# ===== AI 相关性判断（硬门槛）=====
# 严格 AI 信号：有这些词直接算 AI 相关
AI_CORE_SIGNALS = [
    "ai ", " llm", "gpt", "gemini", "claude", "mistral", "deepseek",
    "chatgpt", "openai", "anthropic", "deepmind", "meta ai",
    "machine learning", "neural", "benchmark", "training data",
    "inference", "fine-tun", "rag", "embedding", "vector db",
    "agent", "agents", "agentic", "autonomous ai",
    "prompt", "prompting", "few-shot", "zero-shot",
    "scaling law", "emergent", "reasoning model",
    "cursor", "copilot", "replit", "perplexity",
]
# 宽松 AI 信号：必须含洞察关键词才能进摘要
# 重新设计——只有真正有观点/洞察的才收录
AI_INSIGHT_SIGNALS = [
    # 核心洞察类
    "mistake", "wrong", "lie ", "truth", "surprising",
    "actually", "realize", "lesson", "learned",
    "surprised", "unexpected", "counterintuitive",
    # 趋势/格局类
    "trend", "prediction", "forecast", "will happen",
    "the future of", "next wave", "paradigm",
    # 深度分析/观点
    "insight", "analysis", "opinion", "perspective",
    "the key is", "the problem is", "the reason is",
    "here's what", "here is what",
    # 具体洞察描述
    "over-rely", "underestimate", "overestimate",
    "fundamentally", "architecture", "unlocks",
    "solved problem", "the real", "the actual",
    # 产品/系统设计洞察
    "ux ", "user experience", "developer experience",
    "design taste",
    # 技术系统类（Agent/Harness 生态）
    "plugin", "harness", "agent system", "agentic",
    # 协作/工作流洞察
    "collaborat", "workflow", "handoff",
]
NON_AI_SIGNALS = [
    # 纯生活/娱乐/个人
    "broadway", "theater", "theatre", "musical", "百老汇",
    "flight ", "fly to", "flew to", "fly back", "travel", "hotel",
    "dinner", "lunch", "breakfast", "coffee break",
    "good morning", "good night", "gm ", "晚安", "早安",
    "weekend", "holiday", "vacation", "beach", "sunset",
    "family", "kid", "wife", "husband", "baby", "dog", "cat",
    "gym", "running", "yoga", "fitness",
    "movie", "film", "book", "music", "concert", "game",
    "restaurant", "pub ", "cafe", "pizza",
    "birthday", "anniversary", "celebrat", "party",
    # 纯社交/情绪
    "haha", "lol", "lmao", "笑死",
    "love this", "love it", "so cool", "so funny",
    "proud of", "congrats", "congratulations",
    "thank you", "thanks for",
    # 纯转发
    "retweet", "shared", "via ",
    # 纯 promo
    "link in bio", "subscribe", "check out my",
    # Swyx 生活类关键词
    "latent space", "swyx", "solo song", "cabaret", "seating",
    "fumbled", "lyrics", "singing", "performer", "v limited",
    "song for the first time",
]


# ===== 翻译精炼函数 =====
# 去掉翻译后文字中的语气词、开头白话，直接出观点
FILLER_PATTERNS = [
    r"^(so |too |yeah |yes |well |look,? )",
    r"^(honestly|actually|basically|literally|simply|just )",
    r"^(the thing is|what i realize|what i learned|here'?s (the )?(thing|take):?\s*)",
    r"(哈哈|呵呵|嘿嘿|嘻嘻|～|…{2,})$",  # 尾部语气
]


def strip_filler(text):
    """去掉推文开头的语气词/白话，直接出核心观点。"""
    t = text.strip()
    for pat in FILLER_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    # 去掉开头括号说明（"1)" "2)" 等列表格式，保留内容）
    t = re.sub(r"^\d+\)\s*", "", t)
    return t


def is_ai_relevant(text):
    """
    判断推文是否跟 AI/科技/行业认知相关。
    逻辑（保守，宁少勿滥）：
    1. 有严格 AI 信号词（AI_CORE_SIGNALS）→ 相关
    2. 有非 AI 信号词（NON_AI_SIGNALS）且无严格 AI 信号 → 不相关
    3. 有洞察关键词（AI_INSIGHT_SIGNALS）→ 相关
    4. 其他 → 不相关
    """
    t_lower = text.lower()
    has_core = any(sig in t_lower for sig in AI_CORE_SIGNALS)
    has_insight = any(sig in t_lower for sig in AI_INSIGHT_SIGNALS)
    has_non_ai = any(sig in t_lower for sig in NON_AI_SIGNALS)

    if has_core:
        return True
    if has_non_ai and not has_core:
        return False
    if has_insight:
        return True
    return False


LOW_SIGNALS = [
    # 纯情绪
    "haha", "lol", "lmao", "笑死", "笑到", "太牛", "太强", "绝了",
    "love this", "love it", "so cool", "so funny", "so good",
    "proud", "congrats", "congratulations", "amazing",
    # 纯日常
    "good morning", "good night", "gm ", "gn ", "晚安", "早安",
    "had a", "great meal", "lunch", "dinner", "coffee",
    # 纯转发
    "retweet", "rt @", "shared", "via ",
    # 纯 promo/announcement
    "link in bio", "subscribe", "check out my", "new video",
    "new post", "just dropped", "episode", "podcast",
    # 太短无信息量
    "yes", "no ", "ok ", "sure", "wow", "wtf", "omg",
    # 纯符号/无实质
    "🪄", "🦞", "🦀", "⬆️", "✅", "👏", "😂", "🎉",
]


def score_quality(text):
    """
    给一条推文打内容质量分（0~100）。
    - 60 分以上：有实质内容，可加入观点速览
    - 80 分以上：高质量，进入最值得看候选
    """
    t = text.strip()
    score = 50  # 基准分

    # 长度奖励（去掉链接后）
    clean_len = len(re.sub(r"https?://\S+", "", t).strip())
    if clean_len >= 200:
        score += 20
    elif clean_len >= 120:
        score += 10
    elif clean_len < 40:
        return 0  # 太短直接淘汰

    t_lower = t.lower()

    # 加分信号
    for sig in QUALITY_SIGNALS:
        if sig.lower() in t_lower:
            score += 8

    # 扣分信号
    for sig in LOW_SIGNALS:
        if sig.lower() in t_lower:
            score -= 25

    # 检查是否几乎全是符号/emoji（无实质文字）
    alpha_ratio = sum(1 for c in t if c.isalpha()) / max(len(t), 1)
    if alpha_ratio < 0.3:
        score -= 40

    return max(0, min(100, score))


def is_substantive(text):
    """判断是否值得加入摘要：有实质内容 + 与 AI/科技/行业相关。"""
    return is_ai_relevant(text) and score_quality(text) >= 60


def is_top_quality(text):
    """判断是否值得进入「最值得看」板块（高质量 + AI 相关）。"""
    return is_ai_relevant(text) and score_quality(text) >= 80


# ===== 工具函数 =====
def translate(text, src="en", dst="zh-CN", retries=2):
    """调用 MyMemory 免费翻译 API，将 text 从 src 译为 dst。"""
    if not text or len(text.strip()) < 5:
        return text
    url = (
        f"https://api.mymemory.translated.net/get"
        f"?q={urllib.parse.quote(text[:500])}"
        f"&langpair={src}|{dst}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())
        match = d.get("responseStatus")
        if match == 200:
            translated = d["responseData"]["translatedText"]
            # MyMemory 对过长文本分段翻译，拼接后返回
            return translated
    except Exception:
        pass
    return text

import urllib.parse

def translate_v2(text, src="en", dst="zh-CN"):
    """翻译一段文字，自动处理长文本分段。"""
    MAX_LEN = 450
    if not text:
        return text
    # 判断是否全中文，是则不译
    try:
        if sum(1 for c in text[:50] if '\u4e00' <= c <= '\u9fff') > 20:
            return text
    except:
        pass
    if len(text) <= MAX_LEN:
        return _translate_chunk(text, src, dst)
    # 分句
    sentences = text.split('. ')
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) < MAX_LEN:
            current += (". " if current else "") + s
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    # 合并相邻短句减少碎片
    merged = []
    for c in chunks:
        if merged and len(merged[-1]) + len(c) < MAX_LEN + 20:
            merged[-1] += ". " + c
        else:
            merged.append(c)
    result = []
    for chunk in merged:
        t = _translate_chunk(chunk.strip(), src, dst)
        result.append(t)
        time.sleep(0.3)
    return " ".join(result)

def _translate_chunk(text, src, dst):
    url = (
        f"https://api.mymemory.translated.net/get"
        f"?q={urllib.parse.quote(text)}"
        f"&langpair={src}|{dst}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())
        if d.get("responseStatus") == 200:
            return d["responseData"]["translatedText"]
    except Exception:
        pass
    return text

def translate_tweets(texts, delay=0.4):
    """批量翻译推文，返回 [(原文, 译文)]。"""
    results = []
    for t in texts:
        zh = translate_v2(t)
        results.append((t, zh))
        time.sleep(delay)
    return results

def get_tenant_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read())
    if d.get("code") != 0:
        raise Exception(f"获取 token 失败: {d.get('msg')}")
    return d["tenant_access_token"]

def send_feishu_text(token, open_id, text):
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    payload = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read())
    if d.get("code") != 0:
        raise Exception(f"发送失败: {d.get('msg')}")
    return d

def fetch_feed():
    req = urllib.request.Request(FEED_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# ===== 核心逻辑：构建摘要 =====
def build_digest(feed, translations):
    today = datetime.now().strftime("%Y-%m-%d")
    builders = feed.get("x", [])

    top_items = []
    view_items = []

    for b in builders:
        handle = b.get("handle", "").lower()
        name_raw = b.get("name", handle)
        role = BUILDER_NAMES.get(handle, (name_raw, ""))[1]
        name = BUILDER_NAMES.get(handle, (name_raw, ""))[0]

        tweets = b.get("tweets", [])
        if not tweets:
            continue

        for tw in tweets:
            text = tw.get("text", "")
            clean_text = re.sub(r"https?://\S+", "", text).strip()
            likes = tw.get("likes", 0)
            rt = tw.get("retweets", 0)

            # 用质量评分判断是否值得收录
            if not is_substantive(clean_text):
                continue

            zh_text = translations.get(clean_text, translations.get(text, clean_text))
            # 精炼：去掉语气词/白话，直接出观点
            zh_text = strip_filler(zh_text)
            entry = f"- {name}（{role}）：{zh_text}"

            # 最值得看：高质量（>=80分）或高互动（likes>=20 or rt>=5）
            is_top = is_top_quality(clean_text) or (likes >= 20 or rt >= 5)
            if is_top and len(top_items) < 3:
                top_items.append("▶ " + entry)
            elif len(view_items) < 8:
                view_items.append("💡 " + entry)

    lines = [
        f"🌅 AI Builder 每日晨报｜{today}",
        "跟踪真正做产品、做研究、做系统的人。",
        "",
        "🔥 今日最值得看",
    ]
    lines += top_items if top_items else ["（今日暂无高质量推文）"]

    lines += ["", "🧠 Builder 观点速览"]
    lines += view_items if view_items else ["（今日暂无高质量推文）"]

    lines += [
        "",
        "📌 今天可执行的启发",
        "- 如果你在做产品 → 问自己：用户是想「跟 AI 聊」还是想把「一件事交给 AI 做完」？",
        "- 如果你在做内容 → 多关注构建者的原始表达，而不是二手解读。",
        "- 如果你在做 Agent 工作流 → 优先补「稳定性、权限、可观察性、失败兜底」。",
        "- 如果你在做商业化 → 盯紧企业级 AI 的真实需求：接系统、接数据、可执行、能交付。",
    ]

    return "\n".join(lines)

def build_links_summary(feed):
    builders = feed.get("x", [])
    links = []
    seen = set()
    for b in builders:
        handle = b.get("handle", "").lower()
        name = BUILDER_NAMES.get(handle, (b.get("name", ""), ""))[0]
        for tw in b.get("tweets", []):
            u = tw.get("url", "")
            if u and u not in seen:
                seen.add(u)
                links.append(f"- {name}：{u}")
    return "🔗 今日原文链接汇总\n" + "\n".join(links[:10])

def main():
    print("📡 读取 feed 数据...")
    feed = fetch_feed()
    builders_data = feed.get("x", [])
    print(f"   → {len(builders_data)} 位 Builders")

    # 收集所有待翻译的推文（必须：AI相关 + 质量评分 >= 60）
    print("🌏 收集推文文本（AI相关 + 质量评分 >= 60）...")
    all_texts = []
    text_to_builder = {}
    skipped = []
    for b in builders_data:
        for tw in b.get("tweets", []):
            t_raw = tw.get("text", "")
            t = re.sub(r"https?://\S+", "", t_raw).strip()
            if not is_ai_relevant(t):
                skipped.append(t[:50])
                continue
            if is_substantive(t) and t not in text_to_builder:
                text_to_builder[t] = True
                all_texts.append(t)
    print(f"   → {len(all_texts)} 条通过，{len(skipped)} 条因非AI相关内容被过滤")
    print(f"   → {len(all_texts)} 条推文待翻译")

    print("✍️  翻译推文...")
    translations = {}
    for i, text in enumerate(all_texts):
        zh = translate_v2(text)
        translations[text] = zh
        print(f"   [{i+1}/{len(all_texts)}] {'✅' if zh != text else '⏭'} {text[:40]}...")
        time.sleep(0.5)

    print("📝 生成中文摘要...")
    digest = build_digest(feed, translations)
    links = build_links_summary(feed)
    print(f"   → 摘要 {len(digest)} 字")

    print("🔑 获取飞书 token...")
    token = get_tenant_token()

    print("📤 发送飞书消息...")
    chunk_size = 3800
    chunks = [digest[i:i+chunk_size] for i in range(0, len(digest), chunk_size)]
    for i, chunk in enumerate(chunks):
        part = f"[{i+1}/{len(chunks)}]\n{chunk}"
        result = send_feishu_text(token, FEISHU_USER_OPEN_ID, part)
        print(f"   → 第 {i+1} 部分: code={result.get('code')}")

    send_feishu_text(token, FEISHU_USER_OPEN_ID, links)
    print("   → 链接汇总已发送")

    print("✅ 完成！")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
