import platform
import subprocess
import os

def get_os_info():
    """Mendeteksi OS untuk menyesuaikan perintah terminal."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine()
    }

def run_shell_command_realtime(command: str):
    """Menjalankan perintah terminal dan menghasilkan (yield) output secara real-time."""
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Membaca output baris per baris secara real-time
        for line in process.stdout:
            yield line
            
        process.wait()
        if process.returncode != 0:
            yield f"\n[Exit Code: {process.returncode}]"
            
    except Exception as e:
        yield f"\nError executing command: {str(e)}"

def read_local_file(file_path: str) -> str:
    """Membaca file lokal."""
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return f"Error: File '{file_path}' not found."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_local_file(file_path: str, content: str) -> str:
    """Menulis atau menimpa file lokal."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{file_path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"