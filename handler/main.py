import os
import sys
import runpod

# Обеспечиваем доступность пакета `handler` при запуске как скрипта
# (когда выполняется /handler/main.py и родительская директория не в sys.path)
try:
    from handler.job_handler import handle  # попытка абсолютного импорта
except ModuleNotFoundError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from handler.job_handler import handle


def handler(job):
    return handle(job)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

