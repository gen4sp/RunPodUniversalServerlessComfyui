import runpod
from handler.job_handler import handle


def handler(job):
    return handle(job)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

