#!/bin/bash

# Lab Control App 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# 가상환경 활성화
source venv/bin/activate

# 앱 실행
cd lab_control_app
python main.py

