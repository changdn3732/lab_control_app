# Lab Control App

실험실 모터 및 가스 제어를 위한 GUI 애플리케이션입니다.

## 주요 기능

- 🔧 **모터 제어**: Modbus RTU 통신을 통한 스테핑 모터 제어
- 💨 **가스 제어**: 시리얼 통신을 통한 MFC(Mass Flow Controller) 제어
- 📅 **스케줄러**: 시간 기반 자동화 스케줄 설정
- 📊 **실시간 모니터링**: 장치 상태 실시간 확인

## 기술 스택

- **GUI Framework**: [Flet](https://flet.dev/) (Flutter 기반 Python GUI)
- **차트**: Plotly, Flet Charts
- **통신**: PyModbus, PySerial

---

## Ubuntu 22.04 LTS 설치 가이드

### 1. 시스템 패키지 업데이트
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Python 및 pip 설치
```bash
sudo apt install -y python3 python3-pip python3-venv
```

### 3. Flet 필수 시스템 의존성 설치
Flet은 Flutter 기반이라 GTK, GStreamer 등이 필요합니다:
```bash
sudo apt install -y \
    libgtk-3-0 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    gstreamer1.0-plugins-good \
    libmpv1 \
    libglib2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0
```

### 4. 시리얼 포트 권한 설정 (모터/가스 제어용)
```bash
sudo usermod -a -G dialout $USER
```
⚠️ **이후 로그아웃 후 다시 로그인 필요!**

### 5. 프로젝트 클론 및 실행
```bash
# 저장소 클론
git clone https://github.com/changdn3732/lab_control_app.git
cd lab_control_app

# 실행 권한 부여 (최초 1회)
chmod +x run.sh

# 앱 실행 (가상환경 자동 생성 및 패키지 설치)
./run.sh
```

> ℹ️ `run.sh`가 자동으로 가상환경을 생성하고 필요한 패키지를 설치합니다.  
> 재부팅 후에도 `./run.sh`만 실행하면 됩니다.

---

### 📋 빠른 설치 (한 번에 복사용)
```bash
# 시스템 패키지
sudo apt update && sudo apt install -y python3 python3-pip python3-venv \
    libgtk-3-0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
    gstreamer1.0-plugins-good libmpv1 libglib2.0-0 libcairo2 \
    libpango-1.0-0 libpangocairo-1.0-0 git

# 시리얼 포트 권한
sudo usermod -a -G dialout $USER

# 프로젝트 클론 및 실행
git clone https://github.com/changdn3732/lab_control_app.git
cd lab_control_app
chmod +x run.sh
./run.sh
```

> ⚠️ 시리얼 포트 권한 적용을 위해 최초 설치 후 **로그아웃/로그인** 필요

---

## 🔌 오프라인 설치 (인터넷 없는 환경)

인터넷이 연결되지 않은 환경에서 사용하려면 미리 패키지를 다운로드해야 합니다.

### 준비 단계 (인터넷 연결된 Linux에서)
```bash
# 저장소 클론
git clone https://github.com/changdn3732/lab_control_app.git
cd lab_control_app

# wheel 다운로드 스크립트 실행
chmod +x download_wheels.sh
./download_wheels.sh

# USB에 복사하거나, git에 포함
git add wheels/
git commit -m "Add offline wheels"
git push   # (선택) 개인 저장소에 올리기
```

### 오프라인 환경에서 실행
```bash
# USB에서 복사하거나 git clone
cd lab_control_app
chmod +x run.sh
./run.sh
```

> ℹ️ `run.sh`가 `wheels/` 폴더를 감지하면 자동으로 오프라인 설치를 진행합니다.

---

## Windows 설치 가이드

### 1. Python 설치
[Python 공식 사이트](https://www.python.org/downloads/)에서 Python 3.10 이상 설치

### 2. 프로젝트 설정
```powershell
# 저장소 클론
git clone https://github.com/changdn3732/lab_control_app.git
cd lab_control_app

# 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\Activate

# 패키지 설치
pip install -r lab_control_app\requirements.txt
```

### 3. 앱 실행
```powershell
cd lab_control_app
python main.py
```

---

## 프로젝트 구조

```
lab_control_app/
├── main.py                 # 메인 애플리케이션
├── motor_driver.py         # 모터 드라이버 (Modbus RTU)
├── gas_controller.py       # 가스 컨트롤러 (Serial)
├── requirements.txt        # Python 의존성
├── views/
│   ├── home_view.py        # 홈 화면
│   ├── scheduler_view.py   # 스케줄러 화면
│   └── device_settings_view.py  # 장치 설정 화면
└── schedules/              # 저장된 스케줄 파일
```

---

## 라이선스

MIT License

