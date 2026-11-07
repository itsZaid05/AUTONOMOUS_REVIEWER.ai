"""Compatibility entry point: generate the five current autonomous conference workflows."""
import runpy
from pathlib import Path
if __name__=='__main__':
    runpy.run_path(str(Path(__file__).with_name('generate_agent_workflows.py')),run_name='__main__')
