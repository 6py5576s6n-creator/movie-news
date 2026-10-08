import urllib.request, json, base64, re, html as html_lib, sys, urllib.error
from datetime import datetime, timezone, timedelta

def read_clean(path):
    raw = open(path, "r", encoding="utf-8").read()
    raw = re.sub(r"[\u2028\u2029\u200b\u200c\u200d\ufeff\u00a0]", "", raw)
    raw = raw.replace("\r", "").replace("\n", "")
    return raw.strip()

TOKEN = read_clean("/home/openclaw/.openclaw/workspace/github.token")
COOKIE = read_clean("/home/openclaw/.openclaw/workspace/weibo.cookie")
XSRF = read_clean("/home/openclaw/.openclaw/workspace/weibo.xsrf")

REPO = "6py5576s6n-creator/movie-news"
PATH = "hotsearch.json"
HISTORY_PATH = "hotsearch_history.json"

H = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cookie": COOKIE,
    "X-XSRF-TOKEN": XSRF,
    "Referer": "https://weibo.com/"
}

def fetch(url, ref):
    h = dict(H)
    h["Referer"] = ref
    req = urllib.request.Request(url, headers=h)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.getcode(), resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)

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

def gh_put_json(path, data, sha, msg):
    body = {
        "message": msg,
        "content": base64.b64encode(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode()
    }
    if sha:
        body["sha"] = sha
    return gh("PUT", path, body)

print("=== 1. 抓热搜总榜 ===")
hot = []
code, raw = fetch("https://weibo.com/ajax/side/hotSearch", "https://weibo.com/")
print("HTTP 状态:", code)
print("返回长度:", len(raw))
if code == 200 and raw:
    try:
        data = json.loads(raw)
        rt = data.get("data", {}).get("realtime", [])
        print("原始条数:", len(rt))
        for i, it in enumerate(rt, 1):
            hot.append({
                "rank": i,
                "title": (it.get("word") or "").strip("# "),
                "hot": int(it.get("num") or 0),
                "label": it.get("label_name") or ""
            })
    except Exception as e:
        print("JSON 解析失败: " + str(e))
        print("返回前 200 字符: " + raw[:200])
else:
    print("返回前 200 字符: " + raw[:200])

print("=== 2. 抓文娱榜 ===")
ent = []
code, raw = fetch("https://s.weibo.com/top/summary?cate=entrank", "https://s.weibo.com/")
print("HTTP 状态:", code)
print("返回长度:", len(raw))
if code == 200 and raw:
    try:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
        print("tr 行数:", len(rows))
        for row in rows:
            mr = re.search(r'<td class="td-01[^"]*">\s*(\d+)\s*</td>', row)
            if not mr:
                continue
            mt = re.search(r'<td class="td-02">\s*<a[^>]*>(.*?)</a>', row, re.DOTALL)
            if not mt:
                continue
            title = html_lib.unescape(re.sub(r'<[^>]+>', '', mt.group(1)).strip())
            mh = re.search(r'<span[^>]*>(\d+)</span>', row)
            ml = re.search(r'<td class="td-03">(.*?)</td>', row, re.DOTALL)
            label = html_lib.unescape(re.sub(r'<[^>]+>', '', ml.group(1)).strip()) if ml else ""
            ent.append({
                "rank": int(mr.group(1)),
                "title": title,
                "hot": int(mh.group(1)) if mh else 0,
                "label": label
            })
    except Exception as e:
        print("HTML 解析失败: " + str(e))

print("=== 3. 抓取结果 ===")
print("hot =", len(hot), " ent =", len(ent))

print("=== 4. 读取旧文件 ===")
old, old_sha = gh_get_json(PATH)
oh = len(old.get("hot", [])) if old else 0
oe = len(old.get("ent", [])) if old else 0
print("旧文件: hot=" + str(oh) + " ent=" + str(oe))

print("=== 5. 防覆盖 ===")
skip = False
reason = ""
if oh > 0 and len(hot) < oh * 0.5:
    skip = True
    reason = "new hot " + str(len(hot)) + " < old " + str(oh) + " 的 50%"
elif oe > 0 and len(ent) < oe * 0.5:
    skip = True
    reason = "new ent " + str(len(ent)) + " < old " + str(oe) + " 的 50%"
elif len(hot) == 0 and len(ent) == 0:
    skip = True
    reason = "新旧数据都为空"

if skip:
    print("跳过写入：" + reason)
    print("=== ALL DONE (SKIPPED) ===")
    sys.exit(0)

print("校验通过: hot " + str(oh) + "->" + str(len(hot)) + ", ent " + str(oe) + "->" + str(len(ent)))

now = datetime.now(timezone(timedelta(hours=8)))
result = {
    "updated_at": now.strftime("%Y-%m-%d %H:%M"),
    "hot": hot,
    "ent": ent
}

r = gh_put_json(PATH, result, old_sha, "update hotsearch " + result["updated_at"])
print("hotsearch commit:", r["commit"]["sha"])

with open("/home/openclaw/.openclaw/workspace/hotsearch.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

oh2, hs = gh_get_json(HISTORY_PATH)
if not oh2 or not isinstance(oh2.get("records"), list):
    oh2 = {"records": []}
oh2["records"].append({
    "updated_at": result["updated_at"],
    "hot_count": len(hot),
    "ent_count": len(ent),
    "hot": hot,
    "ent": ent
})
oh2["records"] = oh2["records"][-50:]
r2 = gh_put_json(HISTORY_PATH, oh2, hs, "append " + result["updated_at"])
print("history commit:", r2["commit"]["sha"])
print("history 总数:", len(oh2["records"]))

print("=== ALL DONE ===")
