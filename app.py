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
import signal
import psutil  # Server RAM/CPU monitor
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- সিকিউরিটি (Login System) ---
auth = HTTPBasicAuth()
users = {
    "admin": generate_password_hash("admin123")  # আপনার ইউজারনেম ও পাসওয়ার্ড (পরিবর্তন করতে পারেন)
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# --- কনফিগারেশন ---
CLONE_DIR = "cloned_repos"
DATA_FILE = "bots_data.json"

if not os.path.exists(CLONE_DIR):
    os.makedirs(CLONE_DIR)

running_processes = {}   
deployment_status = {}   
bot_configs = {}         

# --- ডাটাবেস লোড এবং সেভ ---
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

def run_bot_process(folder_name):
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
        
        # Cross-platform process setup
        kwargs = {}
        if os.name == 'posix':
            kwargs['preexec_fn'] = os.setsid
            
        proc = subprocess.Popen(
            ["python", start_file],
            cwd=repo_path,
            env=bot_env,
            stdout=log_file,
            stderr=log_file,
            **kwargs
        )
        running_processes[folder_name] = proc
        
        time.sleep(5)
        if proc.poll() is None:
            deployment_status[folder_name] = f"Running 🟢 (Port: {assigned_port})"
        else:
            deployment_status[folder_name] = "❌ Crashed (View Logs)"
            
    except Exception as e:
        deployment_status[folder_name] = f"❌ Error: {str(e)}"

# --- লাইভ ইনস্টলেশন লগ সহ আপডেট করা ফাংশন ---
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
        
        log_file_path = os.path.join(repo_path, "bot_logs.txt")
        
        # pip install এর আউটপুট সরাসরি লগে পাঠানো হচ্ছে
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write("\n[System] Repository cloned successfully. Preparing installation...\n")
            
            req_file = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(req_file):
                deployment_status[folder_name] = "📦 Installing Requirements..."
                log_file.write("[System] Installing from requirements.txt...\n")
                subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, stdout=log_file, stderr=log_file)
            else:
                deployment_status[folder_name] = "🔍 Smart Scanning..."
                detected_imports = get_imports_from_folder(repo_path)
                packages_to_install = []
                for lib in detected_imports:
                    if lib not in STANDARD_LIBS and not lib.startswith("_"):
                        packages_to_install.append(PIP_MAPPING.get(lib, lib))
                
                if packages_to_install:
                    deployment_status[folder_name] = f"📦 Auto-Installing Libs..."
                    log_file.write(f"[System] Auto-installing detected packages: {', '.join(packages_to_install)}\n")
                    subprocess.run(["pip", "install"] + packages_to_install, cwd=repo_path, stdout=log_file, stderr=log_file)
            
            log_file.write("\n[System] Package installation complete! Starting bot process...\n\n")

        run_path = os.path.join(repo_path, start_file)
        if not os.path.exists(run_path):
            possible_files = ["app.py", "main.py", "bot.py", "start.py", "run.py"]
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
        # এরর হলে সেটাও লগে সেভ হবে
        if os.path.exists(repo_path):
            with open(os.path.join(repo_path, "bot_logs.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n[System Error] Deployment Failed: {e}\n")

def restore_sessions():
    time.sleep(2)
    print("🔄 Restoring previous sessions...")
    load_data()
    for folder_name in bot_configs:
        path = os.path.join(CLONE_DIR, folder_name)
        if os.path.exists(path):
            threading.Thread(target=run_bot_process, args=(folder_name,)).start()

# --- ROUTES ---

@app.route('/')
@auth.login_required
def home():
    return render_template('index.html')

@app.route('/system_stats')
@auth.login_required
def system_stats():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    return jsonify({"cpu": cpu, "ram": ram})

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
        if resp.status_code in [301, 302, 303, 307, 308]:
            location = resp.headers.get('Location')
            if location:
                if base_url in location: location = location.replace(base_url, "")
                new_loc = f"/view/{folder_name}{location}" if location.startswith("/") else f"/view/{folder_name}/{location}"
                return redirect(new_loc, code=resp.status_code)

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'location']
        headers = [(name, value) for (name, value) in resp.headers.items() if name.lower() not in excluded_headers]

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
@auth.login_required
def status_api():
    bots_data = []
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
@auth.login_required
def get_config(folder_name):
    config = bot_configs.get(folder_name, {})
    env_vars = config.get("env", {})
    env_text = "\n".join([f"{k}={v}" for k, v in env_vars.items()])
    return jsonify({"env": env_text})

@app.route('/logs/<folder_name>')
@auth.login_required
def get_logs(folder_name):
    repo_path = os.path.join(CLONE_DIR, folder_name)
    log_file_path = os.path.join(repo_path, "bot_logs.txt")
    
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:] # শেষ ২০০ লাইন দেখাবে
                return "".join(lines)
        except Exception as e:
            return f"Error reading logs: {e}"
    return "No logs found yet. Please wait..."

@app.route('/update_config/<folder_name>', methods=['POST'])
@auth.login_required
def update_config(folder_name):
    if folder_name in bot_configs:
        env_text = request.form.get("env_vars", "")
        bot_configs[folder_name]["env"] = parse_env_text(env_text)
        save_data()
        return "Updated", 200
    return "Not Found", 404

@app.route('/deploy', methods=['POST'])
@auth.login_required
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
@auth.login_required
def start_bot(folder_name):
    if folder_name not in running_processes or running_processes[folder_name].poll() is not None:
        deployment_status[folder_name] = "⏳ Starting..."
        thread = threading.Thread(target=run_bot_process, args=(folder_name,))
        thread.start()
    return redirect(url_for('home'))

@app.route('/stop/<folder_name>')
@auth.login_required
def stop_bot(folder_name):
    if folder_name in running_processes:
        proc = running_processes[folder_name]
        try:
            if os.name == 'posix':
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
        except:
            proc.kill()
            
        del running_processes[folder_name]
    deployment_status[folder_name] = "Stopped 🔴"
    return redirect(url_for('home'))

@app.route('/delete/<folder_name>')
@auth.login_required
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
