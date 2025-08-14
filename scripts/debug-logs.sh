#!/bin/bash

# Скрипт для диагностики и мониторинга ошибок ComfyUI
# Использование: ./scripts/debug-logs.sh [опции]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# Функция для показа помощи
show_help() {
    echo "Скрипт диагностики логов ComfyUI"
    echo ""
    echo "Использование: $0 [опции]"
    echo ""
    echo "Опции:"
    echo "  -h, --help          Показать эту справку"
    echo "  -f, --follow        Следить за логами в реальном времени"
    echo "  -e, --errors        Показать только ошибки"
    echo "  -l, --last N        Показать последние N строк (по умолчанию 50)"
    echo "  -s, --status        Проверить статус ComfyUI"
    echo "  -c, --clear         Очистить логи"
    echo "  --all-logs          Показать все доступные логи"
    echo ""
    echo "Примеры:"
    echo "  $0 -f               # Следить за логами"
    echo "  $0 -e -l 100        # Последние 100 строк с ошибками"
    echo "  $0 -s               # Проверить статус"
}

# Функция для проверки статуса ComfyUI
check_status() {
    log_info "Проверка статуса ComfyUI..."
    
    # Проверяем процесс
    if pgrep -f "main.py" > /dev/null; then
        log_success "ComfyUI процесс запущен"
        echo "PID: $(pgrep -f 'main.py')"
    else
        log_error "ComfyUI процесс не найден"
    fi
    
    # Проверяем порт
    if nc -z localhost 8188 2>/dev/null; then
        log_success "ComfyUI API доступен на порту 8188"
    else
        log_error "ComfyUI API недоступен на порту 8188"
    fi
    
    # Проверяем HTTP статус
    if curl -s http://localhost:8188/ > /dev/null 2>&1; then
        log_success "ComfyUI HTTP сервер отвечает"
    else
        log_error "ComfyUI HTTP сервер не отвечает"
    fi
    
    echo ""
}

# Функция для показа доступных логов
show_all_logs() {
    log_info "Доступные файлы логов:"
    
    for log_path in "/tmp/comfyui.log" "/workspace/ComfyUI/user/comfyui.log" "/var/log/runpod.log"; do
        if [ -f "$log_path" ]; then
            size=$(du -h "$log_path" | cut -f1)
            lines=$(wc -l < "$log_path" 2>/dev/null || echo "0")
            log_success "✓ $log_path (размер: $size, строк: $lines)"
        else
            log_warn "✗ $log_path (не найден)"
        fi
    done
    echo ""
}

# Функция для очистки логов
clear_logs() {
    log_info "Очистка логов..."
    
    for log_path in "/tmp/comfyui.log" "/workspace/ComfyUI/user/comfyui.log"; do
        if [ -f "$log_path" ]; then
            > "$log_path"
            log_success "Очищен: $log_path"
        fi
    done
}

# Функция для фильтрации ошибок
filter_errors() {
    grep -i -E "(error|exception|failed|traceback|critical)" "$1" | tail -n "$2"
}

# Функция для мониторинга логов
monitor_logs() {
    local log_file="$1"
    local errors_only="$2"
    
    if [ ! -f "$log_file" ]; then
        log_error "Файл лога не найден: $log_file"
        return 1
    fi
    
    log_info "Мониторинг логов: $log_file"
    log_info "Нажмите Ctrl+C для выхода"
    echo ""
    
    if [ "$errors_only" = "true" ]; then
        tail -f "$log_file" | grep -i -E "(error|exception|failed|traceback|critical)" --line-buffered
    else
        tail -f "$log_file"
    fi
}

# Основная логика
FOLLOW=false
ERRORS_ONLY=false
LAST_LINES=50
CHECK_STATUS=false
CLEAR_LOGS=false
SHOW_ALL=false

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -e|--errors)
            ERRORS_ONLY=true
            shift
            ;;
        -l|--last)
            LAST_LINES="$2"
            shift 2
            ;;
        -s|--status)
            CHECK_STATUS=true
            shift
            ;;
        -c|--clear)
            CLEAR_LOGS=true
            shift
            ;;
        --all-logs)
            SHOW_ALL=true
            shift
            ;;
        *)
            log_error "Неизвестная опция: $1"
            show_help
            exit 1
            ;;
    esac
done

# Выполнение команд
if [ "$SHOW_ALL" = "true" ]; then
    show_all_logs
fi

if [ "$CHECK_STATUS" = "true" ]; then
    check_status
fi

if [ "$CLEAR_LOGS" = "true" ]; then
    clear_logs
    exit 0
fi

# Определяем основной файл лога
MAIN_LOG="/workspace/ComfyUI/user/comfyui.log"
if [ ! -f "$MAIN_LOG" ]; then
    MAIN_LOG="/tmp/comfyui.log"
fi

if [ ! -f "$MAIN_LOG" ]; then
    log_error "Файлы логов не найдены!"
    log_info "Попробуйте сначала запустить ComfyUI"
    exit 1
fi

if [ "$FOLLOW" = "true" ]; then
    monitor_logs "$MAIN_LOG" "$ERRORS_ONLY"
else
    log_info "Показываем последние $LAST_LINES строк из: $MAIN_LOG"
    echo ""
    
    if [ "$ERRORS_ONLY" = "true" ]; then
        filter_errors "$MAIN_LOG" "$LAST_LINES"
    else
        tail -n "$LAST_LINES" "$MAIN_LOG"
    fi
fi
