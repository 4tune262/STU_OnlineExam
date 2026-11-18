import subprocess
import tempfile
import shutil
import os


class CPPCompiler:

    def __init__(self):
        pass

    def compile(self, workdir):

        compile_cmd = [

            "docker",

            "run",

            "--rm",

            "-v",

            f"{workdir}:/code",

            "gcc",

            "g++",

            "/code/main.cpp",

            "-o",

            "/code/main"

        ]

        result = subprocess.run(

            compile_cmd,

            capture_output=True,

            text=True,

            timeout=30

        )

        return result

    def execute(self, workdir, input_data=""):

        run_cmd = [

            "docker",

            "run",

            "--rm",

            "-i",

            "-v",

            f"{workdir}:/code",

            "gcc",

            "/code/main"

        ]

        result = subprocess.run(

            run_cmd,

            input=input_data,

            capture_output=True,

            text=True,

            timeout=30

        )

        return result


compiler = CPPCompiler()


def run_cpp(code, input_data=""):

    workdir = tempfile.mkdtemp()

    cpp_file = os.path.join(workdir, "main.cpp")

    with open(cpp_file, "w", encoding="utf8") as f:
        f.write(code)

    compile_result = compiler.compile(workdir)

    if compile_result.returncode != 0:

        shutil.rmtree(workdir)

        return {

            "status": "Compile Error",

            "success": False,

            "compile_error": compile_result.stderr

        }

    try:

        run_result = compiler.execute(
            workdir,
            input_data
        )

        shutil.rmtree(workdir)

        return {

            "status": "Success",

            "success": True,

            "stdout": run_result.stdout,

            "stderr": run_result.stderr,

            "returncode": run_result.returncode

        }

    except subprocess.TimeoutExpired:

        shutil.rmtree(workdir)

        return {

            "status": "Time Limit Exceeded",

            "success": False,

            "stdout": "",

            "stderr": "Program timeout"

        }

    except Exception as e:

        shutil.rmtree(workdir)

        return {

            "status": "Runtime Error",

            "success": False,

            "stdout": "",

            "stderr": str(e)

        }

class PHPCompiler:
    """Run untrusted PHP CLI code in an isolated Docker container."""
    IMAGE = "php:8.4-cli"

    def execute(self, code, input_data=""):
        workdir = tempfile.mkdtemp(prefix="stu_php_")
        try:
            php_file = os.path.join(workdir, "main.php")
            with open(php_file, "w", encoding="utf-8") as f:
                f.write(code)
            command = [
                "docker", "run", "--rm", "-i",
                "--network", "none", "--memory", "128m",
                "--memory-swap", "128m", "--cpus", "0.5",
                "--pids-limit", "64", "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--user", "1000:1000",
                "--mount", f"type=bind,source={workdir},target=/code,readonly",
                "--workdir", "/code", self.IMAGE,
                "php", "-d", "display_errors=stderr",
                "-d", "log_errors=0", "-d", "memory_limit=64M",
                "-d", "max_execution_time=3", "/code/main.php",
            ]
            result = subprocess.run(command, input=input_data, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                status = "Compile Error" if "Parse error" in result.stderr or "syntax error" in result.stderr.lower() else "Runtime Error"
                return {"status": status, "success": False, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
            return {"status": "Success", "success": True, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"status": "Time Limit Exceeded", "success": False, "stdout": "", "stderr": "Program timeout (5 seconds)"}
        except Exception as exc:
            return {"status": "Runtime Error", "success": False, "stdout": "", "stderr": str(exc)}
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def run_php(code, input_data=""):
    return PHPCompiler().execute(code, input_data)


def run_code_by_language(language, code, input_data=""):
    """Dispatch by the language stored in the immutable exam snapshot."""
    normalized = str(language or "cpp").strip().lower()
    if normalized in ("cpp", "c++"):
        return run_cpp(code, input_data)
    if normalized == "php":
        return run_php(code, input_data)
    return {"status": "Runtime Error", "success": False, "stdout": "", "stderr": f"Ngôn ngữ chưa được hỗ trợ: {normalized}"}
