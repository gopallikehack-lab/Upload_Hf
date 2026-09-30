import os, re, json, requests
from flask import Flask, request
from huggingface_hub import HfApi

app = Flask(__name__)
TOKEN = os.environ["BOT_TOKEN"]
REPO = "gopallikehack/Skills_Lecture"
API = f"https://api.telegram.org/bot{TOKEN}"
hf = HfApi(token=os.environ["HF_TOKEN"])
RU, RT = os.environ["UPSTASH_REDIS_REST_URL"], os.environ["UPSTASH_REDIS_REST_TOKEN"]

def redis(*cmd):
    r = requests.post(RU, headers={"Authorization": f"Bearer {RT}"}, json=list(cmd))
    return r.json().get("result")

def send(chat, text):
    requests.post(f"{API}/sendMessage",
                  json={"chat_id": chat, "text": text, "parse_mode": "HTML"})

def get_file(msg):
    for k in ("document", "video", "audio", "voice", "photo"):
        if k in msg:
            f = msg[k][-1] if k == "photo" else msg[k]
            name = f.get("file_name") or ("photo.jpg" if k == "photo" else k)
            return f["file_id"], name
    return None

@app.route("/", defaults={"p": ""}, methods=["POST", "GET"])
@app.route("/<path:p>", methods=["POST", "GET"])
def webhook(p):
    if request.method == "GET":
        return "Bot is live"
    msg = (request.get_json() or {}).get("message")
    if not msg:
        return "ok"
    chat, uid = msg["chat"]["id"], msg["from"]["id"]
    key = f"pending:{uid}"

    f = get_file(msg)
    if f:
        redis("SET", key, json.dumps({"id": f[0], "name": f[1]}), "EX", 600)
        send(chat, "📝 File mil gayi! Ab iska <b>Title</b> bhejo.")
        return "ok"

    text = msg.get("text", "")
    pending = redis("GET", key)
    if not pending or text.startswith("/"):
        if text.startswith("/start"):
            send(chat, "File forward karo, main HF dataset mai upload kar dunga 🚀")
        return "ok"

    data = json.loads(pending)
    ext = os.path.splitext(data["name"])[1]
    title = re.sub(r'[\\/:*?"<>|]', "", text).strip()[:100] or "untitled"
    send(chat, "⏳ Uploading...")
    try:
        info = requests.get(f"{API}/getFile", params={"file_id": data["id"]}).json()
        path = info["result"]["file_path"]
        content = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}").content
        hf.upload_file(path_or_fileobj=content, path_in_repo=f"{title}{ext}",
                       repo_id=REPO, repo_type="dataset",
                       commit_message=f"Add {title}{ext}")
        redis("DEL", key)
        send(chat, f"✅ Uploaded: <b>{title}{ext}</b>\n"
                   f"https://huggingface.co/datasets/{REPO}/blob/main/{title}{ext}")
    except Exception as e:
        send(chat, f"❌ Failed: {e}")
    return "ok"
