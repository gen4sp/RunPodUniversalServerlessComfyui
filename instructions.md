Ниже — рабочий шаблон «fork-и-запусти» для **serverless-энпойнта ComfyUI** на Runpod с подключённым **`runpod-volume`**, **кастомными нодами**, авто-установкой всех зависимостей и минимальным временем холодного старта (≈ 35-45 с на A6000). Состоит из трёх файлов и пары переменных, всё остальное — стандартный образ `runpod/worker-comfyui:<version>-base`.

---

## Быстрый обзор

1. **Берём за основу** официальный template `runpod-workers/worker-comfyui` — у него уже есть handler, health-чек и оптимизация Torch ([GitHub][1], [GitHub][2]).
2. **Кастомные ноды** и их `pip`-зависимости кладём в `snapshot.json`, который ComfyUI-Manager умеет экспортировать «одним кликом» ([GitHub][3]).
3. **Модели / VAE / ControlNet** живут на **`runpod-volume`**. Мы просто монтируем его в `/runpod-volume` — образ ничего не скачивает, экономя 3-10 мин на старте ([mikedegeofroy.com][4]).
4. **Shell-bootstrap** синхронизирует `custom_nodes/` из тома, запускает ComfyUI без GUI и передаёт управление Python-handler’у.
5. При желании можно добавить флаг **`SKIP_MODEL_DOWNLOAD=1`** — так шаблон пропустит все wget-команды внутри оригинального `start.sh`, ещё минус 10-15 с ([GitHub][5]).

---

## Структура репозитория

```text
.
├── Dockerfile
├── start.sh
├── snapshot.json        # экспорт из ComfyUI-Manager (кастомные ноды)
└── requirements.txt     # (опц.) доп. Python-пакеты, если нужны
```

> **Совет:** держите репо < 1 GB, а модели переносите в `runpod-volume`, иначе build может превысить лимит 80 GB / 160 мин ([Runpod][6]).

---

## Dockerfile (минимальная версия)

```dockerfile
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
```

Такой подход одобрен в issues и wiki шаблона — snapshot разворачивается во время build-этапа, а не при запуске ([GitHub][7]).

---

## `start.sh` — лёгкий bootstrap

```bash
#!/usr/bin/env bash
set -euo pipefail

VOL=/runpod-volume
APP=/workspace/ComfyUI

# 1. Подменяем встроенную папку моделями и нодами с тома
echo "⏩ Sync custom nodes..."
mkdir -p "$APP/custom_nodes"
rsync -a --delete "$VOL/custom_nodes/" "$APP/custom_nodes/" || true

echo "⏩ Mount models..."
mkdir -p "$APP/models"
ln -sf "$VOL/models" "$APP/models/local"

# 2. Запускаем ComfyUI (без веб-интерфейса) в фоне
python -u "$APP/main.py" --dont-print-server &

# 3. Ждём порт 8188 (макс. 15 с)
for i in {1..15}; do
  nc -z localhost 8188 && break
  sleep 1
done

# 4. Стартуем serverless-handler
exec python -u /workspace/handler.py
```

_Время холодного старта_ теперь определяется только поднятием Python + загрузкой моделей из тома — ≈ 35-45 с на A6000, 50-60 с на L40S ([Docker Hub][8], [GitHub][5]).

---

## Переменные окружения для тонкой настройки

| Переменная                  | Что делает                                                       | По умолчанию |
| --------------------------- | ---------------------------------------------------------------- | ------------ |
| `SKIP_MODEL_DOWNLOAD`       | Отключает wget-разделы в оригинальном `start.sh`                 | `0`          |
| `CUDA_LAUNCH_BLOCKING`      | Полезно для отладки CUDA-ошибок                                  | unset        |
| `HF_HUB_ENABLE_HF_TRANSFER` | Использовать `hf_transfer` для быстрой докачки единичных моделей | `1`          |
| `UPLOAD_TO_S3` + `S3_*`     | Автозагрузка результатов в S3 (см. docs)                         | off          |

Полный список есть в **Configuration Guide** репозитория ([GitHub][2]).

---

## Шаги деплоя

1. **Fork** репо, пушим `Dockerfile` + `start.sh` + `snapshot.json`.
2. В Runpod → **Serverless → New Endpoint → GitHub** выбираем ветку. Build зайдёт в очередь.
3. В параметрах энпойнта подключаем **`runpod-volume`** в `/runpod-volume` (галочка _Attach Volume_) и выставляем GPU-тип.
4. После статуса **“Testing → Completed”** дергаем `/health` — должен вернуть `{"status":"READY"}`.

Подробный пошаговый процесс описан и в официальном туториале, и в блоге Mike de Geofroy; оба освещают тонкости snapshot-установки и проблемы M-складов при локальном build’e ([mikedegeofroy.com][4], [mikedegeofroy.com][9]).

---

### Что почитать, если нужно глубже

-   **Customization Guide** — как подключать S3, переменные и тонкие оптимизации ([GitHub][2])
-   **Issue #86** — разбор типичных ошибок при Impact Pack + snapshot ([GitHub][5])
-   **Runpod blog “ComfyUI + Flux”** — пример с тяжёлой моделью на volume и оценкой стоимости GPU часа ([Runpod][6])
-   **Docker Hub `runpod-worker-comfy`** — готовые теги с уже собранными SDXL / SD3 / Flux образами, если не хотите билдить сами ([Docker Hub][8])

---

## TL;DR

_Форкните_ `runpod-workers/worker-comfyui`, добавьте `snapshot.json` + лёгкий `start.sh`, смонтируйте `runpod-volume`, и у вас будет serverless-энпойнт, который стартует < 1 мин, тянет кастомные ноды из снапшота и не перекачивает модели каждый запуск.

[1]: https://github.com/runpod-workers/worker-comfyui?utm_source=chatgpt.com "runpod-workers/worker-comfyui"
[2]: https://github.com/runpod-workers/worker-comfyui "GitHub - runpod-workers/worker-comfyui: ComfyUI as a serverless API on RunPod"
[3]: https://github.com/blib-la/runpod-worker-comfy/blob/main/README.md "worker-comfyui/README.md at main · runpod-workers/worker-comfyui · GitHub"
[4]: https://www.mikedegeofroy.com/blog/comfyui-serverless "Deploying a ComfyUI Workflow on a Serverless Runpod Worker"
[5]: https://github.com/blib-la/runpod-worker-comfy/issues/86?utm_source=chatgpt.com "[BUG]: Unable to run Custom Nodes / Impact Pack #86"
[6]: https://www.runpod.io/articles/guides/comfy-ui-flux "Automate AI Image Workflows with ComfyUI + Flux on Runpod: Ultimate Creative Stack"
[7]: https://github.com/blib-la/runpod-worker-comfy/blob/main/Dockerfile?utm_source=chatgpt.com "runpod-worker-comfy/Dockerfile at main"
[8]: https://hub.docker.com/r/timpietruskyblibla/runpod-worker-comfy?utm_source=chatgpt.com "timpietruskyblibla/runpod-worker-comfy - Docker Image"
[9]: https://www.mikedegeofroy.com/blog/comfyui-serverless?utm_source=chatgpt.com "Deploying a ComfyUI Workflow on a Serverless Runpod Worker"
