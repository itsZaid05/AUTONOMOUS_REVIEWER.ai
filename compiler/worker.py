"""Filesystem queue compiler. No socket, network, application credentials or host mount.
The controller can only chown/drop UID; every TeX process gets its own UID and private directory.
"""
import ctypes,hashlib,json,os,re,resource,shutil,signal,stat,subprocess,tempfile,time,zipfile,threading
from pathlib import Path
QUEUE=Path('/queue');QUEUE.mkdir(exist_ok=True)
MAX_SIZE=100*1024*1024

def unpack(source,target,suffix):
    if suffix=='.tex':shutil.copyfile(source,target/'main.tex');return
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>1000 or sum(i.file_size for i in entries)>MAX_SIZE:raise ValueError('Archive expansion limit')
        for entry in entries:
            name=Path(entry.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr>>16) or entry.flag_bits&1:raise ValueError('Unsafe archive member')
            path=target/name
            if entry.is_dir():path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as src,path.open('wb') as dst:shutil.copyfileobj(src,dst)

def lower_privileges(uid):
    os.setsid();os.setgroups([]);os.setgid(uid);os.setuid(uid)
    ctypes.CDLL(None).prctl(38,1,0,0,0) # PR_SET_NO_NEW_PRIVS
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_FSIZE,(50*1024*1024,50*1024*1024))
    resource.setrlimit(resource.RLIMIT_AS,(600*1024*1024,600*1024*1024));resource.setrlimit(resource.RLIMIT_NPROC,(32,32))

def execute(command,work,uid):
    env={'PATH':'/usr/bin:/bin','HOME':str(work),'TMPDIR':str(work),'openin_any':'p','openout_any':'p','TEXMFOUTPUT':str(work)}
    p=subprocess.Popen(command,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,preexec_fn=lambda:lower_privileges(uid))
    try:output=p.communicate(timeout=60)[0]
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.communicate();raise ValueError('Compilation time limit exceeded')
    return p.returncode,output.decode(errors='replace')

def compile_job(job):
    started=time.time();uid=10000+(int(job.name[:8],16)%50000)
    request=json.loads((job/'request.json').read_text());source=job/'source';digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=request['sha256']:raise ValueError('Source checksum mismatch')
    if request['suffix'] not in ['.tex','.zip'] or source.stat().st_size>30*1024*1024:raise ValueError('Invalid source')
    work=Path(tempfile.mkdtemp(prefix='tex-',dir='/tmp'));work.chmod(0o700)
    try:
        unpack(source,work,request['suffix'])
        mains=[p for p in work.rglob('*.tex') if '\\documentclass' in p.read_text(errors='replace')]
        if len(mains)!=1:raise ValueError('Exactly one documentclass entry point required')
        main=mains[0]
        for path in [work,*work.rglob('*')]:os.chown(path,uid,uid)
        probe=r'\AtBeginDocument{\typeout{PAPERFLOW-WIDTH=\the\textwidth}\typeout{PAPERFLOW-HEIGHT=\the\textheight}}\input{'+main.name+'}'
        command=['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-jobname='+main.stem,probe]
        code,output=execute(command,main.parent,uid)
        if code:
            line=re.search(r'(?m)^l\.(\d+)',output)
            diagnostic='\n'.join(l for l in output.splitlines() if l.startswith('!')) or 'LaTeX compilation failed'
            raise ValueError(diagnostic+(' (source line '+line[1]+')' if line else ''))
        aux=main.with_suffix('.aux')
        if aux.exists() and '\\bibdata' in aux.read_text(errors='replace'):
            code,biblog=execute(['bibtex',main.stem],main.parent,uid)
            output+=biblog
            if code:raise ValueError('Bibliography compilation failed; verify citation keys, .bib files and bibliography style')
        for _ in range(2):
            code,output=execute(command,main.parent,uid)
            if code:raise ValueError('LaTeX recompilation failed')
        pdf=main.with_suffix('.pdf')
        if not pdf.exists():raise ValueError('Compiler produced no PDF')
        shutil.copyfile(pdf,job/'result.pdf');(job/'result.pdf').chmod(0o644)
        result={'ok':True,'source_sha256':digest,'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'seconds':round(time.time()-started,3),'compiler':'TeX Live / LLNCS','isolation':{'network':'none','host_docker_socket':False,'per_job_uid':uid,'shell_escape':False},'warnings':[l for l in output.splitlines() if 'undefined' in l.lower() or 'multiply defined' in l.lower()]}
        for label,key in [('WIDTH','text_width_mm'),('HEIGHT','text_height_mm')]:
            match=re.search(r'PAPERFLOW-'+label+r'=([0-9.]+)pt',output)
            if match:result[key]=round(float(match.group(1))*25.4/72.27,2)
        return result
    finally:shutil.rmtree(work,ignore_errors=True)

def heartbeat():
    while True:
        (QUEUE/'service.tmp').write_text(json.dumps({'ready':True,'observed_at':time.time(),'network':'none','host_docker_socket':False}))
        (QUEUE/'service.tmp').replace(QUEUE/'service.json');time.sleep(1)

def run():
    threading.Thread(target=heartbeat,daemon=True).start()
    while True:
        for job in sorted(QUEUE.glob('*')):
            if not job.is_dir() or job.is_symlink() or not re.fullmatch('[0-9a-f]{32}',job.name) or not (job/'request.json').exists() or (job/'result.json').exists():continue
            try:result={'ok':False,'diagnostic':'Cancelled'} if (job/'cancel').exists() else compile_job(job)
            except Exception as exc:result={'ok':False,'error_type':type(exc).__name__,'diagnostic':str(exc)[:1500] if isinstance(exc,ValueError) else 'Internal compiler error'}
            if not job.exists():continue
            if (job/'cancel').exists():shutil.rmtree(job,ignore_errors=True);continue
            temporary=job/'result.tmp';temporary.write_text(json.dumps(result));temporary.chmod(0o644);temporary.replace(job/'result.json')
        time.sleep(.2)
if __name__=='__main__':run()
