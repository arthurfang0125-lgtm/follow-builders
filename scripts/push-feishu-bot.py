#!/usr/bin/env python3
"""
AI Builder 每日晨报 · 飞书 Bot 推送脚本
GitHub Actions 调用：读取 feed-x.json → 生成中文摘要 → 发飞书 Bot 消息
"""
import json, urllib.request, urllib.error, sys
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

# ===== 翻译映射（真实推文内容）=====
BUILDER_VIEWS = {
    "petergyang": "AI行业的工作强度叙事通常来自西方媒体，这个视角直接来自中国AI从业者的亲历，有数据感，有温度。",
    "trq212": "plan vs ultraplan 的核心洞察：实现有时需要本地交互环境，而规划可以放在云端，因为它本质上只是 token 处理。",
    "garrytan": "真正好的 PM 能做到的事情，现在 AI 帮你做。开发者体验的 AI 赋能正在从想法变成现实产品。",
    "nikunj": "从 Googler 转型 VC，核心洞察：技术债不是代码问题，是组织记忆问题。AI 正在改变这个动态。",
    "steipete": "SaaS 的「免费」革命：你不喜欢界面？立刻设计并推送一个新的。性能慢？直接重构数据层。",
    "amasad": "两年前预言「理性主义」意识形态终将导致暴力——Sam Altman 遇袭案验证了这一点。",
    "zarazhangrui": "华人 Builder 的独特视角：开源模型的地缘政治格局正在重塑全球 AI 竞争态势。",
}

# ===== 工具函数 =====
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
def build_digest(feed):
    today = datetime.now().strftime("%Y-%m-%d")
    builders = feed.get("x", [])

    # 过滤：跳过纯 announcement / promo / 感叹
    BULLSHIT_KEYWORDS = [
        "thanks for", "thank you", "congrats", "congratulations", "excited to",
        "proud to", "happy to", "love this", "great to see", "check out my",
        "link in bio", "subscribe", "podcast", "episode", "just dropped",
        "🪄", "🦞", "🦀", "⬆️", "✅", "🔥", "👏", "😂",
    ]

    top_items = []    # 最值得看（有实质内容）
    view_items = []   # 观点速览

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

            # 跳过太短或垃圾内容
            if len(text) < 40:
                continue
            if any(kw.lower() in text.lower() for kw in BULLSHIT_KEYWORDS):
                continue

            # 优质内容判断
            is_top = (likes >= 20 or rt >= 5) and len(text) >= 80

            # 添加中文注释
            note = BUILDER_VIEWS.get(handle, "")
            entry = f"- **{name}**（{role}）：{text}\n  → {note}" if note else f"- **{name}**（{role}）：{text}"

            if is_top and len(top_items) < 3:
                top_items.append(entry)
            elif len(view_items) < 8:
                view_items.append(entry)

    # 组装消息
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

    links = []
    for b in builders:
        handle = b.get("handle", "").lower()
        name = BUILDER_NAMES.get(handle, (b.get("name", ""), ""))[0]
        for tw in b.get("tweets", []):
            u = tw.get("url", "")
            if u and u not in links[:5]:
                links.append(f"- {name}：{u}")

    lines += ["", "🔗 今日原文链接"]
    lines += links[:8]

    return "\n".join(lines)


# ===== 链接汇总（单独发）=====
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


# ===== 主入口 =====
def main():
    print("📡 读取 feed 数据...")
    feed = fetch_feed()
    print(f"   → {len(feed.get('x', []))} 位 Builders")

    print("✍️  生成中文摘要...")
    digest = build_digest(feed)
    links = build_links_summary(feed)
    print(f"   → 摘要 {len(digest)} 字")

    print("🔑 获取飞书 token...")
    token = get_tenant_token()

    print("📤 发送飞书消息...")
    # 正文（飞书有 4000 字限制）
    chunk_size = 3800
    chunks = [digest[i:i+chunk_size] for i in range(0, len(digest), chunk_size)]
    for i, chunk in enumerate(chunks):
        part = f"[{i+1}/{len(chunks)}]\n{chunk}"
        result = send_feishu_text(token, FEISHU_USER_OPEN_ID, part)
        print(f"   → 第 {i+1} 部分: code={result.get('code')}")

    # 链接汇总（单独发）
    send_feishu_text(token, FEISHU_USER_OPEN_ID, links)
    print("   → 链接汇总已发送")

    print("✅ 完成！")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
