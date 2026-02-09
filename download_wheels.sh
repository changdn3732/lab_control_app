#!/bin/bash

# 오프라인 설치를 위한 wheel 파일 다운로드 스크립트
# 인터넷이 연결된 Linux 환경에서 실행하세요

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📦 Linux용 패키지 wheel 파일을 다운로드합니다..."

# wheels 폴더 생성
mkdir -p wheels

# wheel 파일 다운로드
pip download -r lab_control_app/requirements.txt -d wheels --python-version 3.10 --only-binary=:all:

echo "✅ 다운로드 완료!"
echo "📁 wheels 폴더에 저장되었습니다."
echo ""
echo "이제 git에 커밋하세요:"
echo "  git add wheels/"
echo "  git commit -m 'Add offline wheels'"
echo "  git push"

