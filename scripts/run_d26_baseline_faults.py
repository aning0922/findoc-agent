"""Run unchanged recovery contracts against the exact unified baseline in a new archive."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

product = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix="findoc-d26-baseline-code-"))
archive = subprocess.check_output(
    ["git", "archive", "7b3f9ec26a2c82b0b90c76c8152236dc577585e0", "app", "tests"], cwd=product
)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(root, filter="data")
(root / "tests/test_d26_recovery.py").write_bytes(
    (product / "tests/test_d26_recovery.py").read_bytes()
)
out = Path(
    os.environ.get("D26_BASELINE_OUT", str(product / "product/d26/evidence/b-baseline-verified"))
)
out.mkdir()
env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
env.update(
    FINDOC_D26_EVIDENCE_DIR=str(out), FINDOC_E2E_DISABLE_ENV_FILES="1", PYTHONDONTWRITEBYTECODE="1"
)
runner = root / "run.py"
runner.write_text(
    """import sys,os,tempfile\nfrom pathlib import Path\nfrom urllib.parse import unquote,urlparse\nroot=Path(__file__).resolve().parent\ndata_root=Path(os.environ["D26_BASELINE_DATA"]).resolve()\ntempfile.tempdir=str(data_root)\ndef guard(event,args):\n if event=="socket.connect":raise RuntimeError("D26 baseline forbids service connection")\n if event=="sqlite3.connect" and args[0]!=":memory:":\n  value=args[0];p=Path(unquote(urlparse(value).path) if str(value).startswith("file:") else value).resolve()\n  if not p.is_relative_to(data_root):raise RuntimeError("D26 baseline rejects foreign SQLite")\nsys.addaudithook(guard)\nimport pytest\nsys.exit(pytest.main(["-q","-p","no:cacheprovider","--basetemp",str(data_root/"pytest"),"--junitxml",os.environ["D26_BASELINE_JUNIT"],"tests/test_d26_recovery.py","-k","not report and not readonly"]))\n"""
)
env["D26_BASELINE_DATA"] = tempfile.mkdtemp(prefix="findoc-d26-baseline-runtime-")
env["D26_BASELINE_JUNIT"] = str(out / "junit.xml")
with (out / "backend.log").open("w") as f:
    code = subprocess.run(
        [sys.executable, str(runner)], cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT
    ).returncode
(out / "record.json").write_text(
    json.dumps(
        dict(
            source_ref="7b3f9ec26a2c82b0b90c76c8152236dc577585e0",
            root=str(root),
            exit_code=code,
            service_connections_blocked=True,
            all_sqlite_in_fresh_root=True,
            human_acceptances=0,
            simulated_test=True,
        ),
        indent=2,
    )
    + "\n"
)
sys.exit(code)
