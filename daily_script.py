import urllib.request, json, base64, sys, time, re, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

def read_clean(path):
 raw = open(path, "r", encoding="utf-8").read()
 bad = [chr(0x2028), chr(0x2029), chr(0x200b), chr(0x200c), chr(0x200d), chr(0xfeff), chr(0x00a0), chr(13), chr(10)]
 for ch in bad:
  raw = raw.replace(ch, "")
 return raw.strip()

TOKEN = read_clean("/home/openclaw/.openclaw/workspace/github.token")
TAVILY_KEY = "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"
COOKIE = read_clean("/home/openclaw/.openclaw/workspace/weibo.cookie")
XSRF = read_clean("/home/openclaw/.openclaw/workspace/weibo.xsrf")

REPO = "6py5576s6n-creator/movie-news"

def clean_content(text, title):
 if not text:
  return title
 text = re.sub(r'[{]{2}.*?[}]{2}', '', text)
 text = re.sub(r'[{][^{}]*[}]', '', text)
 text = ' '.join(text.split())
 for wd in ["扫描二维码", "访问手机版", "访问移动端", "点击查看", "版权声明", "责任编辑", "更多精彩", "相关新闻："]:
  idx = text.find(wd)
  if idx > 30:
   text = text[:idx]
 text = text.strip()
 if len(text) < 50:
  text = title
 return text

def title_key(t):
 if not t:
  return ""
 return "".join(ch for ch in t if ch.isalnum()).lower()

def is_similar(a, b):
 if not a or not b:
  return False
 return SequenceMatcher(None, a, b).ratio() > 0.85

def normalize_url(u):
 if not u:
  return ""
 try:
  p = urllib.parse.urlparse(u)
  return p.netloc + p.path
 except Exception:
  return u

def gh(method, path, body=None):
 url = "https://api.github.com/repos/" + REPO + "/contents/" + path
 r = urllib.request.Request(url, method=method)
 r.add_header("Authorization", "Bearer " + TOKEN)
 r.add_header("Accept", "application/vnd.github+json")
 r.add_header("Content-Type", "application/json")
 if body:
  r.data = json.dumps(body).encode()
 return json.loads(urllib.request.urlopen(r).read())

def gh_get_json(path):
 try:
  c = gh("GET", path)
  return json.loads(base64.b64decode(c["content"]).decode("utf-8")), c["sha"]
 except Exception as e:
  print("读 " + path + " 失败: " + str(e))
  return None, None

def gh_put_json_retry(path, data, msg):
 for attempt in range(3):
  try:
   c = gh("GET", path)
   sha = c["sha"]
  except Exception:
   sha = None
  body = {"message": msg, "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode()}
  if sha:
   body["sha"] = sha
  try:
   return gh("PUT", path, body)
  except urllib.error.HTTPError as e:
   if e.code == 409 and attempt < 2:
    print("检测到 409，第 " + str(attempt+1) + " 次重试...")
    time.sleep(3)
    continue
   raise
 raise Exception("3 次重试后仍失败")

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
  print("Tavily [" + query + "] 失败: " + str(e))
  return []

new_items = []
for kw in ["电影 定档 2026", "剧集 开机 2026", "国庆档 票房", "AI 电影 开机", "短剧 热度 2026"]:
 print("-- Tavily: " + kw)
 for res in tavily(kw):
  title = (res.get("title") or "").strip()
  if not title:
   continue
  if any(exclude in title for exclude in ["盘点", "影评", "十大", "必看", "回顾"]):
   continue
  raw_content = res.get("content") or ""
  content = clean_content(raw_content, title)
  summary = content[:80] if content else title
  theme = "long"
  if "AI" in title or "ai" in title:
   theme = "ai"
  elif "短剧" in title:
   theme = "short"
  new_items.append({
   "id": "T_" + str(int(time.time() * 1000)) + "_" + str(len(new_items)),
   "theme": theme,
   "sub": "日常资讯",
   "source": "Tavily",
   "publish_time": (res.get("published_date") or datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"))[:16],
   "title": title,
   "summary": summary,
   "content": content,
   "tags": ["日常资讯"],
   "source_url": res.get("url") or "",
   "confidence": 0.7
  })
print("Tavily 新增:", len(new_items), "条")

print("=== 4. 微博追踪 ===")

def weibo_search(name):
 q = urllib.parse.quote(name)
 url = "https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D" + q + "&page_type=searchall"
 h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
  "Cookie": COOKIE, "X-XSRF-TOKEN": XSRF, "X-Requested-With": "XMLHttpRequest", "Referer": "https://m.weibo.cn/"}
 try:
  d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30).read())
  return d.get("data", {}).get("cards", [])
 except Exception as e:
  print("微博 [" + name + "] 失败: " + str(e))
  return []

tracking = []
for name in tracked:
 print("-- 微博: " + name)
 for card in weibo_search(name):
  for g in card.get("card_group", []):
   mb = g.get("mblog", {})
   text = mb.get("text", "")
   if not text or len(text) < 15:
    continue
   if not any(kw in text for kw in ["开机", "杀青", "定档", "开播", "上线", "预告", "花絮", "排播", "官宣"]):
    continue
   tracking.append({
    "id": "wb_" + str(mb.get("id", int(time.time() * 1000))),
    "theme": "long",
    "sub": "定向追踪",
    "source": "微博",
    "publish_time": (mb.get("created_at") or "")[:16],
    "title": text[:40],
    "summary": text[:60],
    "content": clean_content(text, text[:40]),
    "tags": [name],
    "source_url": "https://m.weibo.cn/detail/" + str(mb.get("id", "")),
    "confidence": 0.9
   })
 time.sleep(3)
print("微博追踪新增:", len(tracking), "条")

print("=== 5. 合并 + 去重 + 防覆盖 ===")
all_new = new_items + tracking
print("本次新增:", len(all_new), "条")

if len(all_new) == 0 and len(old_news) > 0:
 print("本次 0 条，保留旧文件不动")
 print("=== ALL DONE (SKIPPED) ===")
 sys.exit(0)

print("写入前重新读取最新 news.json...")
latest_news, latest_sha = gh_get_json("news.json")
if isinstance(latest_news, list) and latest_news:
 old_news = latest_news
 print("已刷新基线:", len(old_news), "条")

merged = old_news + all_new
merged.sort(key=lambda k: k.get("publish_time", ""), reverse=True)

final = []
seen_urls = set()
seen_titles = []
for x in merged:
 url_key = normalize_url(x.get("source_url") or "")
 if url_key and url_key in seen_urls:
  continue
 tk = title_key(x.get("title") or "")
 if tk and any(is_similar(tk, s) for s in seen_titles):
  continue
 if url_key:
  seen_urls.add(url_key)
 if tk:
  seen_titles.append(tk)
 final.append(x)

final = final[:200]
print("合并后:", len(final), "条 (去掉了 " + str(len(merged) - len(final)) + " 条重复)")

r = gh_put_json_retry("news.json", final, "daily update " + datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"))
print("news.json commit:", r["commit"]["sha"])
print("=== ALL DONE ===")
