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
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response

app = Flask(__name__)

# --- কনফিগারেশন ---
CLONE_DIR = "cloned_repos"
DATA_FILE = "bots_data.json"  

if not os.path.exists(CLONE_DIR):
    os.makedirs(CLONE_DIR)

# মেমোরি স্টোরেজ 
running_processes = {}   
deployment_status = {}   
bot_configs = {}         

# --- ডাটাবেস লোড এবং সেভ ফাংশন ---
def load_data():
    global bot_configs
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                bot_configs = json.load(f)
        except:
            bot_configs = {}
    else:
        bot_configs = {}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(bot_configs, f, indent=4)
    except Exception as e:
        print(f"Error saving data: {e}")

# স্ট্যান্ডার্ড লাইব্রেরি
STANDARD_LIBS = {
    "os", "sys", "time", "json", "math", "random", "datetime", "subprocess", "threading",
    "collections", "re", "ftplib", "http", "urllib", "email", "shutil", "logging", "typing",
    "traceback", "asyncio", "html", "socket", "base64", "io", "platform", "signal", "flask"
}

PIP_MAPPING = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "dotenv": "python-dotenv",
    "discord": "discord.py",
    "aiogram": "aiogram",
    "googleapiclient": "google-api-python-client",
    "youtube_dl": "youtube_dl",
    "yt_dlp": "yt_dlp",
    "pymongo": "pymongo[srv]"
}

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

def get_imports_from_folder(folder_path):
    imports = set()
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".py"):
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8", errors="ignore") as f:
                        tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imports.add(alias.name.split('.')[0])
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.add(node.module.split('.')[0])
                except:
                    pass
    return imports

def pull_latest_code(folder_name):
    """গিটহাব থেকে নতুন আপডেট নেওয়ার ফাংশন"""
    repo_path = os.path.join(CLONE_DIR, folder_name)
    if os.path.exists(os.path.join(repo_path, ".git")):
        deployment_status[folder_name] = "🔄 Pulling Latest Code..."
        try:
            # লোকাল কোন পরিবর্তন থাকলে মুছে দিয়ে গিটহাবের সাথে সিঙ্ক করা
            subprocess.run(["git", "reset", "--hard"], cwd=repo_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "pull"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # requirements.txt চেক করা এবং আপডেট করা
            req_file = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(req_file):
                deployment_status[folder_name] = "📦 Updating Packages..."
                subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error updating repo {folder_name}: {e}")
            deployment_status[folder_name] = "⚠️ Update Failed (Running Old Code)"
            time.sleep(2)

def run_bot_process(folder_name):
    """বট স্টার্ট করার ফাংশন"""
    repo_path = os.path.join(CLONE_DIR, folder_name)
    config = bot_configs.get(folder_name, {})
    
    start_file = config.get("start_file", "main.py")
    assigned_port = config.get("port", str(random.randint(5001, 9999)))
    custom_env_vars = config.get("env", {}) 

    run_path = os.path.join(repo_path, start_file)
    if not os.path.exists(run_path):
        deployment_status[folder_name] = "⚠️ Start File Missing"
        return

    if folder_name in running_processes and running_processes[folder_name].poll() is None:
        return

    deployment_status[folder_name] = f"🚀 Starting on Port {assigned_port}..."
    
    bot_env = os.environ.copy()
    bot_env.update(custom_env_vars)
    bot_env["PORT"] = str(assigned_port)
    
    log_file_path = os.path.join(repo_path, "bot_logs.txt")
    
    try:
        log_file = open(log_file_path, "a", encoding="utf-8")
        
        proc = subprocess.Popen(
            ["python", start_file],
            cwd=repo_path,
            env=bot_env,
            stdout=log_file,
            stderr=log_file
        )
        running_processes[folder_name] = proc
        
        time.sleep(5)
        if proc.poll() is None:
            deployment_status[folder_name] = f"Running 🟢 (Port: {assigned_port})"
        else:
            deployment_status[folder_name] = "❌ Crashed (View bot_logs.txt)"
            
    except Exception as e:
        deployment_status[folder_name] = f"❌ Error: {str(e)}"

def install_and_run(repo_link, start_file, folder_name, custom_port, env_text):
    repo_path = os.path.join(CLONE_DIR, folder_name)
    port_to_use = custom_port if custom_port else str(random.randint(5001, 9999))
    
    env_vars = parse_env_text(env_text)

    bot_configs[folder_name] = {
        "link": repo_link,
        "start_file": start_file,
        "port": port_to_use,
        "env": env_vars
    }
    save_data() 

    try:
        if not os.path.exists(repo_path):
            deployment_status[folder_name] = "⬇️ Cloning Repo..."
            subprocess.run(["git", "clone", repo_link, repo_path], check=True)
        
        req_file = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(req_file):
            deployment_status[folder_name] = "📦 Installing Requirements..."
            subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, stdout=subprocess.DEVNULL)
        else:
            deployment_status[folder_name] = "🔍 Smart Scanning..."
            detected_imports = get_imports_from_folder(repo_path)
            packages_to_install =[]
            for lib in detected_imports:
                if lib not in STANDARD_LIBS and not lib.startswith("_"):
                    packages_to_install.append(PIP_MAPPING.get(lib, lib))
            
            if packages_to_install:
                deployment_status[folder_name] = f"📦 Auto-Installing Libs..."
                subprocess.run(["pip", "install"] + packages_to_install, cwd=repo_path, stdout=subprocess.DEVNULL)

        run_path = os.path.join(repo_path, start_file)
        if not os.path.exists(run_path):
            possible_files =["app.py", "main.py", "bot.py", "start.py", "run.py"]
            for f in possible_files:
                if os.path.exists(os.path.join(repo_path, f)):
                    start_file = f
                    bot_configs[folder_name]["start_file"] = f
                    save_data() 
                    break
        
        run_bot_process(folder_name)

    except Exception as e:
        print(f"Error: {e}")
        deployment_status[folder_name] = "❌ Error Occurred"

# --- আগের সেশন রিস্টোর করা ---
def restore_sessions():
    time.sleep(2) 
    print("🔄 Restoring previous sessions...")
    load_data() 
    for folder_name in bot_configs:
        path = os.path.join(CLONE_DIR, folder_name)
        if os.path.exists(path):
            threading.Thread(target=run_bot_process, args=(folder_name,)).start()
        else:
            print(f"⚠️ Folder missing for {folder_name}, skipping.")

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/view/<folder_name>/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/view/<folder_name>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_view(folder_name, path):
    config = bot_configs.get(folder_name)
    if not config:
        return "Bot config not found!", 404
        
    port = config.get("port")
    base_url = f"http://127.0.0.1:{port}"
    target_url = f"{base_url}/{path}"
    if request.query_string: target_url += f"?{request.query_string.decode('utf-8')}"

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for (key, value) in request.headers if key.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False
        )
        if resp.status_code in[301, 302, 303, 307, 308]:
            location = resp.headers.get('Location')
            if location:
                if base_url in location: location = location.replace(base_url, "")
                new_loc = f"/view/{folder_name}{location}" if location.startswith("/") else f"/view/{folder_name}/{location}"
                return redirect(new_loc, code=resp.status_code)

        excluded_headers =['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'location']
        headers =[(name, value) for (name, value) in resp.headers.items() if name.lower() not in excluded_headers]

        content = resp.content
        if 'text/html' in resp.headers.get('Content-Type', ''):
            decoded_content = content.decode('utf-8', errors='ignore')
            decoded_content = decoded_content.replace('href="/', f'href="/view/{folder_name}/')
            decoded_content = decoded_content.replace('src="/', f'src="/view/{folder_name}/')
            decoded_content = decoded_content.replace('action="/', f'action="/view/{folder_name}/')
            decoded_content = decoded_content.replace("action='/", f"action='/view/{folder_name}/")
            content = decoded_content.encode('utf-8')

        return Response(content, resp.status_code, headers)
    except Exception as e:
        return f"Proxy Error (Bot might be stopped): {e}", 502

@app.route('/status')
def status_api():
    bots_data =[]
    for folder, config in bot_configs.items():
        current_status = deployment_status.get(folder, "Unknown")
        is_running = False
        
        if folder in running_processes:
            if running_processes[folder].poll() is None:
                current_status = deployment_status.get(folder, "Running 🟢")
                is_running = True
            else:
                current_status = "Stopped 🔴"
        else:
            current_status = deployment_status.get(folder, "Stopped 🔴")

        bots_data.append({
            "name": folder,
            "status": current_status,
            "running": is_running,
            "port": config.get("port", "N/A")
        })
    return jsonify(bots_data)

@app.route('/get_config/<folder_name>')
def get_config(folder_name):
    config = bot_configs.get(folder_name, {})
    env_vars = config.get("env", {})
    env_text = "\n".join([f"{k}={v}" for k, v in env_vars.items()])
    return jsonify({"env": env_text})

@app.route('/update_config/<folder_name>', methods=['POST'])
def update_config(folder_name):
    if folder_name in bot_configs:
        env_text = request.form.get("env_vars", "")
        bot_configs[folder_name]["env"] = parse_env_text(env_text)
        save_data()
        return "Updated", 200
    return "Not Found", 404

@app.route('/deploy', methods=['POST'])
def deploy():
    repo_link = request.form.get('repo_link')
    start_file = request.form.get('start_file') or "main.py"
    custom_port = request.form.get('custom_port')
    env_text = request.form.get('env_vars')
    
    if not repo_link: return "Link Required", 400
    
    repo_link = clean_url(repo_link)
    folder_name = repo_link.split("/")[-1].replace(".git", "")

    if folder_name in running_processes and running_processes[folder_name].poll() is None:
        return "Already Running", 400

    deployment_status[folder_name] = "⏳ Queued..."
    thread = threading.Thread(target=install_and_run, args=(repo_link, start_file, folder_name, custom_port, env_text))
    thread.start()

    return redirect(url_for('home'))

@app.route('/start/<folder_name>')
def start_bot(folder_name):
    """স্টার্ট করার আগে নতুন কোড পুশ করবে"""
    if folder_name not in running_processes or running_processes[folder_name].poll() is not None:
        deployment_status[folder_name] = "⏳ Preparing to Start..."
        
        def start_task():
            pull_latest_code(folder_name)
            run_bot_process(folder_name)
            
        thread = threading.Thread(target=start_task)
        thread.start()
    return redirect(url_for('home'))

@app.route('/update/<folder_name>')
def update_bot(folder_name):
    """স্টপ করে, আপডেট নিয়ে তারপর স্টার্ট করবে"""
    deployment_status[folder_name] = "🔄 Updating & Restarting..."
    
    def update_task():
        # বট রানিং থাকলে আগে স্টপ করা হবে
        if folder_name in running_processes:
            try:
                running_processes[folder_name].terminate()
                running_processes[folder_name].wait(timeout=2)
            except:
                running_processes[folder_name].kill()
            del running_processes[folder_name]
        
        # গিটহাব থেকে পুল করা হবে
        pull_latest_code(folder_name)
        # পুনরায় চালু করা হবে
        run_bot_process(folder_name)
        
    thread = threading.Thread(target=update_task)
    thread.start()
    return redirect(url_for('home'))

@app.route('/stop/<folder_name>')
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
def delete_bot(folder_name):
    if folder_name in running_processes:
        stop_bot(folder_name)
    repo_path = os.path.join(CLONE_DIR, folder_name)
    if os.path.exists(repo_path):
        try:
            shutil.rmtree(repo_path)
        except:
            pass
    if folder_name in deployment_status: del deployment_status[folder_name]
    if folder_name in bot_configs: 
        del bot_configs[folder_name]
        save_data() 
    return redirect(url_for('home'))

if __name__ == "__main__":
    threading.Thread(target=restore_sessions).start()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
