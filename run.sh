#!/bin/bash

# Lab Control App 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# 패키지 설치 여부 확인 (flet이 설치되어 있는지 체크)
if ! python3 -c "import flet" 2>/dev/null; then
    echo "📦 패키지를 설치합니다... (sudo 권한 필요)"
    
    # wheels 폴더가 있으면 오프라인 설치, 없으면 온라인 설치
    if [ -d "wheels" ] && [ "$(ls -A wheels 2>/dev/null)" ]; then
        echo "   (오프라인 모드)"
        sudo pip3 install --no-index --find-links=wheels -r lab_control_app/requirements.txt
    else
        echo "   (온라인 모드)"
        sudo pip3 install -r lab_control_app/requirements.txt
    fi
    
    if [ $? -eq 0 ]; then
        echo "✅ 설치 완료!"
    else
        echo "❌ 설치 실패! 오류를 확인하세요."
        exit 1
    fi
fi

# 앱 실행
cd lab_control_app
python3 main.py
