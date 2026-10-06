"""Запуск word_run.ps1 с планом: копирует скрипт в Temp Windows, ограничивает по времени, гасит только свой WINWORD."""
import json, subprocess, os, shutil, sys, time
WIN = '/mnt/c/Users/Budnik_AN/AppData/Local/Temp/canon_reeng'
WINP = 'C:\\Users\\Budnik_AN\\AppData\\Local\\Temp\\canon_reeng'
HERE = os.path.dirname(os.path.abspath(__file__))

def winpath(name): return WINP + '\\' + name.replace('/', '\\')
def wsl(name): return os.path.join(WIN, name)

def run(steps, tag, timeout=900):
    os.makedirs(WIN, exist_ok=True)
    shutil.copy(os.path.join(HERE, 'word_run.ps1'), wsl('word_run.ps1'))
    plan = {'steps': steps, 'log': winpath(tag + '.log'), 'pidfile': winpath(tag + '.pid')}
    with open(wsl(tag + '.plan.json'), 'w', encoding='utf-8-sig') as f: json.dump(plan, f)  # ASCII-escaped
    open(wsl(tag + '.log'), 'w').close()
    cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', winpath('word_run.ps1'), '-Plan', winpath(tag + '.plan.json')]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, timeout=timeout, capture_output=True)
        out = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired:
        out = 'TIMEOUT'
        try: pids = open(wsl(tag + '.pid')).read().strip().strip('\ufeff').split(',')
        except Exception: pids = []
        for pid in pids:
            if pid.strip().isdigit():
                subprocess.run(['powershell.exe', '-NoProfile', '-Command', f"Get-Process -Id {pid.strip()} -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -eq 'WINWORD' }} | Stop-Process -Force"])   # только WINWORD: номер процесса мог достаться другой программе (validator 06.10)
    log = open(wsl(tag + '.log'), encoding='utf-8-sig', errors='replace').read()
    return {'out': out, 'log': log, 'sec': round(time.time() - t0)}
