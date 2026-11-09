"""Submit source bytes to an isolated compiler. Never contacts a Docker daemon."""
import hashlib,json,shutil,time,uuid
from pathlib import Path
from .settings import settings

def compile_source(source):
    source=Path(source);content=source.read_bytes();digest=hashlib.sha256(content).hexdigest()
    queue=settings.compile_queue;queue.mkdir(parents=True,exist_ok=True)
    job=queue/uuid.uuid4().hex;job.mkdir(mode=0o700)
    try:
        (job/'source').write_bytes(content)
        ready=job/'request.tmp';ready.write_text(json.dumps({'suffix':source.suffix,'sha256':digest}));ready.replace(job/'request.json')
        deadline=time.monotonic()+settings.compile_timeout_seconds
        while time.monotonic()<deadline:
            if (job/'result.json').exists():
                result=json.loads((job/'result.json').read_text())
                if not result.get('ok'):raise ValueError('Isolated compilation failed: '+result.get('diagnostic',result.get('error_type','Unknown error')))
                if result['source_sha256']!=digest:raise ValueError('Compiler source checksum mismatch')
                pdf=(job/'result.pdf').read_bytes()
                if hashlib.sha256(pdf).hexdigest()!=result['pdf_sha256'] or not pdf.startswith(b'%PDF'):raise ValueError('Compiler output integrity failure')
                target=source.with_suffix('.rendered.pdf');target.write_bytes(pdf)
                return target,result
            time.sleep(.2)
        raise TimeoutError('Isolated compiler did not respond; verify the compiler service')
    finally:
        # The controller never runs as the worker identity; only its generated output is shared.
        if (job/'result.json').exists():shutil.rmtree(job,ignore_errors=True)
        elif job.exists():(job/'cancel').touch()
