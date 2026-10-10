from codegates import scan
from codegates.__main__ import main


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return p


def test_silent_except_detecta_e_aceita_log_ou_raise(tmp_path):
    _write(tmp_path, "a.py", '''
import logging
log = logging.getLogger(__name__)

def ruim():
    try:
        1 / 0
    except Exception:
        pass

def bare():
    try:
        1 / 0
    except:
        return None

def ok_log():
    try:
        1 / 0
    except Exception as e:
        log.warning("x %s", e)

def ok_raise():
    try:
        1 / 0
    except Exception:
        raise

def ok_especifico():
    try:
        1 / 0
    except ZeroDivisionError:
        pass
''')
    f = scan(tmp_path, ["silent-except"])
    assert [x.line for x in f] == [8, 14]


def test_cancelamento_engolido(tmp_path):
    _write(tmp_path, "b.py", '''
import asyncio

async def ruim():
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        return

async def ok():
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
''')
    f = scan(tmp_path, ["swallowed-cancellation"])
    assert len(f) == 1 and f[0].line == 7


def test_bloqueio_dentro_de_async(tmp_path):
    _write(tmp_path, "c.py", '''
import time, subprocess, asyncio
from pathlib import Path

async def ruim():
    time.sleep(1)
    subprocess.run(["ls"])
    open("x").read()
    Path("y").read_text()

async def ok():
    def sync_part():
        time.sleep(1)
        return open("x").read()
    await asyncio.to_thread(sync_part)
    await asyncio.sleep(1)

def sync_fn():
    time.sleep(1)
''')
    f = scan(tmp_path, ["blocking-in-async"])
    assert [x.line for x in f] == [6, 7, 8, 9]


def test_pastas_ignoradas_e_check_desconhecido(tmp_path):
    (tmp_path / ".venv").mkdir()
    _write(tmp_path / ".venv", "x.py", "try:\n    pass\nexcept Exception:\n    pass\n")
    assert scan(tmp_path) == []
    try:
        scan(tmp_path, ["nao-existe"])
    except ValueError as e:
        assert "unknown checks" in str(e)
    else:
        raise AssertionError("deveria falhar")


def test_cli_codigo_de_saida(tmp_path, capsys):
    _write(tmp_path, "d.py", "try:\n    pass\nexcept Exception:\n    pass\n")
    assert main([str(tmp_path)]) == 1
    assert "silent-except" in capsys.readouterr().out
    clean = tmp_path / "limpo"
    clean.mkdir()
    _write(clean, "e.py", "x = 1\n")
    assert main([str(clean)]) == 0
