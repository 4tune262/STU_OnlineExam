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