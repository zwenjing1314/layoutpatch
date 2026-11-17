"""External process watchdog. No torch/model imports in the supervisor."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

LIMITS = {'preflight': 300, 'load': 600, 'page': 300, 'overlay': 60, 'review': 900}


def atomic_json(path, obj):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)


def kill_group(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def supervise(command, root, limits=None, sample_gpu=True):
    root = Path(root)
    limits = LIMITS if limits is None else limits
    started = time.monotonic()
    seen = None; stage_started = started; stage = {'phase':'preflight'}
    timed_out = None; rss_peak = 0; gpu_peak = None
    with (root/'stdout.log').open('x') as stdout, (root/'stderr.log').open('x') as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while child.poll() is None:
                state_file = root/'state.json'
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    if state['sequence'] != seen:
                        seen = state['sequence']; stage_started = time.monotonic(); stage = state
                        print(json.dumps(dict(event='stage', **state)), flush=True)
                elapsed = time.monotonic()-stage_started
                if elapsed > limits.get(stage['phase'], 180) or time.monotonic()-started > 13200:
                    timed_out = dict(phase=stage['phase'],page_id=stage.get('page_id'),elapsed_seconds=elapsed)
                    kill_group(child)
                    break
                record = dict(time=time.time(),phase=stage['phase'],page_id=stage.get('page_id'))
                try:
                    values = Path(f'/proc/{child.pid}/status').read_text().splitlines()
                    for line in values:
                        if line.startswith('VmRSS:'):
                            record['worker_rss_bytes'] = int(line.split()[1])*1024
                            rss_peak = max(rss_peak, record['worker_rss_bytes'])
                except (FileNotFoundError, ProcessLookupError):
                    pass
                if sample_gpu:
                    try:
                        result = subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total',
                            '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
                        if result.returncode == 0:
                            used,total = [int(v.strip()) for v in result.stdout.splitlines()[0].split(',')]
                            record.update(gpu_total_used_MiB=used,gpu_capacity_MiB=total)
                            gpu_peak = max(gpu_peak or 0, used)
                        else:
                            record['gpu_sample_error'] = 'nvidia-smi failed'
                    except (subprocess.TimeoutExpired, OSError, ValueError):
                        record['gpu_sample_error'] = 'nvidia-smi unavailable'
                with (root/'resources.jsonl').open('a') as stream:
                    stream.write(json.dumps(record)+'\n')
                time.sleep(0.2 if not sample_gpu else 1)
        finally:
            if child.poll() is None:
                kill_group(child)
    status = 'timeout' if timed_out else ('completed' if child.returncode == 0 else 'failed')
    # On crash/timeout preserve the full planned denominator and classify active page.
    pages_file = root/'page_status.json'
    if pages_file.exists():
        pages = json.loads(pages_file.read_text())
        for page in pages:
            if page['status'] in ('running','awaiting_review'):
                page.update(status='timeout' if timed_out else 'invalid',phase=stage['phase'])
        atomic_json(pages_file,pages)
    outcome = dict(status=status,worker_exit_code=child.returncode,timeout=timed_out,
                   elapsed_seconds=time.monotonic()-started,worker_peak_sampled_rss_bytes=rss_peak,
                   gpu_peak_sampled_total_used_MiB=gpu_peak,
                   gpu_metric_includes_other_processes=True,limits_seconds=limits)
    atomic_json(root/'supervisor.json',outcome)
    return outcome


if __name__ == '__main__':
    outcome=supervise([sys.executable,'-B','-u','/trial/worker.py'],Path('/run'))
    sys.exit(0 if outcome['status']=='completed' else 2)
