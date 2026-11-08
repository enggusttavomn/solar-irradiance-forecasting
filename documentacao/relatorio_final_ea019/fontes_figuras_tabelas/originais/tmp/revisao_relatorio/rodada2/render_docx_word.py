"""Use Word COM for conversion and the unmodified packaged renderer for PNG QA."""
from pathlib import Path
import importlib.util
import json
import os
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
RUNTIME = Path('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies')
SKILL = Path('C:/Users/gusta/.codex/plugins/cache/openai-primary-runtime/documents/26.1026.10807/skills/documents')
POWERSHELL = RUNTIME / 'native/powershell/pwsh.exe'
POPPLER_BIN = RUNTIME / 'native/poppler/Library/bin'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PATH'] = os.pathsep.join([str(POPPLER_BIN), str(RUNTIME / 'python'), os.environ.get('PATH', '')])
spec = importlib.util.spec_from_file_location('canonical_render_docx', SKILL / 'render_docx.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def convert_with_word(doc_path, user_profile, convert_tmp_dir, stem, verbose):
    pdf_path = Path(convert_tmp_dir) / (stem + '.pdf')
    pid_path = Path(convert_tmp_dir) / 'word-process.json'
    command = [str(POWERSHELL), '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
               str(Path(__file__).with_name('word_export_readonly.ps1')),
               '-InputDocx', str(Path(doc_path).resolve()), '-OutputPdf', str(pdf_path),
               '-PidFile', str(pid_path)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        if pid_path.is_file():
            owned = json.loads(pid_path.read_text(encoding='utf-8-sig'))
            if owned.get('newlyCreated') and owned.get('pid'):
                try:
                    os.kill(int(owned['pid']), signal.SIGTERM)
                except OSError:
                    pass
        return '', 'Microsoft Word read-only conversion exceeded the 30-second timeout.'
    log = 'BACKEND: Microsoft Word COM, hidden, read-only, no source save\n' + proc.stdout + proc.stderr
    if verbose:
        print(log)
    if proc.returncode == 0 and pdf_path.is_file() and pdf_path.stat().st_size:
        return str(pdf_path), log
    return '', log


renderer.convert_to_pdf = convert_with_word
if __name__ == '__main__':
    renderer.main()
