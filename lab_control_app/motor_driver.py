"""
오토닉스 PMC-2HSP 모터 드라이버 통신 모듈
- 드라이버 2개, 모터 4개 (각 드라이버당 X/Y 2축)
- Modbus RTU 통신
- 스텝각: 0.72°, 풀스텝, 1회전(360°) = 5mm
"""
from pymodbus.client import ModbusSerialClient
from typing import Optional, Dict, Callable
from dataclasses import dataclass
from enum import Enum
import threading
import time


# ==================== 상수 정의 ====================

# 모터 사양
STEP_ANGLE = 0.72           # 스텝각 (도)
PULSE_PER_REV = 500         # 1회전당 펄스 (360/0.72)
MM_PER_REV = 5              # 1회전당 이동거리 (mm)
PULSE_PER_MM = 100          # 펄스/mm (500/5)

# 레지스터 주소 (Modbus 0-based, 40001 기준 오프셋)
# 명령 레지스터 (40001 = 0x0000)
CMD_REGISTER = 0x0000

# X축 레지스터
X_REGISTERS = {
    'speed_ratio': 0x0454 - 0x0001,     # 41109 → 1108 (속도 배율)
    'accel': 0x0455 - 0x0001,           # 41110 → 1109 (가속도)
    'decel': 0x0456 - 0x0001,           # 41111 → 1110 (감속도)
    'start_speed': 0x0457 - 0x0001,     # 41112 → 1111 (기동속도)
    'drive_speed1': 0x0458 - 0x0001,    # 41113 → 1112 (드라이브 속도 1)
    'drive_speed2': 0x0459 - 0x0001,    # 41114 → 1113
    'drive_speed3': 0x045A - 0x0001,    # 41115 → 1114
    'drive_speed4': 0x045B - 0x0001,    # 41116 → 1115
    'end_pulse_width': 0x045D - 0x0001, # 41118 → 1117
    'scale_num': 0x045E - 0x0001,       # 41119 → 1118 (펄스 스케일 분자)
    'scale_den': 0x045F - 0x0001,       # 41120 → 1119 (펄스 스케일 분모)
    'jerk': 0x0472 - 0x0001,            # 41139 → 1138 (가가속도)
}

# Y축 레지스터
Y_REGISTERS = {
    'speed_ratio': 0x0460 - 0x0001,     # 41121 → 1120
    'accel': 0x0461 - 0x0001,           # 41122 → 1121
    'decel': 0x0462 - 0x0001,           # 41123 → 1122
    'start_speed': 0x0463 - 0x0001,     # 41124 → 1123
    'drive_speed1': 0x0464 - 0x0001,    # 41125 → 1124
    'drive_speed2': 0x0465 - 0x0001,    # 41126 → 1125
    'drive_speed3': 0x0466 - 0x0001,    # 41127 → 1126
    'drive_speed4': 0x0467 - 0x0001,    # 41128 → 1127
    'post_timer1': 0x0468 - 0x0001,     # 41129 → 1128
    'post_timer2': 0x0469 - 0x0001,     # 41130 → 1129
    'post_timer3': 0x046A - 0x0001,     # 41131 → 1130
    'end_pulse_width': 0x046F - 0x0001, # 41136 → 1135
    'scale_num': 0x0470 - 0x0001,       # 41137 → 1136
    'scale_den': 0x0471 - 0x0001,       # 41138 → 1137
    'jerk': 0x0473 - 0x0001,            # 41140 → 1139
}

# 명령 코드 (상위 바이트, 하위 바이트)
class MotorCommand:
    """모터 제어 명령 코드"""
    # 연속 드라이브
    X_PLUS_CONTINUOUS = (0x01, 0x20)    # X축 +방향 연속 드라이브
    X_MINUS_CONTINUOUS = (0x01, 0x10)   # X축 -방향 연속 드라이브
    Y_PLUS_CONTINUOUS = (0x01, 0x02)    # Y축 +방향 연속 드라이브
    Y_MINUS_CONTINUOUS = (0x01, 0x01)   # Y축 -방향 연속 드라이브
    
    # 정지
    X_DECEL_STOP = (0x05, 0x01)         # X축 감속 정지
    Y_DECEL_STOP = (0x05, 0x02)         # Y축 감속 정지
    X_IMMEDIATE_STOP = (0x05, 0x10)     # X축 즉시 정지
    Y_IMMEDIATE_STOP = (0x05, 0x20)     # Y축 즉시 정지
    
    # 속도 선택
    X_SPEED_1 = (0x04, 0x10)            # X축 속도 1 선택
    X_SPEED_2 = (0x04, 0x20)            # X축 속도 2 선택
    X_SPEED_3 = (0x04, 0x30)            # X축 속도 3 선택
    X_SPEED_4 = (0x04, 0x40)            # X축 속도 4 선택
    Y_SPEED_1 = (0x04, 0x01)            # Y축 속도 1 선택
    Y_SPEED_2 = (0x04, 0x02)            # Y축 속도 2 선택
    Y_SPEED_3 = (0x04, 0x03)            # Y축 속도 3 선택
    Y_SPEED_4 = (0x04, 0x04)            # Y축 속도 4 선택


class MotorAxis(Enum):
    """모터 축"""
    X = "X"
    Y = "Y"


class MotorDirection(Enum):
    """이동 방향"""
    PLUS = "plus"
    MINUS = "minus"
    CW = "cw"       # 시계방향 (회전용)
    CCW = "ccw"     # 반시계방향 (회전용)


@dataclass
class MotorStatus:
    """모터 상태"""
    connected: bool = False
    running: bool = False
    speed: int = 0
    position_pulse: int = 0
    direction: Optional[MotorDirection] = None
    error: Optional[str] = None


class PMC2HSPDriver:
    """
    PMC-2HSP 모터 드라이버 클래스
    - 하나의 드라이버가 X축, Y축 2개 모터 제어
    """
    
    def __init__(self, slave_id: int = 1, port: str = 'COM7', baudrate: int = 9600):
        self.slave_id = slave_id
        self.port = port
        self.baudrate = baudrate
        self.client: Optional[ModbusSerialClient] = None
        self.connected = False
        
        # 모터 상태
        self.x_status = MotorStatus()
        self.y_status = MotorStatus()
        
        # 콜백
        self.on_status_change: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
    
    def log(self, message: str):
        """로그 출력"""
        if self.on_log:
            self.on_log(f"[Driver {self.slave_id}] {message}")
        print(f"[Driver {self.slave_id}] {message}")
    
    def connect(self, client: Optional[ModbusSerialClient] = None) -> bool:
        """
        Modbus 연결
        - client가 주어지면 공유, 없으면 새로 생성
        """
        try:
            if client:
                # 공유 클라이언트 사용
                self.client = client
                self.connected = client.is_socket_open()
            else:
                # 새 클라이언트 생성
                self.client = ModbusSerialClient(
                    port=self.port,
                    baudrate=self.baudrate,
                    parity='N',
                    stopbits=1,
                    bytesize=8,
                    timeout=1
                )
                self.connected = self.client.connect()
            
            if self.connected:
                self.log(f"연결 성공 ({self.port})")
                self.x_status.connected = True
                self.y_status.connected = True
            else:
                self.log(f"연결 실패 ({self.port})")
                
            return self.connected
            
        except Exception as e:
            self.log(f"연결 오류: {e}")
            return False
    
    def disconnect(self):
        """연결 해제"""
        if self.client:
            self.client.close()
            self.client = None
        self.connected = False
        self.x_status.connected = False
        self.y_status.connected = False
        self.log("연결 해제됨")
    
    def _send_command(self, hi: int, lo: int) -> bool:
        """
        명령 전송 (40001 레지스터)
        """
        if not self.connected or not self.client:
            self.log("연결되지 않음")
            return False
        
        try:
            value = (hi << 8) | lo
            result = self.client.write_register(CMD_REGISTER, value, slave=self.slave_id)
            
            if result.isError():
                self.log(f"명령 전송 실패: 0x{value:04X}")
                return False
            
            self.log(f"명령 전송: 0x{value:04X}")
            return True
            
        except Exception as e:
            self.log(f"통신 오류: {e}")
            return False
    
    def _write_register(self, address: int, value: int) -> bool:
        """
        특정 레지스터에 값 쓰기
        """
        if not self.connected or not self.client:
            return False
        
        try:
            result = self.client.write_register(address, value, slave=self.slave_id)
            
            if result.isError():
                self.log(f"레지스터 쓰기 실패: 0x{address:04X} = {value}")
                return False
            
            self.log(f"레지스터 설정: 0x{address:04X} = {value}")
            return True
            
        except Exception as e:
            self.log(f"레지스터 쓰기 오류: {e}")
            return False
    
    def _read_register(self, address: int) -> Optional[int]:
        """
        레지스터 읽기
        """
        if not self.connected or not self.client:
            return None
        
        try:
            result = self.client.read_holding_registers(address, 1, slave=self.slave_id)
            
            if result.isError():
                return None
            
            return result.registers[0]
            
        except Exception as e:
            self.log(f"레지스터 읽기 오류: {e}")
            return None
    
    # ==================== 속도 설정 ====================
    
    def set_speed(self, axis: MotorAxis, speed: int, speed_num: int = 1) -> bool:
        """
        드라이브 속도 설정 (1~8000)
        
        Args:
            axis: X 또는 Y축
            speed: 속도 값 (1~8000)
            speed_num: 속도 번호 (1~4)
        """
        if speed < 1 or speed > 8000:
            self.log(f"속도 범위 오류: {speed} (1~8000)")
            return False
        
        registers = X_REGISTERS if axis == MotorAxis.X else Y_REGISTERS
        speed_key = f'drive_speed{speed_num}'
        
        if speed_key not in registers:
            self.log(f"잘못된 속도 번호: {speed_num}")
            return False
        
        return self._write_register(registers[speed_key], speed)
    
    def set_accel(self, axis: MotorAxis, accel: int) -> bool:
        """가속도 설정 (1~8000)"""
        if accel < 1 or accel > 8000:
            return False
        
        registers = X_REGISTERS if axis == MotorAxis.X else Y_REGISTERS
        return self._write_register(registers['accel'], accel)
    
    def set_decel(self, axis: MotorAxis, decel: int) -> bool:
        """감속도 설정 (1~8000)"""
        if decel < 1 or decel > 8000:
            return False
        
        registers = X_REGISTERS if axis == MotorAxis.X else Y_REGISTERS
        return self._write_register(registers['decel'], decel)
    
    def set_pulse_scale(self, axis: MotorAxis, numerator: int = 1, denominator: int = 100) -> bool:
        """
        펄스 스케일 설정 (거리 환산용)
        
        기본값: 분자=1, 분모=100 → 1펄스 = 0.01mm
        (0.72° 스텝각, 풀스텝, 1회전=5mm 기준)
        """
        registers = X_REGISTERS if axis == MotorAxis.X else Y_REGISTERS
        
        success = self._write_register(registers['scale_num'], numerator)
        success = success and self._write_register(registers['scale_den'], denominator)
        
        return success
    
    # ==================== 모터 제어 ====================
    
    def select_speed(self, axis: MotorAxis, speed_num: int = 1) -> bool:
        """속도 번호 선택 (1~4)"""
        if axis == MotorAxis.X:
            commands = [MotorCommand.X_SPEED_1, MotorCommand.X_SPEED_2, 
                       MotorCommand.X_SPEED_3, MotorCommand.X_SPEED_4]
        else:
            commands = [MotorCommand.Y_SPEED_1, MotorCommand.Y_SPEED_2,
                       MotorCommand.Y_SPEED_3, MotorCommand.Y_SPEED_4]
        
        if speed_num < 1 or speed_num > 4:
            return False
        
        return self._send_command(*commands[speed_num - 1])
    
    def start_continuous(self, axis: MotorAxis, direction: MotorDirection) -> bool:
        """
        연속 드라이브 시작
        
        Args:
            axis: X 또는 Y축
            direction: plus/minus 또는 cw/ccw
        """
        if axis == MotorAxis.X:
            if direction in [MotorDirection.PLUS, MotorDirection.CW]:
                cmd = MotorCommand.X_PLUS_CONTINUOUS
            else:
                cmd = MotorCommand.X_MINUS_CONTINUOUS
            self.x_status.running = True
            self.x_status.direction = direction
        else:
            if direction in [MotorDirection.PLUS, MotorDirection.CW]:
                cmd = MotorCommand.Y_PLUS_CONTINUOUS
            else:
                cmd = MotorCommand.Y_MINUS_CONTINUOUS
            self.y_status.running = True
            self.y_status.direction = direction
        
        return self._send_command(*cmd)
    
    def stop(self, axis: MotorAxis, immediate: bool = False) -> bool:
        """
        모터 정지
        
        Args:
            axis: X 또는 Y축
            immediate: True면 즉시 정지, False면 감속 정지
        """
        if axis == MotorAxis.X:
            cmd = MotorCommand.X_IMMEDIATE_STOP if immediate else MotorCommand.X_DECEL_STOP
            self.x_status.running = False
            self.x_status.direction = None
            self.x_status.speed = 0
        else:
            cmd = MotorCommand.Y_IMMEDIATE_STOP if immediate else MotorCommand.Y_DECEL_STOP
            self.y_status.running = False
            self.y_status.direction = None
            self.y_status.speed = 0
        
        return self._send_command(*cmd)
    
    def stop_all(self, immediate: bool = False) -> bool:
        """X축, Y축 모두 정지"""
        x_ok = self.stop(MotorAxis.X, immediate)
        y_ok = self.stop(MotorAxis.Y, immediate)
        return x_ok and y_ok
    
    def move_with_speed(self, axis: MotorAxis, direction: MotorDirection, speed: int) -> bool:
        """
        지정된 속도로 이동 시작
        
        Args:
            axis: X 또는 Y축
            direction: 이동 방향
            speed: 속도 (1~8000)
        """
        # 속도 1에 설정
        if not self.set_speed(axis, speed, 1):
            return False
        
        time.sleep(0.05)
        
        # 속도 1 선택
        if not self.select_speed(axis, 1):
            return False
        
        time.sleep(0.05)
        
        # 연속 드라이브 시작
        result = self.start_continuous(axis, direction)
        
        if result:
            status = self.x_status if axis == MotorAxis.X else self.y_status
            status.speed = speed
        
        return result


# ==================== 변환 유틸리티 ====================

def mm_to_pulse(mm: float) -> int:
    """mm를 펄스로 변환"""
    return int(mm * PULSE_PER_MM)

def pulse_to_mm(pulse: int) -> float:
    """펄스를 mm로 변환"""
    return pulse / PULSE_PER_MM

def degree_to_pulse(degree: float) -> int:
    """각도를 펄스로 변환"""
    return int(degree / STEP_ANGLE)

def pulse_to_degree(pulse: int) -> float:
    """펄스를 각도로 변환"""
    return pulse * STEP_ANGLE

def rpm_to_pps(rpm: float) -> int:
    """RPM을 펄스/초로 변환"""
    return int((rpm * PULSE_PER_REV) / 60)

def pps_to_rpm(pps: int) -> float:
    """펄스/초를 RPM으로 변환"""
    return (pps * 60) / PULSE_PER_REV


# ==================== 통합 컨트롤러 ====================

class MotorController:
    """
    4개 모터 통합 컨트롤러
    - 드라이버 1: 상부 스테이지(X), 상부 회전(Y)
    - 드라이버 2: 하부 스테이지(X), 하부 회전(Y)
    """
    
    # 모터 ID 매핑
    MOTOR_MAP = {
        'upper_stage': {'driver': 1, 'axis': MotorAxis.X, 'name': '상부 스테이지'},
        'upper_rotate': {'driver': 1, 'axis': MotorAxis.Y, 'name': '상부 회전'},
        'lower_stage': {'driver': 2, 'axis': MotorAxis.X, 'name': '하부 스테이지'},
        'lower_rotate': {'driver': 2, 'axis': MotorAxis.Y, 'name': '하부 회전'},
    }
    
    def __init__(self, port: str = 'COM7', baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        
        # 공유 클라이언트
        self.client: Optional[ModbusSerialClient] = None
        self.connected = False
        
        # 드라이버 인스턴스 (Slave ID 1, 2)
        self.driver1 = PMC2HSPDriver(slave_id=1, port=port, baudrate=baudrate)
        self.driver2 = PMC2HSPDriver(slave_id=2, port=port, baudrate=baudrate)
        
        # 모터 속도 상태
        self.motor_speeds: Dict[str, int] = {
            'upper_stage': 0,
            'upper_rotate': 0,
            'lower_stage': 0,
            'lower_rotate': 0,
        }
        
        # 콜백
        self.on_log: Optional[Callable] = None
    
    def log(self, message: str):
        """로그 출력"""
        if self.on_log:
            self.on_log(message)
        print(f"[MotorController] {message}")
    
    def connect(self) -> bool:
        """모든 드라이버 연결"""
        try:
            # 공유 클라이언트 생성
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=1
            )
            
            if not self.client.connect():
                self.log(f"Modbus 연결 실패: {self.port}")
                return False
            
            self.connected = True
            self.log(f"Modbus 연결 성공: {self.port}")
            
            # 드라이버에 공유 클라이언트 전달
            self.driver1.connect(self.client)
            self.driver2.connect(self.client)
            
            # 초기 설정 (펄스 스케일)
            self._initialize_drivers()
            
            return True
            
        except Exception as e:
            self.log(f"연결 오류: {e}")
            return False
    
    def disconnect(self):
        """연결 해제"""
        self.driver1.disconnect()
        self.driver2.disconnect()
        
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        self.log("연결 해제됨")
    
    def _initialize_drivers(self):
        """드라이버 초기 설정"""
        # 펄스 스케일 설정 (1펄스 = 0.01mm)
        for driver in [self.driver1, self.driver2]:
            driver.set_pulse_scale(MotorAxis.X, 1, 100)
            driver.set_pulse_scale(MotorAxis.Y, 1, 100)
        
        self.log("드라이버 초기화 완료")
    
    def _get_driver_axis(self, motor_id: str) -> tuple:
        """모터 ID로 드라이버와 축 가져오기"""
        if motor_id not in self.MOTOR_MAP:
            raise ValueError(f"알 수 없는 모터 ID: {motor_id}")
        
        config = self.MOTOR_MAP[motor_id]
        driver = self.driver1 if config['driver'] == 1 else self.driver2
        axis = config['axis']
        
        return driver, axis
    
    def set_speed(self, motor_id: str, speed: int) -> bool:
        """
        모터 속도 설정
        
        Args:
            motor_id: 모터 ID (upper_stage, upper_rotate, lower_stage, lower_rotate)
            speed: 속도 (1~8000)
        """
        if not self.connected:
            self.log("연결되지 않음")
            return False
        
        driver, axis = self._get_driver_axis(motor_id)
        return driver.set_speed(axis, speed, 1)
    
    def start_motor(self, motor_id: str, direction: str, speed: int = 1000) -> bool:
        """
        모터 시작
        
        Args:
            motor_id: 모터 ID
            direction: 'plus', 'minus', 'cw', 'ccw'
            speed: 속도 (1~8000)
        """
        if not self.connected:
            self.log("연결되지 않음")
            return False
        
        # 방향 변환
        dir_map = {
            'plus': MotorDirection.PLUS,
            'minus': MotorDirection.MINUS,
            'up': MotorDirection.PLUS,
            'down': MotorDirection.MINUS,
            'cw': MotorDirection.CW,
            'ccw': MotorDirection.CCW,
            'left': MotorDirection.CCW,
            'right': MotorDirection.CW,
        }
        
        direction_enum = dir_map.get(direction.lower())
        if not direction_enum:
            self.log(f"잘못된 방향: {direction}")
            return False
        
        driver, axis = self._get_driver_axis(motor_id)
        result = driver.move_with_speed(axis, direction_enum, speed)
        
        if result:
            self.motor_speeds[motor_id] = speed
            self.log(f"{self.MOTOR_MAP[motor_id]['name']} 시작: {direction}, 속도={speed}")
        
        return result
    
    def stop_motor(self, motor_id: str, immediate: bool = False) -> bool:
        """모터 정지"""
        if not self.connected:
            return False
        
        driver, axis = self._get_driver_axis(motor_id)
        result = driver.stop(axis, immediate)
        
        if result:
            self.motor_speeds[motor_id] = 0
            self.log(f"{self.MOTOR_MAP[motor_id]['name']} 정지")
        
        return result
    
    def stop_all(self, immediate: bool = False) -> bool:
        """모든 모터 정지"""
        self.driver1.stop_all(immediate)
        self.driver2.stop_all(immediate)
        
        for motor_id in self.motor_speeds:
            self.motor_speeds[motor_id] = 0
        
        self.log("모든 모터 정지")
        return True
    
    def move_distance(self, motor_id: str, distance_mm: float, speed: int = 1000) -> bool:
        """
        지정 거리만큼 이동 (예약 - 실제 구현은 펄스 드라이브 명령 필요)
        
        Args:
            motor_id: 모터 ID
            distance_mm: 이동 거리 (mm), 음수면 역방향
            speed: 속도 (1~8000)
        """
        pulses = mm_to_pulse(abs(distance_mm))
        direction = 'plus' if distance_mm >= 0 else 'minus'
        
        self.log(f"{self.MOTOR_MAP[motor_id]['name']}: {distance_mm}mm = {pulses} 펄스, 방향={direction}")
        
        # TODO: 펄스 드라이브 명령 구현 (매뉴얼 참조)
        # 현재는 연속 드라이브로 시뮬레이션
        return self.start_motor(motor_id, direction, speed)
    
    def rotate_angle(self, motor_id: str, angle_deg: float, speed: int = 1000) -> bool:
        """
        지정 각도만큼 회전
        
        Args:
            motor_id: 모터 ID (회전 모터 권장)
            angle_deg: 회전 각도 (도), 음수면 역방향
            speed: 속도 (1~8000)
        """
        pulses = degree_to_pulse(abs(angle_deg))
        direction = 'cw' if angle_deg >= 0 else 'ccw'
        
        self.log(f"{self.MOTOR_MAP[motor_id]['name']}: {angle_deg}° = {pulses} 펄스, 방향={direction}")
        
        # TODO: 펄스 드라이브 명령 구현
        return self.start_motor(motor_id, direction, speed)
    
    def get_motor_speed(self, motor_id: str) -> int:
        """현재 모터 속도 반환"""
        return self.motor_speeds.get(motor_id, 0)
    
    def get_all_speeds(self) -> Dict[str, int]:
        """모든 모터 속도 반환"""
        return dict(self.motor_speeds)


# ==================== 테스트 ====================

if __name__ == "__main__":
    print("=== PMC-2HSP 모터 드라이버 테스트 ===")
    print(f"스텝각: {STEP_ANGLE}°")
    print(f"1회전: {PULSE_PER_REV} 펄스 = {MM_PER_REV}mm")
    print(f"1mm: {PULSE_PER_MM} 펄스")
    print(f"분해능: {1/PULSE_PER_MM}mm = {1/PULSE_PER_MM * 1000}μm")
    print()
    
    # 변환 테스트
    print("=== 변환 테스트 ===")
    print(f"10mm → {mm_to_pulse(10)} 펄스")
    print(f"360° → {degree_to_pulse(360)} 펄스")
    print(f"100 펄스 → {pulse_to_mm(100)}mm")
    print(f"500 펄스 → {pulse_to_degree(500)}°")
    print()
    
    # 컨트롤러 테스트 (실제 연결 없이)
    controller = MotorController(port='COM7')
    print("MotorController 생성 완료")
    print(f"모터 맵: {controller.MOTOR_MAP}")


