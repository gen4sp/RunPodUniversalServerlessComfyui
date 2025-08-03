FROM runpod/worker-comfyui:5.3.0-base

# 1) Копируем snapshot и скрипт
COPY snapshot.json /snapshot.json
COPY start.sh /start.sh
RUN chmod +x /start.sh

# 2) (опц.) ставим extra-deps
COPY requirements.txt /tmp/req.txt
RUN if [ -s /tmp/req.txt ]; then pip install -r /tmp/req.txt; fi

# 3) Включаем быстрый старт
ENV SKIP_MODEL_DOWNLOAD=1 \
    PYTHONUNBUFFERED=1

CMD ["/start.sh"]