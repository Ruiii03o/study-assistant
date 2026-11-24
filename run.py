"""Run this file in PyCharm using the project's virtual environment."""
import os
from pathlib import Path
import uvicorn

if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)
    print('过了么：http://127.0.0.1:8000（停止请按 Ctrl+C）')
    uvicorn.run('backend.app:app', host='127.0.0.1', port=8000)
