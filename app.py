import os
import sys
import subprocess
import shutil
import threading
import ast
import time
import random
import requests
import json
import psutil
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response

app = Flask(__name__)

# --- সিকিউরিটি (লগিন সিস্টেম) ---
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def authenticate():
    return Response(
    'Login Required! 🔐\nProvide proper credentials to access the Ultimate Bot Manager.', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- কনফিগারেশন ---
CLONE_DIR = "cloned_repos"
DATA_FILE = "bots_data.json"
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mahap83280:mahap83280@cluster0.a7cnaha.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") 

if not os.path.exists(CLONE_DIR):
    os.makedirs(CLONE_DIR)

# মেমোরি স্টোরেজ 
running_processes = {}   
deployment_status = {}   
bot_configs = {}         

# --- ডাটাবেস সেটআপ (MongoDB + JSON Fallback) ---
HAS_MONGO = False
collection = None

if MONGO_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI)
        db = client["ultimate_bot_manager"]
        collection = db["bot_configs"]
        HAS_MONGO = True
        print("✅ MongoDB Connected! Recovery system active.")
    except Exception as e:
        print(f"❌ MongoDB Connection Failed: {e}")

def load_data():
    global bot_configs
    if HAS_MONGO:
        try:
            bot_configs = {}
            for doc in collection.find():
                bot_configs[doc["_id"]] = doc["config"]
        except: pass
    else:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    bot_configs = json.load(f)
            except: bot_configs = {}

def save_data(name=None):
    if HAS_MONGO and collection is not None:
        try:
            if name: # নির্দিষ্ট একটি বট সেভ করা
                collection.update_one({"_id": name}, {"$set": {"config": bot_configs[name]}}, upsert=True)
            else: # সব বট সেভ করা
                for n, config in bot_configs.items():
                    collection.update_one({"_id": n}, {"$set": {"config": config}}, upsert=True)
        except Exception as e: print(f"DB Error: {e}")
    else:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(bot_configs, f, indent=4)
        except Exception as e: print(f"File Error: {e}")

# --- হেল্পার ফাংশন ---
def clean_url(url): 
    return url.strip().rstrip("/")

def parse_env_text(text):
    env_vars = {}
    if not text: return env_vars
    for line in text.split('\n'):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            env_vars[key.strip()] = value.strip()
    return env_vars

def pull_latest_code(folder_name):
    repo_path = os.path.join(CLONE_DIR, folder_name)
    if os.path.exists(os.path.join(repo_path, ".git")):
        deployment_status[folder_name] = "🔄 Pulling Latest Code..."
        try:
            subprocess.run(["git", "reset", "--hard"], cwd=repo_path, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "pull"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL)
            if os.path.exists(os.path.join(repo_path, "requirements.txt")):
                deployment_status[folder_name] = "📦 Updating Packages..."
                subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, stdout=subprocess.DEVNULL)
        except: deployment_status[folder_name] = "⚠️ Update Failed"

def run_bot_process(folder_name):
    repo_path = os.path.join(CLONE_DIR, folder_name)
    config = bot_configs.get(folder_name, {})
    
    start_file = config.get("start_file", "main.py")
    assigned_port = config.get("port", str(random.randint(5001, 9999)))
    
    run_path = os.path.join(repo_path, start_file)
    if not os.path.exists(run_path):
        deployment_status[folder_name] = "⚠️ Start File Missing"
        return

    if folder_name in running_processes and running_processes[folder_name].poll() is None:
        return

    deployment_status[folder_name] = f"🚀 Starting..."
    bot_env = os.environ.copy()
    bot_env.update(config.get("env", {}))
    bot_env["PORT"] = str(assigned_port)
    
    log_file_path = os.path.join(repo_path, "bot_logs.txt")
    try:
        log_file = open(log_file_path, "a", encoding="utf-8")
        proc = subprocess.Popen(["python", start_file], cwd=repo_path, env=bot_env, stdout=log_file, stderr=subprocess.STDOUT)
        running_processes[folder_name] = proc
        time.sleep(3)
        if proc.poll() is None: 
            deployment_status[folder_name] = f"Running 🟢"
        else: 
            deployment_status[folder_name] = "❌ Crashed"
    except Exception as e:
        deployment_status[folder_name] = f"❌ Error: {str(e)}"

def install_and_run(repo_link, start_file, folder_name, custom_port, env_text):
    repo_path = os.path.join(CLONE_DIR, folder_name)
    env_vars = parse_env_text(env_text)

    # কনফিগারেশন সেভ
    bot_configs[folder_name] = {
        "link": repo_link, "start_file": start_file, 
        "port": custom_port if custom_port else str(random.randint(5001, 9999)), "env": env_vars
    }
    save_data(folder_name) 

    try:
        if not os.path.exists(repo_path):
            deployment_status[folder_name] = "⬇️ Cloning Repo..."
            subprocess.run(["git", "clone", repo_link, repo_path], check=True)
        
        if os.path.exists(os.path.join(repo_path, "requirements.txt")):
            deployment_status[folder_name] = "📦 Installing Requirements..."
            subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, stdout=subprocess.DEVNULL)

        run_bot_process(folder_name)
    except Exception as e:
        deployment_status[folder_name] = f"❌ Setup Failed: {e}"

# --- অটো-রিস্টার্ট এবং রিস্টোরেশন লজিক ---
def auto_recovery_and_monitor():
    """সার্ভার রিস্টার্ট হলে সব রিস্টোর করবে এবং ক্র্যাশ হলে রিস্টার্ট করবে"""
    print("🔄 Initializing Recovery System...")
    time.sleep(5)
    load_data() 
    
    # রিস্টোরেশন
    for folder_name, config in list(bot_configs.items()):
        path = os.path.join(CLONE_DIR, folder_name)
        if not os.path.exists(path):
            print(f"📦 Re-cloning missing bot: {folder_name}")
            env_text = "\n".join([f"{k}={v}" for k, v in config.get("env", {}).items()])
            threading.Thread(target=install_and_run, args=(config['link'], config['start_file'], folder_name, config['port'], env_text)).start()
        else:
            threading.Thread(target=run_bot_process, args=(folder_name,)).start()
        time.sleep(2) # গ্যাপ রাখা যাতে মেমোরি লোড না হয়

    # মনিটরিং লুপ
    while True:
        time.sleep(20)
        for folder, proc in list(running_processes.items()):
            if proc.poll() is not None:
                if "Stopped" not in deployment_status.get(folder, "") and "Deleted" not in deployment_status.get(folder, ""):
                    run_bot_process(folder)

# --- ROUTES ---

@app.route('/')
@requires_auth
def home():
    return render_template('index.html')

@app.route('/status')
@requires_auth
def status_api():
    bots_data =[]
    for folder, config in bot_configs.items():
        current_status = deployment_status.get(folder, "Unknown")
        is_running = False
        ram_usage = "0"
        cpu_usage = "0.0"
        
        if folder in running_processes and running_processes[folder].poll() is None:
            is_running = True
            current_status = deployment_status.get(folder, "Running 🟢")
            try:
                proc = psutil.Process(running_processes[folder].pid)
                ram_usage = str(round(proc.memory_info().rss / (1024 * 1024), 1))
                cpu_usage = str(round(proc.cpu_percent(interval=0.1), 1))
            except: pass
        else:
            if "Running" in current_status: current_status = "Stopped 🔴"

        bots_data.append({
            "name": folder, "status": current_status, "running": is_running,
            "port": config.get("port", "N/A"), "ram": ram_usage, "cpu": cpu_usage
        })
    return jsonify(bots_data)

@app.route('/logs/<folder_name>')
@requires_auth
def get_logs(folder_name):
    log_file = os.path.join(CLONE_DIR, folder_name, "bot_logs.txt")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                return "".join(f.readlines()[-100:])
        except: return "Error reading logs."
    return "No logs found."

@app.route('/deploy', methods=['POST'])
@requires_auth
def deploy():
    repo_link = clean_url(request.form.get('repo_link'))
    start_file = request.form.get('start_file') or "main.py"
    custom_port = request.form.get('custom_port')
    env_text = request.form.get('env_vars')
    folder_name = repo_link.split("/")[-1].replace(".git", "")

    deployment_status[folder_name] = "⏳ Queued..."
    threading.Thread(target=install_and_run, args=(repo_link, start_file, folder_name, custom_port, env_text)).start()
    return redirect(url_for('home'))

@app.route('/start/<folder_name>')
@requires_auth
def start_bot(folder_name):
    threading.Thread(target=run_bot_process, args=(folder_name,)).start()
    return redirect(url_for('home'))

@app.route('/update/<folder_name>')
@requires_auth
def update_bot(folder_name):
    deployment_status[folder_name] = "🔄 Updating..."
    def update_task():
        stop_bot(folder_name)
        pull_latest_code(folder_name)
        run_bot_process(folder_name)
    threading.Thread(target=update_task).start()
    return redirect(url_for('home'))

@app.route('/stop/<folder_name>')
@requires_auth
def stop_bot(folder_name):
    if folder_name in running_processes:
        try:
            running_processes[folder_name].terminate()
            running_processes[folder_name].wait(timeout=2) 
        except:
            running_processes[folder_name].kill()
        del running_processes[folder_name]
    deployment_status[folder_name] = "Stopped 🔴"
    return redirect(url_for('home'))

@app.route('/delete/<folder_name>')
@requires_auth
def delete_bot(folder_name):
    stop_bot(folder_name)
    repo_path = os.path.join(CLONE_DIR, folder_name)
    if os.path.exists(repo_path):
        try: shutil.rmtree(repo_path)
        except: pass
    if folder_name in deployment_status: del deployment_status[folder_name]
    if folder_name in bot_configs: 
        del bot_configs[folder_name]
        if HAS_MONGO: collection.delete_one({"_id": folder_name})
        save_data()
    return redirect(url_for('home'))

@app.route('/get_config/<folder_name>')
@requires_auth
def get_config(folder_name):
    config = bot_configs.get(folder_name, {})
    env_vars = config.get("env", {})
    env_text = "\n".join([f"{k}={v}" for k, v in env_vars.items()])
    return jsonify({"env": env_text})

@app.route('/update_config/<folder_name>', methods=['POST'])
@requires_auth
def update_config(folder_name):
    if folder_name in bot_configs:
        env_text = request.form.get("env_vars", "")
        bot_configs[folder_name]["env"] = parse_env_text(env_text)
        save_data(folder_name)
        return "Updated", 200
    return "Not Found", 404

# --- PROXY VIEW (বটের ওয়েব ভার্সন দেখার জন্য) ---
@app.route('/view/<folder_name>/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/view/<folder_name>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_view(folder_name, path):
    config = bot_configs.get(folder_name)
    if not config: return "Bot config not found!", 404
        
    port = config.get("port")
    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.query_string: target_url += f"?{request.query_string.decode('utf-8')}"

    try:
        resp = requests.request(
            method=request.method, url=target_url,
            headers={key: value for (key, value) in request.headers if key.lower() != 'host'},
            data=request.get_data(), cookies=request.cookies, allow_redirects=False
        )
        excluded_headers =['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers =[(name, value) for (name, value) in resp.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return f"Proxy Error: Bot might be stopped or not running on port {port}.", 502

if __name__ == "__main__":
    # রিকভারি এবং মনিটর একসাথে শুরু হবে
    threading.Thread(target=auto_recovery_and_monitor, daemon=True).start()
    
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
