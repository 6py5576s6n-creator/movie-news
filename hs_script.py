import urllib.request, json, base64, re, html as html_lib, sys, os
from datetime import datetime, timezone, timedelta

TOKEN = open("/home/openclaw/.openclaw/workspace/github.token").read().strip()
COOKIE = open("/home/openclaw/.openclaw/workspace/weibo.cookie").read().strip()
XSRF = open("/home/openclaw/.openclaw/workspace/weibo.xsrf").read().strip()

REPO = "6py5576s6n-creator/movie-news"
PATH = "hotsearch.json"
HISTORY_PATH = "hotsearch_history.json"

H = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cookie": COOKIE,
    "X-XSRF-TOKEN": XSRF,
    "Referer": "https://weibo.com/"
}

def fetch(url, ref="https://weibo.com/"):
    h = dict(H); h["Referer"] = ref
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30).read().decode("utf-8", errors="ignore")

def gh(method, url, body=None):
    r = urllib.request.Request(url, method=method)
    r.add_header("Authorization", f"Bearer {TOKEN}")
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("Content-Type", "application/json")
    if body: r.data = json.dumps(body).encode()
    return json.loads(urllib.request.urlopen(r).read())

def gh_get(p):
    try:
        c = gh("GET", f"https://api.github.com/repos/{REPO}/contents/{p}")
        return json.loads(base64.b64decode(c["content"]).decode("utf-8")), c["sha"]
    except Exception:
        return None, None

def gh_put(p, data, sha, msg):
    body = {"message": msg, "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode()}
    if sha: body["sha"] = sha
    return gh("PUT", f"https://api.github.com/repos/{REPO}/contents/{p}", body)

print("=== 抓热搜总榜 ===")
hot = []
try:
    data = json.loads(fetch("https://weibo.com/ajax/side/hotSearch"))
    rt = data.get("data", {}).get("realtime", [])
    print("原始条数:", len(rt))
    for i, it in enumerate(rt, 1):
        hot.append({"rank": i, "title": (it.get("word") or "").strip("# "), "hot": int(it.get("num") or 0), "label": it.get("label_name") or ""})
except Exception as e:
    print("总榜失败:", str(e))

print("=== 抓文娱榜 ===")
ent = []
try:
    raw = fetch("https://s.weibo.com/top/summary?cate=entrank", ref="https://s.weibo.com/")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
    print("tr 行数:", len(rows))
    for row in rows:
        mr = re.search(r'<td class="td-01[^"]*">\s*(\d+)\s*</td>', row)
        if not mr: continue
        mt = re.search(r'<td class="td-02">\s*<a[^>]*>(.*?)</a>', row, re.DOTALL)
        if not mt: continue
        title = html_lib.unescape(re.sub(r'<[^>]+>', '', mt.group(1)).strip())
        mh = re.search(r'<span[^>]*>(\d+)</span>', row)
        ml = re.search(r'<td class="td-03">(.*?)</td>', row, re.DOTALL)
        label = html_lib.unescape(re.sub(r'<[^>]+>', '', ml.group(1)).strip()) if ml else ""
        ent.append({"rank": int(mr.group(1)), "title": title, "hot": int(mh.group(1)) if mh else 0, "label": label})
except Exception as e:
    print("文娱榜失败:", str(e))

print("抓取结果: hot =", len(hot), " ent =", len(ent))

print("=== 读取现有数据 ===")
old, old_sha = gh_get(PATH)
oh, oe = (len(old.get("hot", [])), len(old.get("ent", []))) if old else (0, 0)
print(f"旧文件: hot={oh} ent={oe}")

print("=== 防覆盖校验 ===")
skip = False
reason = ""
if oh > 0 and len(hot) < oh * 0.5: skip = True; reason = f"new hot {len(hot)} < old {oh} 的50%"
elif oe > 0 and len(ent) < oe * 0.5: skip = True; reason = f"new ent {len(ent)} < old {oe} 的50%"
elif len(hot) == 0 and len(ent) == 0: skip = True; reason = "新旧数据都为空"

if skip:
    print(f"跳过写入：{reason}")
    print("=== 保留现有 hotsearch.json ===")
    print("=== ALL DONE (SKIPPED) ===")
    sys.exit(0)

print(f"校验通过: hot {oh}->{len(hot)}, ent {oe}->{len(ent)}")

now = datetime.now(timezone(timedelta(hours=8)))
result = {"updated_at": now.strftime("%Y-%m-%d %H:%M"), "hot": hot, "ent": ent}

r = gh_put(PATH, result, old_sha, f"update {result['updated_at']}")
print("hotsearch commit:", r["commit"]["sha"])

with open("/home/openclaw/.openclaw/workspace/hotsearch.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

oh2, hs = gh_get(HISTORY_PATH)
if not oh2 or not isinstance(oh2.get("records"), list): oh2 = {"records": []}
oh2["records"].append({"updated_at": result["updated_at"], "hot_count": len(hot), "ent_count": len(ent), "hot": hot, "ent": ent})
oh2["records"] = oh2["records"][-50:]
r2 = gh_put(HISTORY_PATH, oh2, hs, f"append {result['updated_at']}")
print("history commit:", r2["commit"]["sha"])
print("history 总数:", len(oh2["records"]))
print("=== ALL DONE ===")
