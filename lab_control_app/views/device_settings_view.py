"""
가스 설정 화면 - MFC / BPR / BASIS 가스 제어기 설정
Slave ID 5, 6 할당
"""
import flet as ft
from typing import Callable, Dict, List, Optional

# 모터 드라이버 모듈 import
try:
    from motor_driver import MotorController
    MOTOR_DRIVER_AVAILABLE = True
except ImportError:
    MOTOR_DRIVER_AVAILABLE = False
    print("⚠️ motor_driver 모듈을 찾을 수 없습니다.")

# 가스 제어기 모듈 import
try:
    from gas_controller import GasController, ALICAT_GAS_LIST, GAS_TABLE, DeviceType
    GAS_CONTROLLER_AVAILABLE = True
except ImportError:
    GAS_CONTROLLER_AVAILABLE = False
    print("⚠️ gas_controller 모듈을 찾을 수 없습니다.")


class DeviceSettingsView:
    def __init__(self, page: ft.Page):
        self.page = page
        self.connected_devices: List[Dict] = []
        self.status_text = None
        
        # 모터 컨트롤러
        self.motor_controller: Optional['MotorController'] = None
        self.motor_connected = False
        
        # 가스 컨트롤러
        self.gas_controller: Optional['GasController'] = None
        self.gas_connected = False
        self.gas_port = "COM7"
        self.gas_baudrate = 19200
        
        # 가스 장치 UI 참조
        self.gas_setpoint_inputs = {}
        self.gas_status_texts = {}
        self.gas_dropdown = None
    
    def build(self, navigate_to: Callable):
        """장치 설정 화면 빌드"""
        
        # 상단 헤더
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        icon_color="#333333",
                        on_click=lambda _: navigate_to("home"),
                    ),
                    ft.Text("Gas Settings", size=24, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=20,
            bgcolor="#ffffff",
            border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
        )
        
        # 연결 설정 섹션
        connection_section = self._build_connection_section()
        
        # 연결된 장치 목록
        devices_section = self._build_devices_section()
        
        # 메인 컨텐츠
        main_content = ft.Container(
            content=ft.Row(
                [
                    # 왼쪽: 연결 설정
                    ft.Container(
                        content=connection_section,
                        width=350,
                        padding=20,
                    ),
                    # 오른쪽: 연결된 장치
                    ft.Container(
                        content=devices_section,
                        expand=True,
                        padding=20,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
            bgcolor="#f5f5f5",
        )
        
        return ft.Container(
            content=ft.Column(
                [header, main_content],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )
    
    def _build_connection_section(self):
        """연결 설정 섹션"""
        
        # COM 포트 입력
        port_input = ft.TextField(
            label="COM 포트",
            value="COM7",
            width=150,
        )
        
        # Baudrate 선택
        baudrate_select = ft.Dropdown(
            label="Baudrate",
            options=[
                ft.dropdown.Option("9600"),
                ft.dropdown.Option("19200"),
                ft.dropdown.Option("38400"),
                ft.dropdown.Option("57600"),
                ft.dropdown.Option("115200"),
            ],
            value="9600",
            width=150,
        )
        
        # 장치 타입 선택 (모터 4개: RS-485, Slave ID 1~4 고정)
        device_type_select = ft.Dropdown(
            label="장치 타입",
            options=[
                ft.dropdown.Option("upper_stage", "상부 스테이지 (ID:1)"),
                ft.dropdown.Option("lower_stage", "하부 스테이지 (ID:2)"),
                ft.dropdown.Option("upper_rotate", "상부 회전 (ID:3)"),
                ft.dropdown.Option("lower_rotate", "하부 회전 (ID:4)"),
                ft.dropdown.Option("mfc", "MFC"),
                ft.dropdown.Option("bpr", "BPR"),
                ft.dropdown.Option("pc", "PC"),
            ],
            value="upper_stage",
            width=220,
        )
        
        # 상태 표시
        self.status_text = ft.Text("", size=12, color="#666666")
        
        # 연결 버튼
        connect_btn = ft.ElevatedButton(
            "🔌 연결",
            bgcolor="#007bff",
            color="#ffffff",
            width=200,
            on_click=lambda _: self._connect_device(
                port_input.value,
                baudrate_select.value,
                device_type_select.value,
            ),
        )
        
        # 스캔 버튼
        scan_btn = ft.OutlinedButton(
            "🔍 자동 스캔",
            width=200,
            on_click=lambda _: self._scan_devices(),
        )
        
        # 가스 제어기 연결 상태 표시
        self.gas_connection_status = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LINK_OFF, size=14, color="#dc3545"),
                ft.Text("가스 제어기 연결 안됨", size=12, color="#dc3545"),
            ], spacing=5),
        )
        
        # 가스 제어기 연결 버튼
        gas_connect_btn = ft.ElevatedButton(
            "⛽ 가스 제어기 연결",
            bgcolor="#17a2b8",
            color="#ffffff",
            width=200,
            on_click=lambda _: self._connect_gas_device(port_input.value, baudrate_select.value),
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("연결 설정", size=18, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=20),
                    port_input,
                    baudrate_select,
                    device_type_select,
                    ft.Text("※ 모터 Slave ID: 1~4 / 가스 제어기 ID: 5~6", size=11, color="#666666"),
                    ft.Container(height=10),
                    connect_btn,
                    gas_connect_btn,
                    scan_btn,
                    ft.Container(height=10),
                    self.status_text,
                    self.gas_connection_status,
                ],
                spacing=15,
            ),
            bgcolor="#ffffff",
            padding=20,
            border_radius=10,
            border=ft.border.all(1, "#e0e0e0"),
        )
    
    def _build_devices_section(self):
        """연결된 장치 목록 섹션"""
        
        # 장치 카드들
        device_cards = []
        
        if not self.connected_devices:
            device_cards.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.DEVICE_UNKNOWN, size=48, color="#cccccc"),
                            ft.Text("연결된 장치가 없습니다", color="#999999"),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    alignment=ft.Alignment(0, 0),  # center
                    expand=True,
                )
            )
        else:
            for device in self.connected_devices:
                card = self._create_device_card(device)
                device_cards.append(card)
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("연결된 장치", size=18, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=20),
                    ft.Container(
                        content=ft.Row(
                            device_cards,
                            wrap=True,
                            spacing=15,
                            run_spacing=15,
                        ),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            bgcolor="#ffffff",
            padding=20,
            border_radius=10,
            border=ft.border.all(1, "#e0e0e0"),
            expand=True,
        )
    
    def _create_device_card(self, device: Dict):
        """장치 카드 생성"""
        
        # 장치 타입별 아이콘/색상 (모터: RS-485, Slave ID 1~4)
        type_config = {
            "upper_stage": {"icon": ft.Icons.ARROW_UPWARD, "color": "#2a9d8f", "name": "상부 스테이지", "slave_id": 1},
            "lower_stage": {"icon": ft.Icons.ARROW_DOWNWARD, "color": "#9b5de5", "name": "하부 스테이지", "slave_id": 2},
            "upper_rotate": {"icon": ft.Icons.ROTATE_RIGHT, "color": "#e76f51", "name": "상부 회전", "slave_id": 3},
            "lower_rotate": {"icon": ft.Icons.ROTATE_LEFT, "color": "#f4a261", "name": "하부 회전", "slave_id": 4},
            "mfc": {"icon": ft.Icons.AIR, "color": "#007bff", "name": "MFC", "slave_id": None},
            "bpr": {"icon": ft.Icons.COMPRESS, "color": "#ffc107", "name": "BPR", "slave_id": None},
            "pc": {"icon": ft.Icons.SPEED, "color": "#28a745", "name": "PC", "slave_id": None},
        }
        
        config = type_config.get(device.get("type", ""), 
                                 {"icon": ft.Icons.DEVICE_UNKNOWN, "color": "#666666", "name": "Unknown"})
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(config["icon"], color=config["color"], size=24),
                            ft.Text(device.get("port", ""), weight=ft.FontWeight.BOLD),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=16,
                                icon_color="#dc3545",
                                on_click=lambda _, d=device: self._disconnect_device(d),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(config["name"], size=14, color="#666666"),
                    ft.Text(f"Baud: {device.get('baudrate', '')} | ID: {device.get('slave_id', '')}", 
                           size=12, color="#999999"),
                    ft.Container(height=5),
                    ft.Row(
                        [
                            ft.TextButton("설정", on_click=lambda _, d=device: self._open_device_settings(d)),
                            ft.TextButton("테스트", on_click=lambda _, d=device: self._test_device(d)),
                        ],
                        spacing=5,
                    ),
                ],
                spacing=5,
            ),
            width=200,
            padding=15,
            bgcolor="#f8f9fa",
            border_radius=10,
            border=ft.border.all(1, config["color"]),
        )
    
    def _connect_device(self, port: str, baudrate: str, device_type: str):
        """장치 연결"""
        # 모터 Slave ID 매핑 (RS-485)
        # 드라이버 1: upper_stage(X축, ID=1), upper_rotate(Y축, ID=1)
        # 드라이버 2: lower_stage(X축, ID=2), lower_rotate(Y축, ID=2)
        motor_slave_ids = {
            "upper_stage": 1,
            "upper_rotate": 1,
            "lower_stage": 2,
            "lower_rotate": 2,
        }
        
        try:
            # 모터 장치인 경우 실제 Modbus 연결
            if device_type in motor_slave_ids:
                if MOTOR_DRIVER_AVAILABLE:
                    # 기존 연결 해제
                    if self.motor_controller and self.motor_connected:
                        self.motor_controller.disconnect()
                    
                    # 새 컨트롤러 생성 및 연결
                    self.motor_controller = MotorController(
                        port=port,
                        baudrate=int(baudrate)
                    )
                    
                    if self.motor_controller.connect():
                        self.motor_connected = True
                        
                        # 모든 모터 장치 추가 (하나의 컨트롤러로 4개 모터 제어)
                        for motor_type, slave_id in motor_slave_ids.items():
                            # 중복 체크
                            existing = [d for d in self.connected_devices if d["type"] == motor_type]
                            if not existing:
                                self.connected_devices.append({
                                    "port": port,
                                    "baudrate": int(baudrate),
                                    "slave_id": slave_id,
                                    "type": motor_type,
                                    "connected": True,
                                })
                        
                        if self.status_text:
                            self.status_text.value = f"✅ {port} 연결 성공 (모터 4개)"
                            self.status_text.color = "#28a745"
                    else:
                        if self.status_text:
                            self.status_text.value = f"❌ {port} 연결 실패"
                            self.status_text.color = "#dc3545"
                else:
                    # 시뮬레이션 모드
                    slave_id = motor_slave_ids.get(device_type, 1)
                    new_device = {
                        "port": port,
                        "baudrate": int(baudrate),
                        "slave_id": slave_id,
                        "type": device_type,
                        "connected": True,
                    }
                    self.connected_devices.append(new_device)
                    
                    if self.status_text:
                        self.status_text.value = f"✅ {port} 연결 (시뮬레이션)"
                        self.status_text.color = "#ffc107"
            else:
                # 다른 장치 (MFC, BPR, PC)
                new_device = {
                    "port": port,
                    "baudrate": int(baudrate),
                    "slave_id": 1,
                    "type": device_type,
                    "connected": True,
                }
                self.connected_devices.append(new_device)
                
                if self.status_text:
                    self.status_text.value = f"✅ {port} 연결 성공"
                    self.status_text.color = "#28a745"
            
            self.page.update()
            print(f"✅ 연결됨: {port}")
            
        except Exception as e:
            if self.status_text:
                self.status_text.value = f"❌ 연결 실패: {e}"
                self.status_text.color = "#dc3545"
            self.page.update()
            print(f"❌ 연결 실패: {e}")
    
    def _disconnect_device(self, device: Dict):
        """장치 연결 해제"""
        try:
            device_type = device.get("type", "")
            
            # 모터 장치인 경우
            motor_types = ["upper_stage", "upper_rotate", "lower_stage", "lower_rotate"]
            if device_type in motor_types:
                # 모터 컨트롤러 연결 해제
                if self.motor_controller and self.motor_connected:
                    self.motor_controller.disconnect()
                    self.motor_connected = False
                
                # 모든 모터 장치 제거
                self.connected_devices = [d for d in self.connected_devices if d.get("type") not in motor_types]
            else:
                # 개별 장치만 제거
                self.connected_devices.remove(device)
            
            if self.status_text:
                self.status_text.value = f"🔌 {device['port']} 연결 해제"
                self.status_text.color = "#666666"
            self.page.update()
            print(f"🔌 연결 해제: {device['port']}")
        except Exception as e:
            print(f"연결 해제 오류: {e}")
    
    def _scan_devices(self):
        """장치 자동 스캔"""
        if self.status_text:
            self.status_text.value = "🔍 스캔 중..."
            self.status_text.color = "#007bff"
        self.page.update()
        
        # TODO: 실제 COM 포트 스캔
        print("🔍 장치 스캔 시작...")
    
    def _open_device_settings(self, device: Dict):
        """장치 설정 다이얼로그"""
        print(f"⚙️ 설정 열기: {device['port']}")
        
        # 가스 장치인 경우 가스 설정 다이얼로그 열기
        if device.get("gas_device_id"):
            self._open_gas_settings_dialog(device)
            return
        
        # 모터 장치 설정 다이얼로그 (TODO)
    
    def _test_device(self, device: Dict):
        """장치 테스트"""
        device_type = device.get("type", "")
        motor_types = ["upper_stage", "upper_rotate", "lower_stage", "lower_rotate"]
        
        if device_type in motor_types and self.motor_controller and self.motor_connected:
            try:
                # 짧은 테스트 동작 (100ms 정도 움직인 후 정지)
                import time
                
                # 저속으로 시작
                self.motor_controller.start_motor(device_type, "plus", 500)
                time.sleep(0.1)
                self.motor_controller.stop_motor(device_type)
                
                if self.status_text:
                    self.status_text.value = f"✅ {device_type} 테스트 완료"
                    self.status_text.color = "#28a745"
                self.page.update()
                print(f"🧪 테스트 완료: {device_type}")
                
            except Exception as e:
                if self.status_text:
                    self.status_text.value = f"❌ 테스트 실패: {e}"
                    self.status_text.color = "#dc3545"
                self.page.update()
                print(f"🧪 테스트 실패: {e}")
        else:
            print(f"🧪 테스트 (시뮬레이션): {device['port']}")
    
    # ==================== 가스 제어기 메서드 ====================
    
    def _connect_gas_device(self, port: str, baudrate: str):
        """가스 제어기 연결"""
        if not GAS_CONTROLLER_AVAILABLE:
            if self.status_text:
                self.status_text.value = "❌ gas_controller 모듈이 없습니다"
                self.status_text.color = "#dc3545"
            self.page.update()
            return
        
        if self.status_text:
            self.status_text.value = "⛽ 가스 제어기 연결 중..."
            self.status_text.color = "#007bff"
        self.page.update()
        
        try:
            self.gas_controller = GasController(
                port=port,
                baudrate=int(baudrate)
            )
            self.gas_controller.on_log = self._on_gas_log
            
            if self.gas_controller.connect():
                self.gas_connected = True
                self.gas_port = port
                self.gas_baudrate = int(baudrate)
                
                if self.status_text:
                    self.status_text.value = f"✅ 가스 제어기 연결 성공: {port}"
                    self.status_text.color = "#28a745"
                
                # 연결 상태 업데이트
                if hasattr(self, 'gas_connection_status'):
                    self.gas_connection_status.content = ft.Row([
                        ft.Icon(ft.Icons.LINK, size=14, color="#28a745"),
                        ft.Text(f"가스 제어기 연결됨 ({port})", size=12, color="#28a745"),
                    ], spacing=5)
                
                # 가스 장치 카드 추가
                self._add_gas_device_cards()
                
            else:
                self.gas_connected = False
                if self.status_text:
                    self.status_text.value = "❌ 가스 제어기 연결 실패"
                    self.status_text.color = "#dc3545"
        except Exception as e:
            self.gas_connected = False
            if self.status_text:
                self.status_text.value = f"❌ 가스 제어기 오류: {str(e)}"
                self.status_text.color = "#dc3545"
        
        self.page.update()
    
    def _add_gas_device_cards(self):
        """가스 장치 카드 추가"""
        # MFC #1 (Slave ID 5)
        gas1_device = {
            "port": self.gas_port,
            "type": "mfc",
            "baudrate": self.gas_baudrate,
            "slave_id": 5,
            "gas_device_id": "gas1",
        }
        # 중복 체크
        existing = [d for d in self.connected_devices if d.get("gas_device_id") == "gas1"]
        if not existing:
            self.connected_devices.append(gas1_device)
        
        # MFC #2 (Slave ID 6)
        gas2_device = {
            "port": self.gas_port,
            "type": "mfc",
            "baudrate": self.gas_baudrate,
            "slave_id": 6,
            "gas_device_id": "gas2",
        }
        existing = [d for d in self.connected_devices if d.get("gas_device_id") == "gas2"]
        if not existing:
            self.connected_devices.append(gas2_device)
    
    def _on_gas_log(self, message: str):
        """가스 컨트롤러 로그 콜백"""
        print(f"[Gas Settings] {message}")
    
    def _open_gas_settings_dialog(self, device: Dict):
        """가스 장치 설정 다이얼로그 열기"""
        gas_device_id = device.get("gas_device_id", "")
        if not gas_device_id or not self.gas_controller or not self.gas_connected:
            return
        
        gas_device = self.gas_controller.get_device(gas_device_id)
        if not gas_device:
            return
        
        # 현재 데이터 읽기
        data = gas_device.read_all()
        
        # Setpoint 입력 필드
        setpoint_input = ft.TextField(
            label="Setpoint",
            value=f"{data.setpoint:.2f}",
            width=150,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        
        # Gas 선택 드롭다운
        gas_options = [
            ft.dropdown.Option(key=str(g[0]), text=f"{g[0]}: {g[1]}")
            for g in ALICAT_GAS_LIST
        ]
        gas_dropdown = ft.Dropdown(
            label="Gas 선택",
            options=gas_options,
            value=str(data.gas_index),
            width=200,
        )
        
        # 현재 상태 표시
        status_text = ft.Text(
            f"압력: {data.pressure:.2f} | 온도: {data.temperature:.1f}°C",
            size=12,
            color="#666666",
        )
        
        def apply_setpoint(e):
            try:
                value = float(setpoint_input.value)
                gas_device.write_setpoint(value)
                status_text.value = f"✅ Setpoint → {value}"
                status_text.color = "#28a745"
                self.page.update()
            except Exception as ex:
                status_text.value = f"❌ 오류: {ex}"
                status_text.color = "#dc3545"
                self.page.update()
        
        def apply_gas(e):
            try:
                gas_idx = int(gas_dropdown.value)
                gas_device.write_gas(gas_idx)
                status_text.value = f"✅ Gas → {GAS_TABLE.get(gas_idx, 'Unknown')}"
                status_text.color = "#28a745"
                self.page.update()
            except Exception as ex:
                status_text.value = f"❌ 오류: {ex}"
                status_text.color = "#dc3545"
                self.page.update()
        
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"⛽ 가스 설정 - {gas_device_id.upper()}"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"Slave ID: {device.get('slave_id', '')}", size=12, color="#888888"),
                    ft.Divider(height=10),
                    ft.Row([setpoint_input, ft.ElevatedButton("적용", on_click=apply_setpoint)]),
                    ft.Row([gas_dropdown, ft.ElevatedButton("변경", on_click=apply_gas)]),
                    ft.Container(height=10),
                    status_text,
                ], spacing=15),
                width=350,
                padding=10,
            ),
            actions=[ft.TextButton("닫기", on_click=close_dialog)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

