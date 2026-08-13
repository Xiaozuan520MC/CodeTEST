# -*- coding: utf-8 -*-
"""本地代码执行器：在临时目录中编译并运行用户提交的代码。"""
import os
import shutil
import subprocess
import tempfile
import threading

_LOCK = threading.Lock()
_HOME = os.path.expanduser("~")


def _rustc():
    p = shutil.which("rustc")
    if p:
        return p
    cand = os.path.join(_HOME, ".cargo", "bin", "rustc")
    return cand if os.path.exists(cand) else "rustc"


def _env():
    env = dict(os.environ)
    cargo = os.path.join(_HOME, ".cargo", "bin")
    env["PATH"] = cargo + os.pathsep + env.get("PATH", "")
    return env


def run_code(lang, code, stdin="", timeout_compile=20, timeout_run=10):
    """在临时目录编译运行代码，返回结果字典。"""
    with _LOCK:
        workdir = tempfile.mkdtemp(prefix="judge_")
        try:
            if lang == "python":
                files = [("main.py", code)]
                compile_cmd = None
                run_cmd = ["python3", "main.py"]
            elif lang == "c":
                files = [("main.c", code)]
                compile_cmd = ["gcc", "-O2", "-std=c11", "main.c", "-o", "main"]
                run_cmd = ["./main"]
            elif lang == "cpp":
                files = [("main.cpp", code)]
                compile_cmd = ["g++", "-O2", "-std=c++17", "main.cpp", "-o", "main"]
                run_cmd = ["./main"]
            elif lang == "java":
                files = [("Main.java", code)]
                compile_cmd = ["javac", "--release", "17", "Main.java"]
                run_cmd = ["java", "-Xmx256m", "Main"]
            elif lang == "rust":
                files = [("main.rs", code)]
                compile_cmd = [_rustc(), "-O", "main.rs", "-o", "main"]
                run_cmd = ["./main"]
            else:
                return {"ok": False, "error": f"不支持的语言: {lang}"}

            for name, content in files:
                with open(os.path.join(workdir, name), "w", encoding="utf-8") as f:
                    f.write(content)

            compile_error = ""
            if compile_cmd:
                try:
                    p = subprocess.run(
                        compile_cmd, cwd=workdir, capture_output=True, text=True,
                        timeout=timeout_compile, env=_env(),
                    )
                except subprocess.TimeoutExpired:
                    return {"ok": False, "error": "编译超时"}
                if p.returncode != 0:
                    return {"ok": False, "error": "编译错误:\n" + p.stderr.strip()[:3000]}

            try:
                p = subprocess.run(
                    run_cmd, cwd=workdir, input=stdin, capture_output=True, text=True,
                    timeout=timeout_run, env=_env(),
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "运行超时（可能存在死循环）"}
            if p.returncode != 0:
                return {"ok": False, "error": "运行错误 (退出码 %d):\n%s" % (p.returncode, p.stderr.strip()[:3000])}
            return {"ok": True, "output": p.stdout}
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
