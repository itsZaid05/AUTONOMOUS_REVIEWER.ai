"""Start only missing local processes; logs/PIDs are retained outside the checkout."""
import os,subprocess,socket,sys
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
env=dict(os.environ);env.update({k:v for k,v in dotenv_values(root/'.env').items() if v is not None});env['PYTHONPATH']=str(root)
logs=Path('/workspace/paperflow-environment/logs');logs.mkdir(parents=True,exist_ok=True)
python=sys.executable
commands={'api':[python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],'worker':[python,'-m','celery','-A','app.jobs.queue','worker','--concurrency=2','--loglevel=INFO'],'dashboard':[python,'-m','streamlit','run','app/dashboard.py','--server.address=127.0.0.1','--server.port=8501','--browser.gatherUsageStats=false']}
for name,cmd in commands.items():
    pidfile=logs/(name+'.pid')
    try:
        pid=int(pidfile.read_text());os.kill(pid,0)
        actual=Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace')
        expected={'api':'uvicorn','worker':'celery','dashboard':'streamlit'}[name]
        if expected not in actual:raise RuntimeError(f'{name} PID belongs to another process; inspect and remove stale PID file')
        print(name,'already running');continue
    except (OSError,ValueError):pass
    with (logs/(name+'.log')).open('ab') as log:
        p=subprocess.Popen(cmd,cwd=root,env=env,stdout=log,stderr=log,start_new_session=True)
    pidfile.write_text(str(p.pid));print(name,'started')
