#!/bin/bash

# Lab Control App 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# 가상환경이 없으면 생성 및 패키지 설치
if [ ! -d "venv" ]; then
    echo "🔧 가상환경을 생성합니다..."
    python3 -m venv venv
    source venv/bin/activate
    
    echo "📦 패키지를 설치합니다..."
    
    # wheels 폴더가 있으면 오프라인 설치, 없으면 온라인 설치
    if [ -d "wheels" ] && [ "$(ls -A wheels 2>/dev/null)" ]; then
        echo "   (오프라인 모드)"
        pip install --no-index --find-links=wheels -r lab_control_app/requirements.txt
    else
        echo "   (온라인 모드)"
        pip install -r lab_control_app/requirements.txt
    fi
    
    echo "✅ 설치 완료!"
else
    source venv/bin/activate
fi

# 앱 실행
cd lab_control_app
python main.py
