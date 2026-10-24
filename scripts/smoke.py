"""Start the real server without hotkeys, verify HTTP session, then stop it."""
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    env = dict(os.environ, SCROLLANSWER_DATA_DIR=folder, OPENAI_API_KEY='')
    command = ([sys.argv[1]] if len(sys.argv) > 1 else [sys.executable, str(root / 'backend.py')])
    process = subprocess.Popen([*command, '--no-hotkey'],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready = json.loads(process.stdout.readline())
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with opener.open(ready['url'], timeout=5) as response:
            assert response.status == 200
            assert b'NetWatch' in response.read()
        base = ready['url'].split('/bootstrap')[0]
        with opener.open(base + '/api/state', timeout=5) as response:
            state = json.load(response)
            assert state['answers'] == []
            assert not state['status']['hotkey_ready']
            assert not state['status']['email_configured']
        with opener.open(base + '/api/network', timeout=5) as response:
            network = json.load(response)
            assert 'endpoints' in network['observed']
            assert 'capture_error' in network['observed']
        print('PASS: real Waitress server, bootstrap, cookie session and state endpoint')
    finally:
        process.terminate()
        process.wait(timeout=5)
