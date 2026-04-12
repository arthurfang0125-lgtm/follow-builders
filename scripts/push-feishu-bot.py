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

    # 过滤关键词
    BULLSHIT_KEYWORDS = [
        "thanks for", "thank you", "congrats", "congratulations", "excited to",
        "proud to", "happy to", "love this", "great to see", "check out my",
        "link in bio", "subscribe", "podcast", "episode", "just dropped",
        "🪄", "🦞", "🦀", "⬆️", "✅", "🔥", "👏", "😂",
    ]

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
            url = tw.get("url", "")
            likes = tw.get("likes", 0)
            rt = tw.get("retweets", 0)

            if len(text) < 40:
                continue
            if any(kw.lower() in text.lower() for kw in BULLSHIT_KEYWORDS):
                continue

            is_top = (likes >= 20 or rt >= 5) and len(text) >= 80

            # 去链接 + 翻译
            clean_text = re.sub(r"https?://\S+", "", text).strip()
            zh_text = translations.get(clean_text, translations.get(text, clean_text))

            # 去掉了 → note 价值判断行
            entry = f"- {name}（{role}）：{zh_text}"

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

    # 收集所有待翻译的推文
    print("🌏 收集推文文本...")
    all_texts = []
    text_to_builder = {}
    BULLSHIT_KEYWORDS = [
        "thanks for", "thank you", "congrats", "congratulations", "excited to",
        "proud to", "happy to", "love this", "great to see", "check out my",
        "link in bio", "subscribe", "podcast", "episode", "just dropped",
        "🪄", "🦞", "🦀", "⬆️", "✅", "🔥", "👏", "😂",
    ]
    for b in builders_data:
        for tw in b.get("tweets", []):
            t_raw = tw.get("text", "")
            t = re.sub(r"https?://\S+", "", t_raw).strip()
            if len(t) >= 40 and not any(kw.lower() in t.lower() for kw in BULLSHIT_KEYWORDS):
                if t not in text_to_builder:
                    text_to_builder[t] = True
                    all_texts.append(t)
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
