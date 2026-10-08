import urllib.request, json, base64, sys, time
from datetime import datetime, timezone, timedelta

TOKEN = open("/home/openclaw/.openclaw/workspace/github.token").read().strip()
TAVILY_KEY = "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"
COOKIE = open("/home/openclaw/.openclaw/workspace/weibo.cookie").read().strip()
XSRF = open("/home/openclaw/.openclaw/workspace/weibo.xsrf").read().strip()

REPO = "6py5576s6n-creator/movie-news"

def gh(method, path, body=None):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = urllib.request.Request(url, method=method)
    r.add_header("Authorization", f"Bearer {TOKEN}")
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("Content-Type", "application/json")
    if body: r.data = json.dumps(body).encode()
    return json.loads(urllib.request.urlopen(r).read())

def gh_get_json(path):
    try:
        c = gh("GET", path)
        return json.loads(base64.b64decode(c["content"]).decode("utf-8")), c["sha"]
    except Exception as e:
        print(f"读 {path} 失败: {e}")
        return None, None

def gh_put_json(path, data, sha, msg):
    body = {"message": msg, "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode()}
    if sha: body["sha"] = sha
    return gh("PUT", path, body)

print("=== 1. 读 tracked.json ===")
tracked, _ = gh_get_json("tracked.json")
if not isinstance(tracked, list):
    tracked = ["奇换人生", "美人余"]
print("追踪剧:", tracked)

print("=== 2. 读现有 news.json ===")
old_news, news_sha = gh_get_json("news.json")
if not isinstance(old_news, list):
    old_news = []
print("旧数据:", len(old_news), "条")

print("=== 3. Tavily 搜索 ===")
def tavily(query):
    body = {"api_key": TAVILY_KEY, "query": query, "topic": "news", "days": 7, "max_results": 5}
    r = urllib.request.Request("https://api.tavily.com/search", method="POST",
        headers={"Content-Type": "application/json"}, data=json.dumps(body).encode())
    try:
        return json.loads(urllib.request.urlopen(r, timeout=30).read()).get("results", [])
    except Exception as e:
        print(f"Tavily [{query}] 失败: {e}")
        return []

new_items = []
for kw in ["定档", "开机", "短剧 热度"]:
    print(f"-- Tavily: {kw}")
    for r in tavily(kw):
        title = (r.get("title") or "").strip()
        if not title: continue
        if any(w in title for w in ["盘点","影评","十大","必看","回顾"]): continue
        new_items.append({
            "id": "T_" + str(int(time.time()*1000)) + "_" + str(len(new_items)),
            "theme": "short" if "短剧" in title else "long",
            "sub": "日常资讯",
            "source": "Tavily",
            "publish_time": (r.get("published_date") or datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"))[:16],
            "title": title, "summary": (r.get("content") or "")[:80],
            "content": (r.get("content") or title)[:400],
            "tags": ["日常资讯"],
            "source_url": r.get("url") or "",
            "confidence": 0.7
        })
print("Tavily 新增:", len(new_items), "条")

print("=== 4. 微博追踪 ===")
def weibo_search(name):
    import urllib.parse
    q = urllib.parse.quote(name)
    url = f"https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D{q}&page_type=searchall"
    h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
         "Cookie": COOKIE, "X-XSRF-TOKEN": XSRF, "X-Requested-With": "XMLHttpRequest", "Referer": "https://m.weibo.cn/"}
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30).read())
        return d.get("data", {}).get("cards", [])
    except Exception as e:
        print(f"微博 [{name}] 失败: {e}")
        return []

tracking = []
for name in tracked:
    print(f"-- 微博: {name}")
    for card in weibo_search(name):
        for g in card.get("card_group", []):
            mb = g.get("mblog", {})
            text = mb.get("text", "")
            if not text or len(text) < 15: continue
            if not any(w in text for w in ["开机","杀青","定档","开播","上线","预告","花絮","排播","官宣"]): continue
            tracking.append({
                "id": "wb_" + str(mb.get("id", int(time.time()*1000))),
                "theme": "long", "sub": "定向追踪", "source": "微博",
                "publish_time": (mb.get("created_at") or "")[:16],
                "title": text[:40], "summary": text[:60],
                "content": text, "tags": [name], "source_url": f"https://m.weibo.cn/detail/{mb.get('id','')}",
                "confidence": 0.9
            })
    time.sleep(3)
print("微博追踪新增:", len(tracking), "条")

print("=== 5. 合并 + 防覆盖 ===")
all_new = new_items + tracking
print("本次新增:", len(all_new), "条")

if len(all_new) == 0 and len(old_news) > 0:
    print("本次 0 条，保留旧文件不动")
    print("=== ALL DONE (SKIPPED) ===")
    sys.exit(0)

merged = old_news + all_new
seen = set()
final = []
for x in sorted(merged, key=lambda k: k.get("publish_time", ""), reverse=True):
    key = x.get("id") or x.get("title")
    if key in seen: continue
    seen.add(key)
    final.append(x)
final = final[:200]

print("合并后:", len(final), "条")

r = gh_put_json("news.json", final, news_sha, f"daily update {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}")
print("news.json commit:", r["commit"]["sha"])
print("=== ALL DONE ===")
