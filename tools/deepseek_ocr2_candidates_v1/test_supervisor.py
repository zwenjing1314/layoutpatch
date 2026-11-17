import json
from pathlib import Path
import sys
import tempfile
import unittest
from supervisor import supervise


class WatchdogTests(unittest.TestCase):
    def test_kills_hung_worker_and_retains_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'page_status.json').write_text(json.dumps([{'page_id':'a','status':'running'},
                {'page_id':'b','status':'not_attempted'}]))
            result=supervise([sys.executable,'-c','import time; time.sleep(30)'],root,
                             limits={'preflight':0.3},sample_gpu=False)
            self.assertEqual(result['status'],'timeout')
            self.assertEqual(result['worker_exit_code'],-9)
            self.assertEqual([p['status'] for p in json.loads((root/'page_status.json').read_text())],['timeout','not_attempted'])
    def test_nonzero_exit_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=supervise([sys.executable,'-c','raise SystemExit(2)'],Path(tmp),sample_gpu=False)
            self.assertEqual(result['status'],'failed')
    def test_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=supervise([sys.executable,'-c','print("ok")'],Path(tmp),sample_gpu=False)
            self.assertEqual(result['status'],'completed')


if __name__=='__main__':
    unittest.main(verbosity=2)
