#!/usr/bin/env python3
"""
Анализатор ошибок ComfyUI - помогает диагностировать проблемы по логам
"""

import re
import sys
import json
from datetime import datetime
from collections import defaultdict, Counter
import argparse

def parse_timestamp(line):
    """Извлекает timestamp из строки лога"""
    # Ищем паттерн [YYYY-MM-DD HH:MM:SS.mmm]
    match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]', line)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            pass
    return None

def analyze_log_file(log_path, show_details=False):
    """Анализирует файл лога и выводит статистику ошибок"""
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ Файл лога не найден: {log_path}")
        return
    except Exception as e:
        print(f"❌ Ошибка чтения файла {log_path}: {e}")
        return
    
    print(f"\n📊 Анализ лога: {log_path}")
    print(f"📝 Всего строк: {len(lines)}")
    
    if not lines:
        print("📋 Файл лога пустой")
        return
    
    # Статистика ошибок
    error_patterns = {
        'got_prompt': r'got prompt',
        'error_handling': r'Error handling request',
        'websocket_error': r'websocket.*error|WebSocket.*Error',
        'http_error': r'HTTP.*[Ee]rror|requests.*[Ee]rror',
        'traceback': r'Traceback|Exception:',
        'comfyui_error': r'ComfyUI.*[Ee]rror',
        'validation_error': r'validation.*failed|Workflow validation',
        'timeout': r'timeout|Timeout',
        'connection_error': r'connection.*error|Connection.*Error',
        'model_error': r'model.*not.*found|checkpoint.*error'
    }
    
    error_counts = Counter()
    error_details = defaultdict(list)
    timestamps = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Извлекаем timestamp
        ts = parse_timestamp(line)
        if ts:
            timestamps.append(ts)
        
        # Ищем ошибки по паттернам
        for error_type, pattern in error_patterns.items():
            if re.search(pattern, line, re.IGNORECASE):
                error_counts[error_type] += 1
                if show_details:
                    error_details[error_type].append({
                        'line_num': i + 1,
                        'timestamp': ts.isoformat() if ts else 'unknown',
                        'content': line[:200] + '...' if len(line) > 200 else line
                    })
    
    # Выводим статистику
    print(f"\n🔍 Статистика ошибок:")
    if error_counts:
        for error_type, count in error_counts.most_common():
            print(f"  • {error_type}: {count}")
    else:
        print("  ✅ Ошибки не найдены")
    
    # Анализ временных интервалов
    if timestamps:
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        duration = last_ts - first_ts
        print(f"\n⏰ Временной интервал:")
        print(f"  • Первая запись: {first_ts.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  • Последняя запись: {last_ts.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  • Продолжительность: {duration}")
    
    # Детальная информация об ошибках
    if show_details and error_details:
        print(f"\n📋 Детали ошибок:")
        for error_type, details in error_details.items():
            print(f"\n🔸 {error_type} ({len(details)} раз):")
            for detail in details[-3:]:  # Показываем последние 3 для каждого типа
                print(f"  Строка {detail['line_num']} [{detail['timestamp']}]: {detail['content']}")
    
    # Ищем последние ошибки "Error handling request"
    recent_errors = []
    for i, line in enumerate(lines):
        if 'Error handling request' in line:
            # Собираем контекст вокруг ошибки
            start_idx = max(0, i - 5)
            end_idx = min(len(lines), i + 10)
            context = ''.join(lines[start_idx:end_idx])
            recent_errors.append({
                'line_num': i + 1,
                'context': context
            })
    
    if recent_errors:
        print(f"\n🚨 Последние ошибки 'Error handling request' ({len(recent_errors)}):")
        for error in recent_errors[-2:]:  # Показываем последние 2
            print(f"\n📍 Строка {error['line_num']}:")
            print("=" * 50)
            print(error['context'])
            print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description='Анализатор ошибок ComfyUI')
    parser.add_argument('-f', '--follow', action='store_true', help='Следить за логами в реальном времени')
    parser.add_argument('-e', '--errors', action='store_true', help='Показать только ошибки')
    parser.add_argument('-l', '--last', type=int, default=50, help='Количество последних строк')
    parser.add_argument('-s', '--status', action='store_true', help='Проверить статус ComfyUI')
    parser.add_argument('-d', '--details', action='store_true', help='Показать детали ошибок')
    parser.add_argument('--log-path', default='/workspace/ComfyUI/user/comfyui.log', help='Путь к файлу лога')
    
    args = parser.parse_args()
    
    # Проверяем статус если запрошено
    if args.status:
        import subprocess
        import socket
        
        print("🔍 Проверка статуса ComfyUI...")
        
        # Проверяем процесс
        try:
            result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ ComfyUI процесс запущен (PID: {result.stdout.strip()})")
            else:
                print("❌ ComfyUI процесс не найден")
        except Exception as e:
            print(f"❌ Ошибка проверки процесса: {e}")
        
        # Проверяем порт
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 8188))
            sock.close()
            if result == 0:
                print("✅ Порт 8188 доступен")
            else:
                print("❌ Порт 8188 недоступен")
        except Exception as e:
            print(f"❌ Ошибка проверки порта: {e}")
    
    # Анализируем основной лог
    if not args.follow:
        analyze_log_file(args.log_path, args.details)
        
        # Также проверяем альтернативный лог
        alt_log = "/tmp/comfyui.log"
        if alt_log != args.log_path and open(alt_log, 'r').read().strip():
            analyze_log_file(alt_log, args.details)
    else:
        # Режим мониторинга
        import subprocess
        
        if not args.errors:
            subprocess.run(['tail', '-f', args.log_path])
        else:
            cmd = f"tail -f {args.log_path} | grep -i -E '(error|exception|failed|traceback|critical)'"
            subprocess.run(cmd, shell=True)

if __name__ == "__main__":
    main()
