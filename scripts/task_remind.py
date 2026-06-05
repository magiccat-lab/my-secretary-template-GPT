#!/usr/bin/env python3
"""先輩待ちタスクリマインダー - 未完了タスクがあれば通知"""
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

TASKS_FILE = os.path.expanduser('~/secretary/data/pending_tasks.json')
WEBHOOK = 'http://localhost:8781/remind'
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_RANDOM', '')

def main():
    if not os.path.exists(TASKS_FILE):
        return

    with open(TASKS_FILE) as f:
        data = json.load(f)

    # primary/secondaryセクション両方から集める（旧形式tasksも互換）
    all_tasks = []
    if 'tasks' in data:
        all_tasks = [t for t in data['tasks'] if not t.get('done')]
    else:
        primary_tasks = [t for t in data.get('primary', []) if not t.get('done')]
        secondary_tasks = [t for t in data.get('secondary', []) if not t.get('done')]
        if primary_tasks:
            all_tasks += [{'title': f'[Primary] {t["title"]}', **t} for t in primary_tasks]
        if secondary_tasks:
            all_tasks += [{'title': f'[Secondary] {t["title"]}', **t} for t in secondary_tasks]

    if not all_tasks:
        return

    lines = ['**未完了タスク**']
    for t in all_tasks:
        lines.append(f'・{t["title"]}')

    message = '\n'.join(lines)
    requests.post(WEBHOOK, json={
        'channel_id': CHANNEL_ID,
        'message': message
    }, timeout=10)

if __name__ == '__main__':
    main()
