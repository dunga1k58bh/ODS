"""Exercise the same text=True decoding used by the host agent's curl calls."""

import subprocess
import sys


expected = "m\u00f4-h\u00ecnh.gguf"
if not sys.flags.utf8_mode or sys.argv[-1] != expected:
    sys.exit(1)
result = subprocess.run(
    [sys.executable, "-c", "import os; os.write(1, 'm\\u00f4-h\\u00ecnh.gguf'.encode('utf-8'))"],
    capture_output=True, text=True, check=True,
)
sys.exit(0 if result.stdout == expected else 1)
