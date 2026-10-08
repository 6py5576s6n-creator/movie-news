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

weibo_items = []
for show in tracked:
 print(f"-- 微博: {show}")
 cards = weibo_search(show)
 for card in cards:
 text = (card.get("mblog", {}).get("text_raw") or "")
 created = card.get("mblog", {}).get("created_at")
 mid = card.get("mblog", {}).get("mid")
 keywords = ["开播", "播出", "上线", "定档", "开机", "杀青", "预告", "首发", "官宣"]
 match = any(kw in text for kw in keywords)
 if text and len(text) > 15 and match:
 weibo_items.append({
 "id": f"W_{show}_{str(int(time.time()*1000))}_{len(weibo_items)}",
 "theme": "long",
 "sub": "微博追踪",
 "source": "Weibo",
 "publish_time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
 "title": f"{show}: {text[:80]}",
 "summary": text[:200],
 "content": text[:500],
 "tags": [show, "微博"],
 "source_url": f"https://m.weibo.cn/detail/{mid}" if mid else "",
 "confidence": 0.8
 })
print("微博追踪新增:", len(weibo_items), "条")

print("=== 5. 合并去重写入 ===")
all_new = weibo_items + new_items
print("本次新抓总计:", len(all_new), "条")

existing_ids = set(item.get('id', '') for item in old_news)
merged = list(old_news)
added = 0
for item in all_new:
 if item['id'] not in existing_ids:
 merged.append(item)
 existing_ids.add(item['id'])
 added += 1

# Deduplicate by id
seen = set()
unique_merged = []
for item in sorted(merged, key=lambda x: x.get('publish_time', ''), reverse=True):
 iid = item.get('id', '')
 if iid not in seen:
 unique_merged.append(item)
 seen.add(iid)
merged = unique_merged

print("合并后总数:", len(merged))
print("本次实际新增:", added, "条")

try:
 resp = gh_put_json("news.json", merged, news_sha, f"更新影视资讯：{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')} 新增{added}条")
 print("GitHub 提交成功, commit:", resp["commit"]["sha"])
except Exception as e:
 print("GitHub 写入失败:", e)

print("\n=== 各主题统计 ===")
by_theme = {}
for item in merged:
 theme = item.get('theme', 'other')
 by_theme[theme] = by_theme.get(theme, 0) + 1
for k, v in sorted(by_theme.items()):
 print(f" {k}: {v}")

print("\n=== ALL DONE ===")
