"""
스케줄러 화면 - 상대 시간 기반 타임라인
PMC-2HSP 모터 드라이버 통합 제어
"""
import flet as ft
import flet_charts as fch
from datetime import datetime, timedelta
from typing import List, Dict, Callable, Optional
import threading
import time
import json
import os

# 모터 드라이버 모듈 import
try:
    from motor_driver import (
        MotorController, 
        mm_to_pulse, pulse_to_mm, 
        degree_to_pulse, pulse_to_degree,
        PULSE_PER_MM, PULSE_PER_REV, MM_PER_REV, STEP_ANGLE
    )
    MOTOR_DRIVER_AVAILABLE = True
except ImportError:
    MOTOR_DRIVER_AVAILABLE = False
    print("⚠️ motor_driver 모듈을 찾을 수 없습니다. 시뮬레이션 모드로 실행됩니다.")

# 가스 제어기 모듈 import
try:
    from gas_controller import GasController, GasDeviceData, ALICAT_GAS_LIST, GAS_TABLE
    GAS_CONTROLLER_AVAILABLE = True
except ImportError:
    GAS_CONTROLLER_AVAILABLE = False
    print("⚠️ gas_controller 모듈을 찾을 수 없습니다. 가스 제어 시뮬레이션 모드.")


class ScheduleBlock:
    """스케줄 블록 데이터 (상대 시간 기반)"""
    def __init__(self, device_id: str, start_seconds: int, duration_seconds: int, 
                 action_name: str, action_params: Dict = None):
        self.id = f"{device_id}_{start_seconds}"
        self.device_id = device_id
        self.start_seconds = start_seconds
        self.duration_seconds = duration_seconds
        self.action_name = action_name
        self.action_params = action_params or {}
        self.executed = False
    
    @property
    def end_seconds(self) -> int:
        return self.start_seconds + self.duration_seconds
    
    def format_time(self, seconds: int) -> str:
        """초를 MM:SS 형식으로 변환"""
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    
    def to_dict(self) -> Dict:
        """JSON 직렬화용"""
        return {
            "device_id": self.device_id,
            "start_seconds": self.start_seconds,
            "duration_seconds": self.duration_seconds,
            "action_name": self.action_name,
            "action_params": self.action_params,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ScheduleBlock":
        """JSON에서 복원"""
        return cls(
            device_id=data["device_id"],
            start_seconds=data["start_seconds"],
            duration_seconds=data["duration_seconds"],
            action_name=data["action_name"],
            action_params=data.get("action_params", {}),
        )


class SchedulerView:
    def __init__(self, page: ft.Page):
        self.page = page
        
        # 4개 모터 정의 (RS-485 통신)
        # 드라이버 1: upper_stage(X축), upper_rotate(Y축)
        # 드라이버 2: lower_stage(X축), lower_rotate(Y축)
        self.devices = [
            {"id": "upper_stage", "name": "상부 스테이지", "color": "#2a9d8f", "icon": ft.Icons.ARROW_UPWARD, "slave_id": 1, "type": "stage"},
            {"id": "lower_stage", "name": "하부 스테이지", "color": "#9b5de5", "icon": ft.Icons.ARROW_DOWNWARD, "slave_id": 2, "type": "stage"},
            {"id": "upper_rotate", "name": "상부 회전", "color": "#e76f51", "icon": ft.Icons.ROTATE_RIGHT, "slave_id": 1, "type": "rotate"},
            {"id": "lower_rotate", "name": "하부 회전", "color": "#f4a261", "icon": ft.Icons.ROTATE_LEFT, "slave_id": 2, "type": "rotate"},
        ]
        
        # 가스 장치 정의 (Slave ID 5: MFC, Slave ID 6: BPR)
        self.gas_devices = [
            {"id": "mfc", "name": "MFC", "color": "#007bff", "icon": ft.Icons.AIR, "slave_id": 5, "type": "gas"},
            {"id": "bpr", "name": "BPR", "color": "#17a2b8", "icon": ft.Icons.COMPRESS, "slave_id": 6, "type": "gas"},
        ]
        
        # 전체 장치 목록 (모터 + 가스)
        self.all_devices = self.devices + self.gas_devices
        self.schedule_blocks: List[ScheduleBlock] = []
        self.is_running = False
        self.scheduler_thread = None
        self.elapsed_seconds = 0
        
        # ==================== 모터 컨트롤러 ====================
        self.motor_controller: Optional['MotorController'] = None
        self.motor_connected = False
        self.com_port = "COM7"
        self.baudrate = 9600
        
        # 모터 사양 (0.72° 스텝각, 풀스텝, 1회전=5mm)
        self.PULSE_PER_MM = 100       # 1mm = 100펄스
        self.PULSE_PER_REV = 500      # 1회전 = 500펄스
        self.MM_PER_REV = 5           # 1회전 = 5mm
        self.STEP_ANGLE = 0.72        # 스텝각 (도)
        
        # 타임라인 설정
        self.timeline_max_seconds = 3600
        self.pixels_per_minute = 10
        self.row_height = 45
        
        # UI 참조
        self.timeline_container = None
        self.status_text = None
        self.elapsed_text = None
        self.connection_status = None
        
        # 왼쪽 패널 상태
        self.current_mode = "manual"  # manual, upper_stage, upper_rotate, lower_stage, lower_rotate
        self.left_panel_content = None
        self.mode_buttons_container = None  # 모드 버튼 영역
        self.speed_mode = "low"  # low, high (저속/고속)
        
        # 플로팅 모니터 패널
        self.floating_panel = None
        self.floating_visible = False
        self.floating_maximized = False  # 최대화 상태
        self.graph_data = {device["id"]: [] for device in self.devices}  # 그래프 데이터
        self.max_graph_points = 60  # 최근 60개 포인트 (2초 간격 = 2분)
        self.motor_speeds = {device["id"]: 0 for device in self.devices}  # 현재 속도
        self.progress_bars = {}  # 프로그레스 바 참조
        self.speed_labels = {}  # 속도 라벨 참조
        
        # ==================== 가스 제어기 ====================
        self.gas_controller: Optional['GasController'] = None
        self.gas_connected = False
        self.gas_port = "COM7"
        self.gas_baudrate = 19200
        
        # 가스 장치 데이터
        self.gas_data = {
            'mfc': {'pressure': 0.0, 'temperature': 0.0, 'setpoint': 0.0, 'valve_open': False},
            'bpr': {'pressure': 0.0, 'temperature': 0.0, 'setpoint': 0.0, 'valve_open': False},
        }
        
        # 가스 그래프 데이터
        self.gas_graph_data = {
            'mfc_pressure': [],
            'mfc_temperature': [],
            'mfc_setpoint': [],
            'bpr_pressure': [],
            'bpr_temperature': [],
            'bpr_setpoint': [],
        }
        
        # 모터 컨트롤러 초기화
        self._init_motor_controller()
        
        # 가스 컨트롤러 초기화
        self._init_gas_controller()
    
    # ==================== 모터 컨트롤러 관련 메서드 ====================
    
    def _init_motor_controller(self):
        """모터 컨트롤러 초기화"""
        if MOTOR_DRIVER_AVAILABLE:
            try:
                self.motor_controller = MotorController(
                    port=self.com_port,
                    baudrate=self.baudrate
                )
                self.motor_controller.on_log = self._on_motor_log
                print("✅ MotorController 초기화 완료")
            except Exception as e:
                print(f"⚠️ MotorController 초기화 실패: {e}")
                self.motor_controller = None
        else:
            print("⚠️ motor_driver 모듈 없음 - 시뮬레이션 모드")
    
    def _init_gas_controller(self):
        """가스 컨트롤러 초기화"""
        if GAS_CONTROLLER_AVAILABLE:
            try:
                self.gas_controller = GasController(
                    port=self.gas_port,
                    baudrate=self.gas_baudrate
                )
                self.gas_controller.on_log = self._on_gas_log
                print("✅ GasController 초기화 완료")
            except Exception as e:
                print(f"⚠️ GasController 초기화 실패: {e}")
                self.gas_controller = None
        else:
            print("⚠️ gas_controller 모듈 없음 - 시뮬레이션 모드")
    
    def _on_gas_log(self, message: str):
        """가스 컨트롤러 로그 콜백"""
        print(f"[Gas] {message}")
    
    def connect_gas(self) -> bool:
        """가스 제어기 연결"""
        if not self.gas_controller:
            return False
        
        try:
            if self.gas_controller.connect():
                self.gas_connected = True
                print("✅ 가스 제어기 연결 성공")
                return True
            else:
                self.gas_connected = False
                return False
        except Exception as e:
            self.gas_connected = False
            print(f"❌ 가스 제어기 연결 오류: {e}")
            return False
    
    def disconnect_gas(self):
        """가스 제어기 연결 해제"""
        if self.gas_controller:
            self.gas_controller.disconnect()
        self.gas_connected = False
    
    def toggle_gas_valve(self, device_id: str, is_open: bool) -> bool:
        """가스 밸브 열기/닫기"""
        if not self.gas_connected or not self.gas_controller:
            # 시뮬레이션 모드
            self.gas_data[device_id]['valve_open'] = is_open
            print(f"[시뮬레이션] {device_id} 밸브 {'열림' if is_open else '닫힘'}")
            return True
        
        success = self.gas_controller.set_valve(device_id, is_open)
        if success:
            self.gas_data[device_id]['valve_open'] = is_open
        return success
    
    def read_gas_data(self):
        """가스 장치 데이터 읽기"""
        if not self.gas_connected or not self.gas_controller:
            # 시뮬레이션 데이터
            import random
            for device_id in self.gas_data:
                self.gas_data[device_id]['pressure'] = random.uniform(0.5, 2.0)
                self.gas_data[device_id]['temperature'] = random.uniform(20, 30)
                self.gas_data[device_id]['setpoint'] = 100.0 if self.gas_data[device_id]['valve_open'] else 0.0
            return
        
        try:
            all_data = self.gas_controller.read_all_devices()
            for device_id, data in all_data.items():
                self.gas_data[device_id]['pressure'] = data.pressure
                self.gas_data[device_id]['temperature'] = data.temperature
                self.gas_data[device_id]['setpoint'] = data.setpoint
        except Exception as e:
            print(f"가스 데이터 읽기 오류: {e}")
    
    def _on_motor_log(self, message: str):
        """모터 컨트롤러 로그 콜백"""
        print(f"[Motor] {message}")
    
    def connect_motor(self) -> bool:
        """모터 드라이버 연결"""
        if not self.motor_controller:
            self._update_connection_status("❌ 드라이버 없음", "#dc3545")
            return False
        
        try:
            if self.motor_controller.connect():
                self.motor_connected = True
                self._update_connection_status(f"✅ 연결됨 ({self.com_port})", "#28a745")
                return True
            else:
                self.motor_connected = False
                self._update_connection_status("❌ 연결 실패", "#dc3545")
                return False
        except Exception as e:
            self.motor_connected = False
            self._update_connection_status(f"❌ 오류: {e}", "#dc3545")
            return False
    
    def disconnect_motor(self):
        """모터 드라이버 연결 해제"""
        if self.motor_controller:
            self.motor_controller.disconnect()
        self.motor_connected = False
        self._update_connection_status("⚫ 연결 안됨", "#666666")
    
    def _on_connect_click(self):
        """연결 버튼 클릭"""
        if hasattr(self, 'port_input') and self.port_input:
            self.com_port = self.port_input.value
        
        # 기존 연결 해제
        if self.motor_connected:
            self.disconnect_motor()
        
        # 새 컨트롤러 생성 및 연결
        if MOTOR_DRIVER_AVAILABLE:
            self.motor_controller = MotorController(
                port=self.com_port,
                baudrate=self.baudrate
            )
            self.motor_controller.on_log = self._on_motor_log
        
        self.connect_motor()
    
    def _update_connection_status(self, text: str, color: str):
        """연결 상태 UI 업데이트"""
        if self.connection_status:
            self.connection_status.value = text
            self.connection_status.color = color
            try:
                self.page.update()
            except:
                pass
    
    def _send_motor_command(self, motor_id: str, action: str, speed: int = 1000) -> bool:
        """
        모터 명령 전송
        
        Args:
            motor_id: 모터 ID (upper_stage, upper_rotate, lower_stage, lower_rotate)
            action: 동작 (move_plus, move_minus, rotate_cw, rotate_ccw, stop)
            speed: 속도 (1~8000)
        """
        if not self.motor_connected or not self.motor_controller:
            print(f"[시뮬레이션] {motor_id}: {action}, 속도={speed}")
            return True  # 시뮬레이션 모드에서는 항상 성공
        
        try:
            if action == "stop":
                return self.motor_controller.stop_motor(motor_id)
            
            # 방향 변환
            direction_map = {
                "move_plus": "plus",
                "move_minus": "minus",
                "rotate_cw": "cw",
                "rotate_ccw": "ccw",
            }
            direction = direction_map.get(action, "plus")
            
            return self.motor_controller.start_motor(motor_id, direction, speed)
            
        except Exception as e:
            print(f"모터 명령 오류: {e}")
            return False
    
    def _stop_all_motors(self):
        """모든 모터 정지"""
        if self.motor_controller and self.motor_connected:
            self.motor_controller.stop_all()
        
        for motor_id in self.motor_speeds:
            self.motor_speeds[motor_id] = 0
    
    # ==================== 거리/각도 변환 유틸리티 ====================
    
    def mm_to_pulse(self, mm: float) -> int:
        """mm를 펄스로 변환"""
        return int(mm * self.PULSE_PER_MM)
    
    def pulse_to_mm(self, pulse: int) -> float:
        """펄스를 mm로 변환"""
        return pulse / self.PULSE_PER_MM
    
    def degree_to_pulse(self, degree: float) -> int:
        """각도를 펄스로 변환"""
        return int(degree / self.STEP_ANGLE)
    
    def pulse_to_degree(self, pulse: int) -> float:
        """펄스를 각도로 변환"""
        return pulse * self.STEP_ANGLE
    
    def build(self, navigate_to: Callable):
        """스케줄러 화면 빌드 - 왼쪽(설정) / 오른쪽(간트차트)"""
        
        # pubsub 구독 (UI 업데이트용)
        self.page.pubsub.subscribe(self._on_pubsub_message)
        
        # 연결 상태 텍스트
        self.connection_status = ft.Text("⚫ 연결 안됨", size=12, color="#666666")
        
        # COM 포트 입력
        self.port_input = ft.TextField(
            value=self.com_port,
            width=80,
            height=35,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )
        
        # 상단 헤더
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        icon_color="#333333",
                        on_click=lambda _: navigate_to("home"),
                    ),
                    ft.Text("Motorized Pulling Control", size=20, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(expand=True),
                    # 연결 설정
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("포트:", size=12, color="#666666"),
                                self.port_input,
                                ft.ElevatedButton(
                                    "연결",
                                    bgcolor="#007bff",
                                    color="#ffffff",
                                    height=32,
                                    on_click=lambda _: self._on_connect_click(),
                                ),
                                ft.ElevatedButton(
                                    "해제",
                                    bgcolor="#6c757d",
                                    color="#ffffff",
                                    height=32,
                                    on_click=lambda _: self.disconnect_motor(),
                                ),
                                self.connection_status,
                            ],
                            spacing=8,
                            alignment=ft.MainAxisAlignment.END,
                        ),
                        padding=ft.padding.only(right=15),
                    ),
                    self._build_control_buttons(),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=15,
            bgcolor="#ffffff",
            border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
        )
        
        # 상태 표시
        self.status_text = ft.Text("⏸ 대기 중", size=14, color="#666666")
        self.elapsed_text = ft.Text("경과: 00:00:00", size=14, color="#333333", weight=ft.FontWeight.BOLD)
        
        status_bar = ft.Container(
            content=ft.Row(
                [
                    self.status_text,
                    ft.Container(expand=True),
                    self.elapsed_text,
                ],
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            bgcolor="#f8f9fa",
        )
        
        # ==================== 왼쪽: 스케줄 설정 패널 ====================
        left_panel = self._build_schedule_settings_panel()
        
        # ==================== 오른쪽: 간트차트 (타임라인) ====================
        right_panel = self._build_gantt_chart_panel()
        
        # 메인 컨텐츠: 왼쪽 + 오른쪽
        main_content = ft.Row(
            [
                left_panel,
                right_panel,
            ],
            spacing=0,
            expand=True,
        )
        
        # 플로팅 모니터 패널 생성
        self.floating_panel = self._build_floating_monitor()
        
        # Stack으로 감싸서 플로팅 패널 오버레이
        return ft.Stack(
            [
                # 메인 화면
                ft.Container(
                    content=ft.Column(
                        [header, status_bar, main_content],
                        expand=True,
                        spacing=0,
                    ),
                    expand=True,
                    bgcolor="#f8f9fc",
                ),
                # 플로팅 모니터 패널
                self.floating_panel,
            ],
            expand=True,
        )
    
    def _build_floating_monitor(self):
        """플로팅 실시간 모니터 패널 (라인 차트 포함)"""
        
        # 경과 시간 라벨
        self.floating_elapsed_text = ft.Text("00:00:00", size=16, weight=ft.FontWeight.BOLD, color="#5B6EE1")
        
        # 그래프 설정
        self.max_speed = 8000
        self.max_points = 30  # 최근 30개 포인트
        
        # ==================== 모터 그래프 ====================
        # 그래프 데이터 (각 모터별)
        self.line_chart_data = {device["id"]: [] for device in self.devices}
        
        # LineChartData 생성 (각 모터별)
        self.line_data_series = []
        for device in self.devices:
            data_series = fch.LineChartData(
                points=[fch.LineChartDataPoint(0, 0)],
                stroke_width=2,
                color=device["color"],
                curved=True,
                rounded_stroke_cap=True,
            )
            self.line_data_series.append(data_series)
        
        # 모터 LineChart 생성
        self.line_chart = fch.LineChart(
            data_series=self.line_data_series,
            min_y=0,
            max_y=self.max_speed,
            min_x=0,
            max_x=self.max_points,
            expand=False,
            height=100,
            width=360,
            left_axis=fch.ChartAxis(label_size=30),
            bottom_axis=fch.ChartAxis(label_size=0),
            horizontal_grid_lines=fch.ChartGridLines(interval=2000, color="#e8e8e8", width=1),
            tooltip=fch.LineChartTooltip(bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE)),
        )
        
        # 모터별 범례
        legend_row = ft.Row(
            [
                ft.Row([
                    ft.Container(width=12, height=3, bgcolor=device["color"], border_radius=2),
                    ft.Text(device["name"][:4], size=9, color="#666666"),
                ], spacing=3)
                for device in self.devices
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        # ==================== 가스 그래프 ====================
        # 가스 그래프 데이터 (압력, 온도, 셋포인트)
        self.gas_line_chart_data = {
            'mfc_pressure': [],
            'mfc_temperature': [],
            'mfc_setpoint': [],
            'bpr_pressure': [],
            'bpr_temperature': [],
            'bpr_setpoint': [],
        }
        
        # 가스 그래프 색상
        gas_chart_colors = {
            'mfc_pressure': "#007bff",      # 파랑
            'mfc_temperature': "#dc3545",   # 빨강
            'mfc_setpoint': "#28a745",      # 초록
            'bpr_pressure': "#17a2b8",      # 청록
            'bpr_temperature': "#fd7e14",   # 주황
            'bpr_setpoint': "#6f42c1",      # 보라
        }
        
        # 가스 LineChartData 생성
        self.gas_line_data_series = []
        gas_data_keys = ['mfc_pressure', 'mfc_temperature', 'mfc_setpoint', 
                        'bpr_pressure', 'bpr_temperature', 'bpr_setpoint']
        for key in gas_data_keys:
            data_series = fch.LineChartData(
                points=[fch.LineChartDataPoint(0, 0)],
                stroke_width=2,
                color=gas_chart_colors[key],
                curved=True,
                rounded_stroke_cap=True,
            )
            self.gas_line_data_series.append(data_series)
        
        # 가스 LineChart 생성
        self.gas_line_chart = fch.LineChart(
            data_series=self.gas_line_data_series,
            min_y=0,
            max_y=100,  # 가스 데이터 범위 (필요시 동적 조정)
            min_x=0,
            max_x=self.max_points,
            expand=False,
            height=100,
            width=360,
            left_axis=fch.ChartAxis(label_size=30),
            bottom_axis=fch.ChartAxis(label_size=0),
            horizontal_grid_lines=fch.ChartGridLines(interval=20, color="#e8e8e8", width=1),
            tooltip=fch.LineChartTooltip(bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE)),
        )
        
        # 가스 범례
        gas_legend_items = [
            ("P1", "#007bff"),   # MFC1 압력
            ("T1", "#dc3545"),   # MFC1 온도
            ("SP1", "#28a745"),  # MFC1 셋포인트
            ("P2", "#17a2b8"),   # MFC2 압력
            ("T2", "#fd7e14"),   # MFC2 온도
            ("SP2", "#6f42c1"),  # MFC2 셋포인트
        ]
        gas_legend_row = ft.Row(
            [
                ft.Row([
                    ft.Container(width=10, height=3, bgcolor=color, border_radius=2),
                    ft.Text(label, size=8, color="#666666"),
                ], spacing=2)
                for label, color in gas_legend_items
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        # 각 모터별 현재 속도 표시 (가로 막대)
        self.bar_containers = {}
        speed_display_rows = []
        for device in self.devices:
            speed_label = ft.Text("0", size=11, weight=ft.FontWeight.BOLD, color=device["color"], width=45, text_align=ft.TextAlign.RIGHT)
            self.speed_labels[device["id"]] = speed_label
            
            # 가로 막대
            bar = ft.Container(
                width=0,
                height=14,
                bgcolor=device["color"],
                border_radius=ft.border_radius.only(top_right=3, bottom_right=3),
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            )
            self.bar_containers[device["id"]] = bar
            
            progress = ft.ProgressBar(
                value=0,
                width=70,
                color=device["color"],
                bgcolor="#e8e8e8",
            )
            self.progress_bars[device["id"]] = progress
            
            speed_display_rows.append(
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(device["icon"], size=11, color=device["color"]),
                            width=14,
                        ),
                        ft.Text(device["name"][:4], size=9, color="#444444", width=35),
                        ft.Container(
                            content=ft.Stack([
                                ft.Container(width=100, height=14, bgcolor="#f0f0f0", border_radius=3),
                                bar,
                            ]),
                            width=100,
                            height=14,
                        ),
                        speed_label,
                    ],
                    spacing=4,
                )
            )
        
        # 최대화/최소화 버튼
        self.maximize_btn = ft.IconButton(
            ft.Icons.FULLSCREEN,
            icon_size=16,
            icon_color="#5B6EE1",
            tooltip="최대화",
            on_click=lambda _: self._toggle_maximize_floating_panel(),
        )
        
        # 플로팅 패널 내용
        self.floating_panel_content = ft.Container(
            content=ft.Column(
                [
                    # 헤더
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.SHOW_CHART, size=18, color="#5B6EE1"),
                                ft.Text("실시간 모니터", size=13, weight=ft.FontWeight.BOLD, color="#333333"),
                                ft.Container(expand=True),
                                self.maximize_btn,
                                ft.IconButton(
                                    ft.Icons.CLOSE,
                                    icon_size=16,
                                    icon_color="#888888",
                                    tooltip="닫기",
                                    on_click=lambda _: self._toggle_floating_panel(False),
                                ),
                            ],
                        ),
                        padding=ft.padding.only(left=12, right=4, top=8, bottom=8),
                        bgcolor="#f8f9fc",
                        border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
                    ),
                    
                    # 경과 시간
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.TIMER, size=16, color="#5B6EE1"),
                                ft.Text("경과 시간:", size=12, color="#666666"),
                                self.floating_elapsed_text,
                            ],
                            spacing=8,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        bgcolor="#f0f4ff",
                    ),
                    
                    # 라인 차트 (히스토리)
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(
                                    content=self.line_chart,
                                    bgcolor="#fafafa",
                                    border_radius=8,
                                    border=ft.border.all(1, "#e0e0e0"),
                                    padding=5,
                                ),
                                legend_row,
                            ],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.only(left=12, right=12, top=8, bottom=4),
                    ),
                    
                    # 모터 상태 표시 (2열)
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(speed_display_rows[:2], spacing=5),
                                ft.Column(speed_display_rows[2:], spacing=5),
                            ],
                            spacing=16,
                        ),
                        padding=ft.padding.only(left=12, right=12, bottom=8, top=6),
                        bgcolor="#ffffff",
                    ),
                    
                    # 구분선
                    ft.Container(
                        content=ft.Divider(height=1, color="#e0e0e0"),
                        padding=ft.padding.symmetric(horizontal=12),
                    ),
                    
                    # 가스 그래프 섹션
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.AIR, size=14, color="#17a2b8"),
                                        ft.Text("가스 모니터링", size=11, weight=ft.FontWeight.BOLD, color="#333333"),
                                    ],
                                    spacing=6,
                                ),
                                ft.Container(
                                    content=self.gas_line_chart,
                                    bgcolor="#fafafa",
                                    border_radius=8,
                                    border=ft.border.all(1, "#e0e0e0"),
                                    padding=5,
                                ),
                                gas_legend_row,
                            ],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.only(left=12, right=12, top=8, bottom=4),
                    ),
                    
                    # 가스 상태 표시 섹션
                    self._build_gas_monitor_section(),
                ],
                spacing=0,
                scroll="auto",
            ),
            width=420,
            bgcolor="#ffffff",
            border_radius=12,
            border=ft.border.all(1, "#d0d0d0"),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=12,
                color=ft.Colors.with_opacity(0.2, "#000000"),
            ),
            visible=False,
        )
        
        # 우측 하단에 배치 (부모 Container도 visible 제어 필요)
        self.floating_panel_wrapper = ft.Container(
            content=self.floating_panel_content,
            right=20,
            bottom=20,
            visible=False,  # 부모도 숨김 처리
        )
        return self.floating_panel_wrapper
    
    def _build_gas_monitor_section(self):
        """가스 모니터링 섹션 빌드"""
        # 가스 장치 상태 표시 라벨
        self.gas_labels = {
            'mfc_pressure': ft.Text("--", size=11, color="#007bff", weight=ft.FontWeight.BOLD),
            'mfc_temperature': ft.Text("--", size=11, color="#dc3545"),
            'mfc_setpoint': ft.Text("--", size=11, color="#28a745"),
            'bpr_pressure': ft.Text("--", size=11, color="#17a2b8", weight=ft.FontWeight.BOLD),
            'bpr_temperature': ft.Text("--", size=11, color="#dc3545"),
            'bpr_setpoint': ft.Text("--", size=11, color="#28a745"),
        }
        
        # 가스 밸브 상태 아이콘
        self.gas_valve_icons = {
            'mfc': ft.Icon(ft.Icons.CIRCLE, size=10, color="#dc3545"),
            'bpr': ft.Icon(ft.Icons.CIRCLE, size=10, color="#dc3545"),
        }
        
        return ft.Container(
            content=ft.Column([
                # 헤더
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.AIR, size=14, color="#17a2b8"),
                        ft.Text("가스 모니터링", size=11, weight=ft.FontWeight.BOLD, color="#333333"),
                    ], spacing=6),
                    padding=ft.padding.only(left=12, top=8, bottom=4),
                ),
                
                # MFC (Mass Flow Controller)
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Row([
                                self.gas_valve_icons['mfc'],
                                ft.Text("MFC#1", size=10, color="#666666", width=40),
                            ], spacing=4),
                            width=60,
                        ),
                        ft.Text("P:", size=9, color="#888888"),
                        self.gas_labels['mfc_pressure'],
                        ft.Container(width=4),
                        ft.Text("T:", size=9, color="#888888"),
                        self.gas_labels['mfc_temperature'],
                        ft.Container(width=4),
                        ft.Text("SP:", size=9, color="#888888"),
                        self.gas_labels['mfc_setpoint'],
                    ], spacing=3),
                    padding=ft.padding.symmetric(horizontal=12, vertical=4),
                ),
                
                # BPR (Back Pressure Regulator)
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Row([
                                self.gas_valve_icons['bpr'],
                                ft.Text("MFC#2", size=10, color="#666666", width=40),
                            ], spacing=4),
                            width=60,
                        ),
                        ft.Text("P:", size=9, color="#888888"),
                        self.gas_labels['bpr_pressure'],
                        ft.Container(width=4),
                        ft.Text("T:", size=9, color="#888888"),
                        self.gas_labels['bpr_temperature'],
                        ft.Container(width=4),
                        ft.Text("SP:", size=9, color="#888888"),
                        self.gas_labels['bpr_setpoint'],
                    ], spacing=3),
                    padding=ft.padding.only(left=12, right=12, top=4, bottom=10),
                ),
            ], spacing=0),
            bgcolor="#f0f8ff",
        )
    
    def _update_gas_monitor(self):
        """가스 모니터링 데이터 업데이트"""
        # 가스 데이터 읽기
        self.read_gas_data()
        
        # UI 업데이트
        for device_id in ['mfc', 'bpr']:
            data = self.gas_data.get(device_id, {})
            
            # 라벨 업데이트
            if hasattr(self, 'gas_labels') and f'{device_id}_pressure' in self.gas_labels:
                self.gas_labels[f'{device_id}_pressure'].value = f"{data.get('pressure', 0):.2f}"
            if hasattr(self, 'gas_labels') and f'{device_id}_temperature' in self.gas_labels:
                self.gas_labels[f'{device_id}_temperature'].value = f"{data.get('temperature', 0):.1f}°C"
            if hasattr(self, 'gas_labels') and f'{device_id}_setpoint' in self.gas_labels:
                self.gas_labels[f'{device_id}_setpoint'].value = f"{data.get('setpoint', 0):.1f}"
            
            # 밸브 상태 아이콘
            if hasattr(self, 'gas_valve_icons') and device_id in self.gas_valve_icons:
                is_open = data.get('valve_open', False)
                self.gas_valve_icons[device_id].color = "#28a745" if is_open else "#dc3545"
            
            # 그래프 데이터 추가
            for key in ['pressure', 'temperature', 'setpoint']:
                graph_key = f'{device_id}_{key}'
                if hasattr(self, 'gas_line_chart_data') and graph_key in self.gas_line_chart_data:
                    self.gas_line_chart_data[graph_key].append(data.get(key, 0))
                    # 최대 포인트 수 유지
                    if len(self.gas_line_chart_data[graph_key]) > self.max_points:
                        self.gas_line_chart_data[graph_key].pop(0)
        
        # 가스 LineChart 업데이트
        self._update_gas_line_chart()
    
    def _update_gas_line_chart(self):
        """가스 라인 차트 업데이트"""
        if not hasattr(self, 'gas_line_chart') or not hasattr(self, 'gas_line_data_series'):
            return
        
        gas_data_keys = ['mfc_pressure', 'mfc_temperature', 'mfc_setpoint', 
                        'bpr_pressure', 'bpr_temperature', 'bpr_setpoint']
        
        max_val = 0
        for i, key in enumerate(gas_data_keys):
            data = self.gas_line_chart_data.get(key, [])
            if data:
                max_val = max(max_val, max(data))
                # 데이터 포인트 생성
                points = [
                    fch.LineChartDataPoint(x=idx, y=val)
                    for idx, val in enumerate(data)
                ]
                if i < len(self.gas_line_data_series):
                    self.gas_line_data_series[i].points = points
        
        # Y축 범위 동적 조정
        if max_val > 0:
            self.gas_line_chart.max_y = max(100, max_val * 1.2)
        
        # X축 범위 업데이트
        data_len = max(len(d) for d in self.gas_line_chart_data.values()) if self.gas_line_chart_data else 0
        if data_len > self.max_points:
            self.gas_line_chart.min_x = data_len - self.max_points
            self.gas_line_chart.max_x = data_len
    
    def _update_line_chart(self, motor_speeds: dict):
        """라인 차트 업데이트 (히스토리)"""
        # 데이터 추가
        for device_id, speed in motor_speeds.items():
            if device_id in self.line_chart_data:
                self.line_chart_data[device_id].append(speed)
                # 최대 포인트 수 유지
                if len(self.line_chart_data[device_id]) > self.max_points:
                    self.line_chart_data[device_id].pop(0)
        
        # LineChart 데이터 업데이트
        for i, device in enumerate(self.devices):
            device_id = device["id"]
            data = self.line_chart_data.get(device_id, [])
            
            if data and i < len(self.line_data_series):
                # 데이터 포인트 생성
                points = [
                    fch.LineChartDataPoint(x=idx, y=speed)
                    for idx, speed in enumerate(data)
                ]
                self.line_data_series[i].points = points
        
        # X축 범위 업데이트 (스크롤 효과)
        if hasattr(self, 'line_chart'):
            data_len = max(len(d) for d in self.line_chart_data.values()) if self.line_chart_data else 0
            if data_len > self.max_points:
                self.line_chart.min_x = data_len - self.max_points
                self.line_chart.max_x = data_len
    
    def _toggle_floating_panel(self, show: bool):
        """플로팅 패널 표시/숨김"""
        self.floating_visible = show
        
        # 부모 wrapper와 내용 모두 visible 토글
        if hasattr(self, 'floating_panel_wrapper') and self.floating_panel_wrapper:
            self.floating_panel_wrapper.visible = show
        if hasattr(self, 'floating_panel_content') and self.floating_panel_content:
            self.floating_panel_content.visible = show
        
        # 그래프 데이터 초기화
        if show:
            if hasattr(self, 'line_chart_data'):
                for device_id in self.line_chart_data:
                    self.line_chart_data[device_id] = []
            # 라인 차트 초기화
            if hasattr(self, 'line_data_series'):
                for data_series in self.line_data_series:
                    data_series.points = [fch.LineChartDataPoint(0, 0)]
            # X축 초기화
            if hasattr(self, 'line_chart'):
                self.line_chart.min_x = 0
                self.line_chart.max_x = self.max_points
        
        try:
            self.page.update()
        except:
            pass
    
    def _toggle_maximize_floating_panel(self):
        """플로팅 패널 최대화/최소화 토글"""
        self.floating_maximized = not self.floating_maximized
        
        if hasattr(self, 'floating_panel_content') and self.floating_panel_content:
            if self.floating_maximized:
                # 최대화 상태
                self.floating_panel_content.width = None  # 자동 크기
                self.floating_panel_content.height = None
                
                # 차트 크기 확대
                if hasattr(self, 'line_chart'):
                    self.line_chart.height = 300
                    self.line_chart.width = None  # 자동 너비
                
                # 버튼 아이콘 변경
                if hasattr(self, 'maximize_btn'):
                    self.maximize_btn.icon = ft.Icons.FULLSCREEN_EXIT
                    self.maximize_btn.tooltip = "최소화"
                
                # 부모 컨테이너 위치/크기 조정
                if hasattr(self, 'floating_panel_wrapper') and self.floating_panel_wrapper:
                    self.floating_panel_wrapper.right = 20
                    self.floating_panel_wrapper.bottom = 20
                    self.floating_panel_wrapper.left = 20
                    self.floating_panel_wrapper.top = 100
                
            else:
                # 일반(최소화) 상태
                self.floating_panel_content.width = 420
                self.floating_panel_content.height = None
                
                # 차트 크기 원래대로
                if hasattr(self, 'line_chart'):
                    self.line_chart.height = 120
                    self.line_chart.width = 360
                
                # 버튼 아이콘 변경
                if hasattr(self, 'maximize_btn'):
                    self.maximize_btn.icon = ft.Icons.FULLSCREEN
                    self.maximize_btn.tooltip = "최대화"
                
                # 부모 컨테이너 위치 원래대로
                if hasattr(self, 'floating_panel_wrapper') and self.floating_panel_wrapper:
                    self.floating_panel_wrapper.right = 20
                    self.floating_panel_wrapper.bottom = 20
                    self.floating_panel_wrapper.left = None
                    self.floating_panel_wrapper.top = None
            
            try:
                self.page.update()
            except:
                pass
    
    def _update_floating_monitor(self):
        """플로팅 모니터 업데이트 (2초마다 호출)"""
        if not self.floating_visible:
            return
        
        try:
            # 경과 시간 업데이트
            h, rem = divmod(self.elapsed_seconds, 3600)
            m, s = divmod(rem, 60)
            if hasattr(self, 'floating_elapsed_text') and self.floating_elapsed_text:
                self.floating_elapsed_text.value = f"{h:02d}:{m:02d}:{s:02d}"
            
            for device in self.devices:
                device_id = device["id"]
                speed = self.motor_speeds.get(device_id, 0)
                
                # 그래프 데이터 추가
                self.graph_data[device_id].append(speed)
                if len(self.graph_data[device_id]) > self.max_graph_points:
                    self.graph_data[device_id].pop(0)
                
                # 프로그레스 바 업데이트 (0~8000 → 0~1)
                if device_id in self.progress_bars:
                    self.progress_bars[device_id].value = min(speed / 8000, 1.0)
                
                # 속도 라벨 업데이트
                if device_id in self.speed_labels:
                    self.speed_labels[device_id].value = str(int(speed))
            
            # 가스 모니터링 업데이트
            if hasattr(self, 'gas_labels'):
                self._update_gas_monitor()
            
            self.page.update()
        except Exception as e:
            print(f"모니터 업데이트 오류: {e}")
    
    def _build_schedule_settings_panel(self):
        """왼쪽 패널: 스케줄 설정 (60% 너비)"""
        
        # 상단 모드 선택 버튼들 (5개, 가로 정렬) - 동적 업데이트를 위해 Container로 감싸기
        self.mode_buttons_container = ft.Container(
            content=self._build_mode_buttons(),
            padding=ft.padding.symmetric(vertical=15),
            bgcolor="#f8f9fc",
            border=ft.border.only(bottom=ft.BorderSide(1, "#e8e8e8")),
        )
        
        # 동적 콘텐츠 영역 (모드에 따라 변경)
        self.left_panel_content = ft.Container(
            content=self._build_mode_content(self.current_mode),
            expand=True,
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    # 모드 선택 버튼
                    self.mode_buttons_container,
                    
                    # 동적 콘텐츠
                    self.left_panel_content,
                ],
                spacing=0,
                expand=True,
            ),
            expand=3,  # 60% (3:2 비율)
            bgcolor="#ffffff",
            border=ft.border.only(right=ft.BorderSide(1, "#e8e8e8")),
        )
    
    def _build_mode_buttons(self):
        """모드 선택 버튼들 빌드"""
        return ft.Row(
            [
                self._mode_button("수동", ft.Icons.TOUCH_APP, "#FF6B6B", "manual"),
                self._mode_button("상부\n스테이지", ft.Icons.ARROW_UPWARD, "#2a9d8f", "upper_stage"),
                self._mode_button("상부\n회전", ft.Icons.ROTATE_RIGHT, "#e76f51", "upper_rotate"),
                self._mode_button("하부\n스테이지", ft.Icons.ARROW_DOWNWARD, "#9b5de5", "lower_stage"),
                self._mode_button("하부\n회전", ft.Icons.ROTATE_LEFT, "#f4a261", "lower_rotate"),
                self._mode_button("MFC", ft.Icons.AIR, "#007bff", "mfc"),
                self._mode_button("BPR", ft.Icons.COMPRESS, "#17a2b8", "bpr"),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll="auto",
        )
    
    def _mode_button(self, label, icon, color, mode):
        """모드 선택 버튼"""
        is_active = self.current_mode == mode
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=24, color="#ffffff" if is_active else color),
                        bgcolor=color if is_active else "#f0f0f0",
                        border_radius=12,
                        padding=12,
                    ),
                    ft.Text(
                        label, 
                        size=10, 
                        color=color if is_active else "#888888",
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            on_click=lambda _, m=mode: self._switch_mode(m),
            ink=True,
            border_radius=12,
            padding=8,
            border=ft.border.all(2, color) if is_active else None,
        )
    
    def _switch_mode(self, mode):
        """모드 전환"""
        self.current_mode = mode
        # 버튼 테두리 업데이트
        if self.mode_buttons_container:
            self.mode_buttons_container.content = self._build_mode_buttons()
        # 콘텐츠 업데이트
        if self.left_panel_content:
            self.left_panel_content.content = self._build_mode_content(mode)
        self.page.update()
    
    def _build_mode_content(self, mode):
        """모드별 콘텐츠 빌드"""
        if mode == "manual":
            return self._build_manual_control_panel()
        else:
            # 모터 장치 확인
            device = next((d for d in self.devices if d["id"] == mode), None)
            if device:
                return self._build_motor_control_panel(device)
            
            # 가스 장치 확인
            gas_device = next((d for d in self.gas_devices if d["id"] == mode), None)
            if gas_device:
                return self._build_gas_control_panel(gas_device)
        return ft.Container()
    
    def _build_manual_control_panel(self):
        """수동 제어 패널 - 버튼 누르고 있을 때만 작동"""
        
        # 속도 입력 필드
        low_speed = 1000
        high_speed = 5000
        
        low_speed_input = ft.TextField(
            value=str(low_speed),
            width=70,
            height=35,
            text_size=12,
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        
        high_speed_input = ft.TextField(
            value=str(high_speed),
            width=70,
            height=35,
            text_size=12,
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        
        # 저속/고속 토글
        speed_toggle = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("속도 모드:", size=12, color="#666666"),
                            ft.Container(width=10),
                            ft.Container(
                                content=ft.Text("저속", size=11, color="#ffffff" if self.speed_mode == "low" else "#666666"),
                                bgcolor="#5B6EE1" if self.speed_mode == "low" else "#e0e0e0",
                                border_radius=ft.border_radius.only(top_left=8, bottom_left=8),
                                padding=ft.padding.symmetric(horizontal=15, vertical=8),
                                on_click=lambda _: self._set_speed_mode("low"),
                            ),
                            ft.Container(
                                content=ft.Text("고속", size=11, color="#ffffff" if self.speed_mode == "high" else "#666666"),
                                bgcolor="#FF6B6B" if self.speed_mode == "high" else "#e0e0e0",
                                border_radius=ft.border_radius.only(top_right=8, bottom_right=8),
                                padding=ft.padding.symmetric(horizontal=15, vertical=8),
                                on_click=lambda _: self._set_speed_mode("high"),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.Text("저속:", size=11, color="#5B6EE1"),
                            low_speed_input,
                            ft.Container(width=15),
                            ft.Text("고속:", size=11, color="#FF6B6B"),
                            high_speed_input,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Text("(1~8000)", size=10, color="#888888"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=15,
        )
        
        # 속도값 저장
        self.manual_low_speed = low_speed_input
        self.manual_high_speed = high_speed_input
        
        # 4개 모터 수동 제어 그리드
        manual_controls = ft.Column(
            [
                # 상부 스테이지 & 회전
                ft.Row(
                    [
                        self._manual_motor_card("upper_stage", "상부 스테이지", "#2a9d8f", "stage"),
                        self._manual_motor_card("upper_rotate", "상부 회전", "#e76f51", "rotate"),
                    ],
                    spacing=15,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                # 하부 스테이지 & 회전
                ft.Row(
                    [
                        self._manual_motor_card("lower_stage", "하부 스테이지", "#9b5de5", "stage"),
                        self._manual_motor_card("lower_rotate", "하부 회전", "#f4a261", "rotate"),
                    ],
                    spacing=15,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=15,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        
        # ==================== 가스 제어기 섹션 ====================
        gas_controls = ft.Container(
            content=ft.Column(
                [
                    ft.Text("⛽ 가스 제어기", size=14, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            self._gas_valve_card("mfc", "MFC (ID:5)", "#007bff"),
                            self._gas_valve_card("bpr", "BPR (ID:6)", "#17a2b8"),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=15,
            bgcolor="#f0f8ff",
            border_radius=12,
            border=ft.border.all(1, "#007bff"),
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=10),
                    ft.Text("🎮 수동 제어", size=16, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Text("버튼을 누르고 있는 동안만 모터가 작동합니다", size=11, color="#888888"),
                    ft.Container(height=15),
                    speed_toggle,
                    ft.Container(height=20),
                    manual_controls,
                    ft.Container(height=25),
                    gas_controls,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll="auto",
                expand=True,
            ),
            padding=20,
            expand=True,
        )
    
    def _manual_motor_card(self, device_id, name, color, motor_type):
        """수동 제어용 모터 카드"""
        if motor_type == "stage":
            # 스테이지: 상하 버튼
            buttons = ft.Row(
                [
                    self._hold_button("▲", color, device_id, "up"),
                    self._hold_button("▼", color, device_id, "down"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        else:
            # 회전: 좌우 버튼
            buttons = ft.Row(
                [
                    self._hold_button("◀", color, device_id, "left"),
                    self._hold_button("▶", color, device_id, "right"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        
        # 정지 버튼
        stop_button = ft.Container(
            content=ft.Text("■ 정지", size=11, color="#ffffff", weight=ft.FontWeight.BOLD),
            width=120,
            height=30,
            bgcolor="#dc3545",
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._stop_single_motor(device_id),
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(name, size=12, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(height=8),
                    buttons,
                    ft.Container(height=8),
                    stop_button,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            width=180,
            padding=15,
            bgcolor="#f8f9fa",
            border_radius=12,
            border=ft.border.all(1, color),
        )
    
    def _stop_single_motor(self, motor_id: str):
        """단일 모터 정지"""
        success = self._send_motor_command(motor_id, "stop", 0)
        self.motor_speeds[motor_id] = 0
        
        status_icon = "✅" if success else "❌"
        print(f"[정지] {status_icon} {motor_id}")
    
    def _gas_valve_card(self, device_id: str, name: str, color: str):
        """가스 밸브 제어 카드"""
        is_open = self.gas_data.get(device_id, {}).get('valve_open', False)
        
        # 밸브 상태 표시
        status_text = ft.Text(
            "열림 🟢" if is_open else "닫힘 🔴",
            size=11,
            color="#28a745" if is_open else "#dc3545",
            weight=ft.FontWeight.BOLD,
        )
        
        # 열기/닫기 버튼
        open_btn = ft.Container(
            content=ft.Text("열기", size=11, color="#ffffff", weight=ft.FontWeight.BOLD),
            width=55,
            height=32,
            bgcolor="#28a745" if not is_open else "#6c757d",
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _, d=device_id: self._on_gas_valve_click(d, True),
        )
        
        close_btn = ft.Container(
            content=ft.Text("닫기", size=11, color="#ffffff", weight=ft.FontWeight.BOLD),
            width=55,
            height=32,
            bgcolor="#dc3545" if is_open else "#6c757d",
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _, d=device_id: self._on_gas_valve_click(d, False),
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AIR, size=16, color=color),
                            ft.Text(name, size=11, weight=ft.FontWeight.BOLD, color="#333333"),
                        ],
                        spacing=5,
                    ),
                    ft.Container(height=5),
                    status_text,
                    ft.Container(height=8),
                    ft.Row([open_btn, close_btn], spacing=8),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            width=150,
            padding=12,
            bgcolor="#ffffff",
            border_radius=10,
            border=ft.border.all(1, color),
        )
    
    def _on_gas_valve_click(self, device_id: str, is_open: bool):
        """가스 밸브 클릭 이벤트"""
        success = self.toggle_gas_valve(device_id, is_open)
        
        status_icon = "✅" if success else "❌"
        action = "열기" if is_open else "닫기"
        print(f"[가스] {status_icon} {device_id} {action}")
        
        # UI 새로고침
        if self.left_panel_content and self.current_mode == "manual":
            self.left_panel_content.content = self._build_mode_content("manual")
            self.page.update()
    
    def _hold_button(self, label, color, device_id, direction):
        """누르고 있을 때 작동하는 버튼"""
        return ft.Container(
            content=ft.Text(label, size=20, color="#ffffff", weight=ft.FontWeight.BOLD),
            width=60,
            height=50,
            bgcolor=color,
            border_radius=10,
            alignment=ft.Alignment(0, 0),
            on_click=lambda _: self._manual_motor_action(device_id, direction, "click"),
            # TODO: on_long_press_start/end 구현 필요 (flet 버전에 따라)
        )
    
    def _set_speed_mode(self, mode):
        """속도 모드 변경"""
        self.speed_mode = mode
        if self.left_panel_content:
            self.left_panel_content.content = self._build_mode_content(self.current_mode)
        self.page.update()
    
    def _manual_motor_action(self, device_id, direction, action_type):
        """수동 모터 제어 액션"""
        # 입력된 속도값 사용
        try:
            if self.speed_mode == "low":
                speed = int(self.manual_low_speed.value) if hasattr(self, 'manual_low_speed') else 1000
            else:
                speed = int(self.manual_high_speed.value) if hasattr(self, 'manual_high_speed') else 5000
            
            # 범위 제한
            speed = max(1, min(8000, speed))
        except:
            speed = 1000 if self.speed_mode == "low" else 5000
        
        # 방향에 따른 액션 매핑
        device = next((d for d in self.devices if d["id"] == device_id), None)
        motor_type = device.get("type", "stage") if device else "stage"
        
        if motor_type == "rotate":
            # 회전 모터
            action_map = {
                "left": "rotate_ccw",
                "right": "rotate_cw",
            }
        else:
            # 스테이지 모터
            action_map = {
                "up": "move_plus",
                "down": "move_minus",
            }
        
        action = action_map.get(direction, "stop")
        
        # 실제 모터 명령 전송
        success = self._send_motor_command(device_id, action, speed)
        
        status_icon = "✅" if success else "❌"
        print(f"[수동] {status_icon} {device_id} - {action} ({self.speed_mode}: {speed})")
        
        # 속도 상태 업데이트
        if success and action != "stop":
            self.motor_speeds[device_id] = speed
        else:
            self.motor_speeds[device_id] = 0
    
    def _build_gas_control_panel(self, gas_device):
        """가스 장치 제어 패널 (스케줄 모드)"""
        device_id = gas_device["id"]
        device_color = gas_device["color"]
        
        # 해당 가스 장치의 스케줄 블록들
        device_blocks = [b for b in self.schedule_blocks if b.device_id == device_id]
        
        # 스케줄 리스트
        schedule_list = []
        for idx, block in enumerate(device_blocks):
            h, m = divmod(block.start_seconds // 60, 60)
            s = block.start_seconds % 60
            start_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            dur_m, dur_s = divmod(block.duration_seconds, 60)
            dur_str = f"{dur_m}분 {dur_s}초" if dur_m > 0 else f"{dur_s}초"
            
            action_text = "열기" if block.action_name == "valve_open" else "닫기"
            
            schedule_list.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"#{idx+1}", size=11, color="#888888", width=30),
                            ft.Text(start_str, size=11, color=device_color, weight=ft.FontWeight.BOLD, width=70),
                            ft.Text(dur_str, size=11, color="#666666", width=60),
                            ft.Container(
                                content=ft.Text(action_text, size=10, color="#ffffff"),
                                bgcolor="#28a745" if block.action_name == "valve_open" else "#dc3545",
                                border_radius=4,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color="#dc3545",
                                on_click=lambda _, b=block: self._remove_schedule_block(b),
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                    bgcolor="#f8f9fa",
                    border_radius=6,
                )
            )
        
        # 새 스케줄 추가 폼
        start_time_input = ft.TextField(
            label="시작 시간 (분:초)",
            value="00:00",
            width=120,
            height=45,
            text_size=12,
        )
        
        duration_input = ft.TextField(
            label="지속 시간 (초)",
            value="60",
            width=100,
            height=45,
            text_size=12,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        
        action_dropdown = ft.Dropdown(
            label="동작",
            options=[
                ft.dropdown.Option("valve_open", "밸브 열기"),
                ft.dropdown.Option("valve_close", "밸브 닫기"),
            ],
            value="valve_open",
            width=140,
            height=50,
            text_size=12,
        )
        
        def add_gas_schedule(_):
            """가스 스케줄 추가"""
            try:
                # 시작 시간 파싱
                time_parts = start_time_input.value.split(":")
                if len(time_parts) == 2:
                    minutes = int(time_parts[0])
                    seconds = int(time_parts[1])
                elif len(time_parts) == 3:
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    minutes += hours * 60
                else:
                    minutes = int(time_parts[0])
                    seconds = 0
                
                start_seconds = minutes * 60 + seconds
                duration_seconds = int(duration_input.value)
                action_name = action_dropdown.value
                
                # 스케줄 블록 생성
                new_block = ScheduleBlock(
                    device_id=device_id,
                    start_seconds=start_seconds,
                    duration_seconds=duration_seconds,
                    action_name=action_name,
                    action_params={},
                )
                self.schedule_blocks.append(new_block)
                
                # UI 새로고침
                if self.left_panel_content:
                    self.left_panel_content.content = self._build_gas_control_panel(gas_device)
                self._refresh_timeline()
                self.page.update()
                
            except ValueError as e:
                print(f"스케줄 추가 오류: {e}")
        
        add_form = ft.Container(
            content=ft.Column(
                [
                    ft.Text("새 스케줄 추가", size=13, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Row(
                        [start_time_input, duration_input, action_dropdown],
                        spacing=10,
                    ),
                    ft.ElevatedButton(
                        "➕ 스케줄 추가",
                        bgcolor=device_color,
                        color="#ffffff",
                        on_click=add_gas_schedule,
                    ),
                ],
                spacing=10,
            ),
            padding=15,
            bgcolor="#f0f8ff",
            border_radius=10,
            border=ft.border.all(1, device_color),
        )
        
        # 현재 상태 표시
        is_open = self.gas_data.get(device_id, {}).get('valve_open', False)
        status_container = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if is_open else ft.Icons.CANCEL,
                        size=20,
                        color="#28a745" if is_open else "#dc3545",
                    ),
                    ft.Text(
                        f"현재 상태: {'열림' if is_open else '닫힘'}",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color="#28a745" if is_open else "#dc3545",
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=10,
            bgcolor="#f8f9fa",
            border_radius=8,
        )
        
        # 수동 제어 버튼
        manual_controls = ft.Container(
            content=ft.Row(
                [
                    ft.ElevatedButton(
                        "🔓 열기",
                        bgcolor="#28a745",
                        color="#ffffff",
                        on_click=lambda _: self._gas_manual_action(device_id, True),
                    ),
                    ft.ElevatedButton(
                        "🔒 닫기",
                        bgcolor="#dc3545",
                        color="#ffffff",
                        on_click=lambda _: self._gas_manual_action(device_id, False),
                    ),
                ],
                spacing=15,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=10,
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.Icon(gas_device["icon"], size=24, color=device_color),
                            ft.Text(gas_device["name"], size=18, weight=ft.FontWeight.BOLD, color="#333333"),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Text(f"Slave ID: {gas_device['slave_id']}", size=11, color="#888888"),
                    ft.Container(height=10),
                    status_container,
                    manual_controls,
                    ft.Container(height=15),
                    add_form,
                    ft.Container(height=15),
                    ft.Text(f"등록된 스케줄 ({len(device_blocks)}개)", size=13, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(height=5),
                    ft.Column(
                        schedule_list if schedule_list else [
                            ft.Text("등록된 스케줄이 없습니다", size=12, color="#888888")
                        ],
                        spacing=5,
                        scroll="auto",
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll="auto",
                expand=True,
            ),
            padding=20,
            expand=True,
        )
    
    def _gas_manual_action(self, device_id: str, is_open: bool):
        """가스 수동 열기/닫기"""
        success = self.toggle_gas_valve(device_id, is_open)
        
        # UI 새로고침
        if self.left_panel_content:
            gas_device = next((d for d in self.gas_devices if d["id"] == device_id), None)
            if gas_device:
                self.left_panel_content.content = self._build_gas_control_panel(gas_device)
        self.page.update()
    
    def _build_motor_control_panel(self, device):
        """개별 모터 제어 패널 (스케줄 모드)"""
        
        # 해당 모터의 스케줄 블록들
        device_blocks = [b for b in self.schedule_blocks if b.device_id == device["id"]]
        
        # 스케줄 리스트
        schedule_list = []
        if device_blocks:
            for block in device_blocks:
                schedule_list.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text(
                                        block.format_time(block.start_seconds), 
                                        size=11, 
                                        color="#ffffff"
                                    ),
                                    bgcolor=device["color"],
                                    border_radius=5,
                                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                ),
                                ft.Text(f"→ {block.format_time(block.end_seconds)}", size=11, color="#666666"),
                                ft.Container(expand=True),
                                ft.Text(block.action_name, size=11, color="#333333"),
                                ft.Text(f"{block.action_params.get('speed', 0)}", size=11, color="#888888"),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    icon_size=16,
                                    icon_color="#dc3545",
                                    on_click=lambda _, b=block: self._delete_block(b),
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=10,
                        bgcolor="#f8f9fa",
                        border_radius=8,
                    )
                )
        else:
            schedule_list.append(
                ft.Container(
                    content=ft.Text("등록된 스케줄이 없습니다", size=12, color="#888888"),
                    padding=20,
                    alignment=ft.Alignment(0, 0),
                )
            )
        
        # 새 스케줄 추가 폼 - 입력 필드들
        start_min_input = ft.TextField(label="시작(분)", width=70, value="0", keyboard_type=ft.KeyboardType.NUMBER)
        start_sec_input = ft.TextField(label="초", width=60, value="0", keyboard_type=ft.KeyboardType.NUMBER)
        duration_min_input = ft.TextField(label="지속(분)", width=70, value="1", keyboard_type=ft.KeyboardType.NUMBER)
        duration_sec_input = ft.TextField(label="초", width=60, value="0", keyboard_type=ft.KeyboardType.NUMBER)
        
        action_options = self._get_action_options(device)
        action_select = ft.Dropdown(
            label="동작",
            options=action_options,
            value=action_options[0].key if action_options else None,
            width=140,
        )
        speed_input = ft.TextField(label="속도", width=100, value="1000", keyboard_type=ft.KeyboardType.NUMBER)
        
        # ==================== 거리/각도 입력 ====================
        is_rotate = device.get("type") == "rotate"
        
        # 거리 또는 각도 입력
        distance_input = ft.TextField(
            label="각도 (°)" if is_rotate else "거리 (mm)",
            width=100, 
            value="10" if is_rotate else "5", 
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 펄스 변환 표시
        pulse_display = ft.Text(
            f"= {self.degree_to_pulse(10) if is_rotate else self.mm_to_pulse(5)} 펄스",
            size=11, 
            color="#5B6EE1"
        )
        
        def on_distance_change(e):
            """거리/각도 입력 시 펄스 변환"""
            try:
                val = float(distance_input.value or 0)
                if is_rotate:
                    pulses = self.degree_to_pulse(val)
                    pulse_display.value = f"= {pulses} 펄스 ({val/360:.2f}회전)"
                else:
                    pulses = self.mm_to_pulse(val)
                    pulse_display.value = f"= {pulses} 펄스 ({val/self.MM_PER_REV:.2f}회전)"
                self.page.update()
            except:
                pass
        
        distance_input.on_change = on_distance_change
        
        # 에러 메시지 표시용
        error_text = ft.Text("", size=11, color="#dc3545")
        
        def on_add_schedule(_):
            """스케줄 추가 실행"""
            start_seconds = int(start_min_input.value or 0) * 60 + int(start_sec_input.value or 0)
            duration_seconds = int(duration_min_input.value or 1) * 60 + int(duration_sec_input.value or 0)
            if duration_seconds <= 0:
                duration_seconds = 60
            
            end_seconds = start_seconds + duration_seconds
            
            # 충돌 체크 - 같은 모터의 기존 스케줄과 겹치는지 확인
            conflict = self._check_schedule_conflict(device["id"], start_seconds, end_seconds)
            if conflict:
                error_text.value = f"⚠️ 기존 스케줄과 겹칩니다! ({conflict.format_time(conflict.start_seconds)} ~ {conflict.format_time(conflict.end_seconds)})"
                self.page.update()
                return
            
            error_text.value = ""
            
            new_block = ScheduleBlock(
                device_id=device["id"],
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                action_name=action_select.value,
                action_params={"speed": int(speed_input.value or 1000)},
            )
            self.schedule_blocks.append(new_block)
            
            # 입력 필드 초기화
            start_min_input.value = "0"
            start_sec_input.value = "0"
            duration_min_input.value = "1"
            duration_sec_input.value = "0"
            speed_input.value = "1000"
            
            # UI 업데이트
            self._refresh_timeline()
            if self.left_panel_content:
                self.left_panel_content.content = self._build_mode_content(self.current_mode)
            self.page.update()
        
        # 왼쪽: 새 스케줄 추가 (세로)
        left_add_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Text("➕ 새 스케줄 추가", size=14, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(height=15),
                    
                    ft.Text("시작 시간", size=11, color="#666666"),
                    ft.Container(height=5),
                    ft.Row([start_min_input, ft.Text("분", size=11), start_sec_input, ft.Text("초", size=11)], spacing=5),
                    
                    ft.Container(height=12),
                    ft.Text("지속 시간", size=11, color="#666666"),
                    ft.Container(height=5),
                    ft.Row([duration_min_input, ft.Text("분", size=11), duration_sec_input, ft.Text("초", size=11)], spacing=5),
                    
                    ft.Container(height=12),
                    ft.Text("동작", size=11, color="#666666"),
                    ft.Container(height=5),
                    action_select,
                    
                    ft.Container(height=12),
                    ft.Text("속도 (1~8000)", size=11, color="#666666"),
                    ft.Container(height=5),
                    speed_input,
                    
                    ft.Container(height=12),
                    ft.Text("각도 / 거리 (참고용)" if is_rotate else "거리 / 각도 (참고용)", size=11, color="#666666"),
                    ft.Container(height=5),
                    ft.Row([distance_input, pulse_display], spacing=8),
                    
                    # 빠른 계산 도우미
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("📐 빠른 계산", size=10, color="#888888"),
                                ft.Text(f"• 1mm = {self.PULSE_PER_MM} 펄스", size=9, color="#666666"),
                                ft.Text(f"• 1회전 = {self.PULSE_PER_REV} 펄스 = {self.MM_PER_REV}mm", size=9, color="#666666"),
                                ft.Text(f"• 1° = {1/self.STEP_ANGLE:.2f} 펄스", size=9, color="#666666"),
                            ],
                            spacing=2,
                        ),
                        bgcolor="#f0f4ff",
                        border_radius=8,
                        padding=10,
                        margin=ft.margin.only(top=10),
                    ),
                    
                    ft.Container(height=15),
                    ft.ElevatedButton(
                        "➕ 스케줄 추가",
                        bgcolor=device["color"],
                        color="#ffffff",
                        width=200,
                        on_click=on_add_schedule,
                    ),
                    error_text,
                ],
                scroll="auto",
            ),
            padding=20,
            bgcolor="#f8f9fc",
            border=ft.border.only(right=ft.BorderSide(1, "#e8e8e8")),
            expand=True,
        )
        
        # 오른쪽: 현재 스케줄 (세로)
        right_schedule_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("📋 현재 스케줄", size=14, weight=ft.FontWeight.BOLD, color="#333333"),
                            ft.Container(expand=True),
                            ft.Container(
                                content=ft.Text(f"{len(device_blocks)}개", size=11, color=device["color"]),
                                bgcolor=f"{device['color']}20",
                                border_radius=8,
                                padding=ft.padding.symmetric(horizontal=10, vertical=3),
                            ),
                        ],
                    ),
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column(schedule_list, spacing=8),
                        expand=True,
                    ),
                ],
                scroll="auto",
                expand=True,
            ),
            padding=20,
            expand=True,
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    # 헤더
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(device["icon"], size=20, color="#ffffff"),
                                    bgcolor=device["color"],
                                    border_radius=8,
                                    padding=8,
                                ),
                                ft.Container(width=10),
                                ft.Column(
                                    [
                                        ft.Text(device["name"], size=16, weight=ft.FontWeight.BOLD, color="#333333"),
                                        ft.Text(f"Slave ID: {device['slave_id']}", size=11, color="#888888"),
                                    ],
                                    spacing=2,
                                ),
                            ],
                        ),
                        padding=15,
                        bgcolor="#ffffff",
                        border=ft.border.only(bottom=ft.BorderSide(1, "#e8e8e8")),
                    ),
                    
                    # 메인 영역: 왼쪽(추가) + 오른쪽(스케줄)
                    ft.Row(
                        [
                            left_add_panel,
                            right_schedule_panel,
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
        )
    
    def _get_action_options(self, device):
        """장치 타입에 따른 액션 옵션"""
        if device.get("type") == "rotate":
            return [
                ft.dropdown.Option("rotate_cw", "↻ 시계방향"),
                ft.dropdown.Option("rotate_ccw", "↺ 반시계방향"),
                ft.dropdown.Option("stop", "■ 정지"),
            ]
        else:
            return [
                ft.dropdown.Option("move_plus", "▲ +방향"),
                ft.dropdown.Option("move_minus", "▼ -방향"),
                ft.dropdown.Option("stop", "■ 정지"),
            ]
    
    def _check_schedule_conflict(self, device_id: str, start: int, end: int, exclude_block=None):
        """스케줄 충돌 체크 - 같은 모터에서 시간이 겹치는지 확인"""
        for block in self.schedule_blocks:
            if block.device_id != device_id:
                continue
            if exclude_block and block == exclude_block:
                continue
            # 시간 범위가 겹치는지 확인
            if not (end <= block.start_seconds or start >= block.end_seconds):
                return block  # 충돌하는 블록 반환
        return None  # 충돌 없음
    
    def _delete_block(self, block):
        """스케줄 블록 삭제"""
        if block in self.schedule_blocks:
            self.schedule_blocks.remove(block)
            self._refresh_timeline()
            if self.left_panel_content:
                self.left_panel_content.content = self._build_mode_content(self.current_mode)
            self.page.update()
    
    def _build_gantt_chart_panel(self):
        """오른쪽 패널: 간트차트 (타임라인) - 40% 너비"""
        
        # 기존 타임라인 구성요소 활용
        timeline_section = ft.Row(
            [
                self._build_device_list(),
                self._build_timeline(),
            ],
            spacing=0,
            expand=True,
        )
        
        return ft.Container(
            content=ft.Column(
                [
                    # 섹션 헤더
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.VIEW_TIMELINE, size=18, color="#5B6EE1"),
                                ft.Container(width=6),
                                ft.Text("타임라인", size=14, weight=ft.FontWeight.BOLD, color="#333333"),
                                ft.Container(expand=True),
                                # 저장/불러오기 버튼
                                ft.IconButton(ft.Icons.SAVE, icon_size=18, icon_color="#5B6EE1", tooltip="저장", on_click=lambda _: self._save_schedule()),
                                ft.IconButton(ft.Icons.FOLDER_OPEN, icon_size=18, icon_color="#28a745", tooltip="불러오기", on_click=lambda _: self._load_schedule()),
                            ],
                        ),
                        padding=ft.padding.only(left=15, right=5, top=10, bottom=5),
                        bgcolor="#ffffff",
                        border=ft.border.only(bottom=ft.BorderSide(1, "#f0f0f0")),
                    ),
                    
                    # 타임라인 영역 (가로/세로 스크롤 가능)
                    ft.Container(
                        content=ft.Column(
                            [timeline_section],
                            scroll="auto",  # 세로 스크롤
                            expand=True,
                        ),
                        expand=True,
                        bgcolor="#ffffff",
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=2,  # 40% (3:2 비율)
            bgcolor="#f8f9fc",
        )
    
    def _build_control_buttons(self):
        """제어 버튼들"""
        return ft.Row(
            [
                ft.ElevatedButton(
                    "▶ 실행",
                    bgcolor="#28a745",
                    color="#ffffff",
                    on_click=lambda _: self._start_scheduler(),
                ),
                ft.ElevatedButton(
                    "⏸ 정지",
                    bgcolor="#ffc107",
                    color="#333333",
                    on_click=lambda _: self._stop_scheduler(),
                ),
                ft.ElevatedButton(
                    "⏮ 리셋",
                    bgcolor="#17a2b8",
                    color="#ffffff",
                    on_click=lambda _: self._reset_scheduler(),
                ),
                ft.Container(width=10),
                ft.IconButton(
                    ft.Icons.SAVE,
                    icon_color="#007bff",
                    tooltip="스케줄 저장",
                    on_click=lambda _: self._save_schedule(),
                ),
                ft.IconButton(
                    ft.Icons.FOLDER_OPEN,
                    icon_color="#28a745",
                    tooltip="스케줄 불러오기",
                    on_click=lambda _: self._load_schedule(),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_FOREVER,
                    icon_color="#dc3545",
                    tooltip="전체 삭제",
                    on_click=lambda _: self._clear_schedule(),
                ),
            ],
            spacing=8,
        )
    
    def _build_device_list(self):
        """왼쪽 장비 리스트"""
        device_rows = []
        
        # 모터 장치
        for device in self.devices:
            row = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(device["icon"], color=device["color"], size=18),
                        ft.Text(device["name"], size=11, weight=ft.FontWeight.W_500),
                    ],
                    spacing=6,
                ),
                height=self.row_height,
                padding=ft.padding.symmetric(horizontal=8),
                bgcolor="#ffffff",
                border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
                alignment=ft.Alignment(-1, 0),
            )
            device_rows.append(row)
        
        # 가스 장치
        for gas_device in self.gas_devices:
            row = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(gas_device["icon"], color=gas_device["color"], size=18),
                        ft.Text(gas_device["name"], size=11, weight=ft.FontWeight.W_500),
                    ],
                    spacing=6,
                ),
                height=self.row_height,
                padding=ft.padding.symmetric(horizontal=8),
                bgcolor="#f0f8ff",  # 가스 장치는 파란색 배경
                border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
                alignment=ft.Alignment(-1, 0),
            )
            device_rows.append(row)
        
        time_header_space = ft.Container(
            content=ft.Text("장치", size=10, color="#666666", weight=ft.FontWeight.BOLD),
            height=30,
            bgcolor="#f8f9fa",
            padding=ft.padding.only(left=8),
            alignment=ft.Alignment(-1, 0),
        )
        
        return ft.Container(
            content=ft.Column(
                [time_header_space] + device_rows,
                spacing=0,
            ),
            width=110,
            bgcolor="#ffffff",
            border=ft.border.only(right=ft.BorderSide(1, "#e0e0e0")),
        )
    
    def _build_timeline(self):
        """타임라인 영역"""
        time_labels = []
        for minute in range(0, 65, 5):
            time_labels.append(
                ft.Container(
                    content=ft.Text(f"{minute:02d}:00", size=9, color="#666666"),
                    width=self.pixels_per_minute * 5,
                )
            )
        
        time_header = ft.Container(
            content=ft.Row(time_labels, spacing=0),
            height=30,
            bgcolor="#f8f9fa",
            border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
        )
        
        timeline_rows = []
        # 모터 장치 타임라인
        for device in self.devices:
            row = self._build_timeline_row(device)
            timeline_rows.append(row)
        
        # 가스 장치 타임라인
        for gas_device in self.gas_devices:
            row = self._build_timeline_row(gas_device)
            timeline_rows.append(row)
        
        self.timeline_container = ft.Column(timeline_rows, spacing=0)
        
        timeline_width = (self.timeline_max_seconds // 60) * self.pixels_per_minute + 100
        
        scrollable_content = ft.Container(
            content=ft.Column(
                [time_header, self.timeline_container],
                spacing=0,
            ),
            width=timeline_width,
        )
        
        return ft.Container(
            content=ft.Row(
                [scrollable_content],
                scroll="auto",
                expand=True,
            ),
            expand=True,
            bgcolor="#ffffff",
        )
    
    def _build_timeline_row(self, device: Dict):
        """장비별 타임라인 행"""
        blocks = [b for b in self.schedule_blocks if b.device_id == device["id"]]
        timeline_width = (self.timeline_max_seconds // 60) * self.pixels_per_minute + 100
        
        stack_children = []
        
        # 그리드 라인
        for minute in range(0, 65, 5):
            line_left = minute * self.pixels_per_minute
            stack_children.append(
                ft.Container(
                    width=1,
                    height=self.row_height,
                    bgcolor="#e8e8e8" if minute % 10 == 0 else "#f0f0f0",
                    left=line_left,
                    top=0,
                )
            )
        
        # 스케줄 블록들
        for block in blocks:
            left_pos = (block.start_seconds / 60) * self.pixels_per_minute
            width = (block.duration_seconds / 60) * self.pixels_per_minute
            
            action_display = {
                "move_plus": "▲+",
                "move_minus": "▼-",
                "rotate_cw": "↻",
                "rotate_ccw": "↺",
                "stop": "■",
            }.get(block.action_name, "?")
            
            block_container = ft.Container(
                content=ft.Text(action_display, size=10, color="#ffffff", weight=ft.FontWeight.BOLD),
                width=max(width, 20),
                height=self.row_height - 12,
                bgcolor=device["color"],
                border_radius=3,
                alignment=ft.Alignment(0, 0),
                left=left_pos,
                top=6,
                on_click=lambda _, b=block: self._show_edit_dialog(b),
            )
            stack_children.append(block_container)
        
        return ft.Container(
            content=ft.Stack(stack_children, width=timeline_width, height=self.row_height),
            height=self.row_height,
            width=timeline_width,
            bgcolor="#ffffff",
            border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
        )
    
    def _show_add_dialog(self, device: Dict):
        """스케줄 추가 다이얼로그"""
        start_min = ft.TextField(label="시작 (분)", value="0", width=70, keyboard_type=ft.KeyboardType.NUMBER)
        start_sec = ft.TextField(label="초", value="0", width=60, keyboard_type=ft.KeyboardType.NUMBER)
        duration_min = ft.TextField(label="지속 (분)", value="1", width=70, keyboard_type=ft.KeyboardType.NUMBER)
        duration_sec = ft.TextField(label="초", value="0", width=60, keyboard_type=ft.KeyboardType.NUMBER)
        
        if "rotate" in device["id"]:
            action_options = [
                ft.dropdown.Option("rotate_cw", "↻ 시계방향"),
                ft.dropdown.Option("rotate_ccw", "↺ 반시계방향"),
                ft.dropdown.Option("stop", "■ 정지"),
            ]
        else:
            action_options = [
                ft.dropdown.Option("move_plus", "▲ +방향"),
                ft.dropdown.Option("move_minus", "▼ -방향"),
                ft.dropdown.Option("stop", "■ 정지"),
            ]
        
        action_select = ft.Dropdown(label="동작", options=action_options, value=action_options[0].key, width=180)
        speed_input = ft.TextField(label="속도 (1~8000)", value="1000", width=140, keyboard_type=ft.KeyboardType.NUMBER)
        
        def on_add(e):
            start_seconds = int(start_min.value or 0) * 60 + int(start_sec.value or 0)
            duration_seconds = int(duration_min.value or 1) * 60 + int(duration_sec.value or 0)
            if duration_seconds <= 0:
                duration_seconds = 60
            
            new_block = ScheduleBlock(
                device_id=device["id"],
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                action_name=action_select.value,
                action_params={"speed": int(speed_input.value or 1000)},
            )
            self.schedule_blocks.append(new_block)
            dialog.open = False
            self.page.update()
            self._refresh_timeline()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"스케줄 추가 - {device['name']}", size=16),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([start_min, start_sec], spacing=8),
                    ft.Row([duration_min, duration_sec], spacing=8),
                    action_select,
                    speed_input,
                ], spacing=12, tight=True),
                width=250,
                height=220,
            ),
            actions=[
                ft.TextButton("취소", on_click=lambda _: self._close_dialog(dialog)),
                ft.ElevatedButton("추가", bgcolor="#28a745", color="#ffffff", on_click=on_add),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _show_edit_dialog(self, block: ScheduleBlock):
        """스케줄 편집/삭제 다이얼로그"""
        device = next((d for d in self.devices if d["id"] == block.device_id), None)
        device_name = device["name"] if device else block.device_id
        
        def on_delete(e):
            self.schedule_blocks.remove(block)
            dialog.open = False
            self.page.update()
            self._refresh_timeline()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"스케줄 - {device_name}", size=16),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"동작: {block.action_name}"),
                    ft.Text(f"시작: {block.format_time(block.start_seconds)}"),
                    ft.Text(f"종료: {block.format_time(block.end_seconds)}"),
                    ft.Text(f"속도: {block.action_params.get('speed', '-')}"),
                ], spacing=8),
                width=220,
            ),
            actions=[
                ft.TextButton("닫기", on_click=lambda _: self._close_dialog(dialog)),
                ft.ElevatedButton("삭제", bgcolor="#dc3545", color="#ffffff", on_click=on_delete),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _close_dialog(self, dialog):
        dialog.open = False
        self.page.update()
    
    def _refresh_timeline(self):
        if self.timeline_container:
            new_rows = [self._build_timeline_row(device) for device in self.devices]
            self.timeline_container.controls = new_rows
            self.page.update()
    
    # ==================== 스케줄 저장/불러오기 ====================
    
    def _save_schedule(self):
        """스케줄 저장 다이얼로그"""
        filename_input = ft.TextField(
            label="파일명",
            value=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            width=250,
        )
        
        def on_save(e):
            filename = filename_input.value
            if not filename.endswith(".json"):
                filename += ".json"
            
            # 저장 폴더
            save_dir = os.path.join(os.path.dirname(__file__), "..", "schedules")
            os.makedirs(save_dir, exist_ok=True)
            
            filepath = os.path.join(save_dir, filename)
            
            # JSON 저장
            data = {
                "created": datetime.now().isoformat(),
                "blocks": [block.to_dict() for block in self.schedule_blocks]
            }
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            dialog.open = False
            self.page.update()
            
            # 성공 알림
            self.page.snack_bar = ft.SnackBar(ft.Text(f"✅ 저장됨: {filename}"))
            self.page.snack_bar.open = True
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("스케줄 저장"),
            content=ft.Container(content=filename_input, width=280),
            actions=[
                ft.TextButton("취소", on_click=lambda _: self._close_dialog(dialog)),
                ft.ElevatedButton("저장", bgcolor="#007bff", color="#ffffff", on_click=on_save),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _load_schedule(self):
        """스케줄 불러오기 다이얼로그"""
        save_dir = os.path.join(os.path.dirname(__file__), "..", "schedules")
        os.makedirs(save_dir, exist_ok=True)
        
        # 파일 목록
        files = [f for f in os.listdir(save_dir) if f.endswith(".json")]
        
        if not files:
            self.page.snack_bar = ft.SnackBar(ft.Text("저장된 스케줄이 없습니다."))
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        file_select = ft.Dropdown(
            label="파일 선택",
            options=[ft.dropdown.Option(f) for f in files],
            value=files[0] if files else None,
            width=280,
        )
        
        def on_load(e):
            if not file_select.value:
                return
            
            filepath = os.path.join(save_dir, file_select.value)
            
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.schedule_blocks.clear()
            for block_data in data.get("blocks", []):
                self.schedule_blocks.append(ScheduleBlock.from_dict(block_data))
            
            dialog.open = False
            self._refresh_timeline()
            
            self.page.snack_bar = ft.SnackBar(ft.Text(f"✅ 불러옴: {file_select.value}"))
            self.page.snack_bar.open = True
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("스케줄 불러오기"),
            content=ft.Container(content=file_select, width=300),
            actions=[
                ft.TextButton("취소", on_click=lambda _: self._close_dialog(dialog)),
                ft.ElevatedButton("불러오기", bgcolor="#28a745", color="#ffffff", on_click=on_load),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    # ==================== 스케줄 실행 ====================
    
    def _start_scheduler(self):
        if self.is_running:
            return
        
        self.is_running = True
        
        if self.status_text:
            self.status_text.value = "▶ 실행 중..."
            self.status_text.color = "#28a745"
        
        # 그래프 데이터 초기화
        for device in self.devices:
            self.graph_data[device["id"]] = []
            self.motor_speeds[device["id"]] = 0
        
        # 플로팅 모니터 표시
        self._toggle_floating_panel(True)
        
        self.page.update()
        
        # 스케줄러 스레드 시작
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        # UI 업데이트 스레드 시작 (플로팅 모니터용)
        self.ui_update_thread = threading.Thread(target=self._ui_update_loop, daemon=True)
        self.ui_update_thread.start()
    
    def _stop_scheduler(self):
        self.is_running = False
        
        # 모든 모터 정지
        self._stop_all_motors()
        
        if self.status_text:
            self.status_text.value = "⏸ 일시정지"
            self.status_text.color = "#ffc107"
            self.page.update()
    
    def _reset_scheduler(self):
        self.is_running = False
        self.elapsed_seconds = 0
        
        for block in self.schedule_blocks:
            block.executed = False
        
        # 모터 속도 초기화
        for device in self.devices:
            self.motor_speeds[device["id"]] = 0
            self.graph_data[device["id"]] = []
        
        # 라인 차트 데이터 초기화
        if hasattr(self, 'line_chart_data'):
            for device_id in self.line_chart_data:
                self.line_chart_data[device_id] = []
        
        # 라인 차트 초기화
        if hasattr(self, 'line_data_series'):
            for data_series in self.line_data_series:
                data_series.points = [fch.LineChartDataPoint(0, 0)]
        
        # X축 초기화
        if hasattr(self, 'line_chart'):
            self.line_chart.min_x = 0
            self.line_chart.max_x = self.max_points if hasattr(self, 'max_points') else 30
        
        # 가로 막대 초기화
        if hasattr(self, 'bar_containers'):
            for device_id, bar in self.bar_containers.items():
                bar.width = 0
        
        # 프로그레스 바 초기화
        if hasattr(self, 'progress_bars'):
            for device_id, progress in self.progress_bars.items():
                progress.value = 0
        
        # 속도 라벨 초기화
        if hasattr(self, 'speed_labels'):
            for device_id, label in self.speed_labels.items():
                label.value = "0"
        
        # 플로팅 패널 숨김
        self._toggle_floating_panel(False)
        
        if self.status_text:
            self.status_text.value = "⏸ 대기 중"
            self.status_text.color = "#666666"
        if self.elapsed_text:
            self.elapsed_text.value = "경과: 00:00:00"
        
        self.page.update()
    
    def _clear_schedule(self):
        self.schedule_blocks.clear()
        self._reset_scheduler()
        self._refresh_timeline()
    
    def _scheduler_loop(self):
        """스케줄 실행 루프 (데이터만 업데이트)"""
        while self.is_running:
            # 블록 실행 체크
            for block in self.schedule_blocks:
                if block.executed:
                    continue
                
                if block.start_seconds <= self.elapsed_seconds < block.end_seconds:
                    self._execute_action(block)
                    block.executed = True
            
            # 현재 모터 속도 계산
            for device in self.devices:
                device_id = device["id"]
                active_block = next(
                    (b for b in self.schedule_blocks 
                     if b.device_id == device_id 
                     and b.start_seconds <= self.elapsed_seconds < b.end_seconds
                     and b.action_name != "stop"),
                    None
                )
                self.motor_speeds[device_id] = active_block.action_params.get("speed", 0) if active_block else 0
            
            # 경과 시간 증가
            self.elapsed_seconds += 1
            
            time.sleep(1)
    
    def _ui_update_loop(self):
        """UI 업데이트 루프 (pubsub로 메시지 전송)"""
        while self.is_running:
            try:
                # pubsub로 UI 업데이트 메시지 전송 (메인 스레드에서 처리됨)
                self.page.pubsub.send_all({
                    "type": "update_monitor",
                    "elapsed_seconds": self.elapsed_seconds,
                    "motor_speeds": dict(self.motor_speeds),
                })
            except Exception as e:
                print(f"pubsub 전송 오류: {e}")
            
            time.sleep(0.5)  # 0.5초마다 UI 업데이트
    
    def _on_pubsub_message(self, message):
        """pubsub 메시지 처리 (메인 스레드에서 실행됨)"""
        try:
            if message.get("type") == "update_monitor":
                elapsed = message.get("elapsed_seconds", 0)
                speeds = message.get("motor_speeds", {})
                
                h, rem = divmod(elapsed, 3600)
                m, s = divmod(rem, 60)
                
                # 경과 시간 텍스트 업데이트
                if self.elapsed_text:
                    self.elapsed_text.value = f"경과: {h:02d}:{m:02d}:{s:02d}"
                
                # 플로팅 모니터 업데이트
                if hasattr(self, 'floating_elapsed_text') and self.floating_elapsed_text:
                    self.floating_elapsed_text.value = f"{h:02d}:{m:02d}:{s:02d}"
                
                # 프로그레스 바, 속도 라벨 업데이트
                for device in self.devices:
                    device_id = device["id"]
                    speed = speeds.get(device_id, 0)
                    
                    # 프로그레스 바 업데이트
                    if device_id in self.progress_bars:
                        self.progress_bars[device_id].value = min(speed / 8000, 1.0)
                    
                    # 속도 라벨 업데이트
                    if device_id in self.speed_labels:
                        self.speed_labels[device_id].value = str(int(speed))
                
                # 라인 차트 업데이트
                if hasattr(self, 'line_chart_data'):
                    self._update_line_chart(speeds)
                
                # 가로 막대 업데이트
                for device in self.devices:
                    device_id = device["id"]
                    speed = speeds.get(device_id, 0)
                    if hasattr(self, 'bar_containers') and device_id in self.bar_containers:
                        bar_width = min((speed / 8000) * 100, 100)
                        self.bar_containers[device_id].width = bar_width
                
                # 페이지 업데이트
                self.page.update()
                
        except Exception as e:
            print(f"UI 업데이트 오류: {e}")
    
    def _execute_action(self, block: ScheduleBlock):
        """액션 실행 - 실제 모터/가스 명령 전송"""
        h, rem = divmod(self.elapsed_seconds, 3600)
        m, s = divmod(rem, 60)
        
        device_id = block.device_id
        action = block.action_name
        
        # 가스 장치인지 확인
        gas_device = next((d for d in self.gas_devices if d["id"] == device_id), None)
        if gas_device:
            # 가스 밸브 제어
            is_open = (action == "valve_open")
            success = self.toggle_gas_valve(device_id, is_open)
            
            action_text = "열기" if is_open else "닫기"
            status_icon = "✅" if success else "❌"
            print(f"[{h:02d}:{m:02d}:{s:02d}] {status_icon} {gas_device['name']}: 밸브 {action_text}")
            
            if self.status_text:
                self.status_text.value = f"▶ {gas_device['name']}: 밸브 {action_text}"
                try:
                    self.page.update()
                except:
                    pass
            return
        
        # 모터 장치
        device = next((d for d in self.devices if d["id"] == device_id), None)
        device_name = device["name"] if device else device_id
        
        speed = block.action_params.get('speed', 1000)
        
        # 실제 모터 명령 전송
        success = self._send_motor_command(device_id, action, speed)
        
        status_icon = "✅" if success else "❌"
        print(f"[{h:02d}:{m:02d}:{s:02d}] {status_icon} {device_name}: {action} (속도: {speed})")
        
        if self.status_text:
            self.status_text.value = f"▶ {device_name}: {action}"
            try:
                self.page.update()
            except:
                pass
