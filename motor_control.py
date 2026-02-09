from pymodbus.client import ModbusSerialClient
import time
import msvcrt  # Windows 키 입력용

client = ModbusSerialClient(
    port='COM7',          # Windows면 COMx, Linux면 /dev/ttyUSB0
    baudrate=9600,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)

if not client.connect():
    print("Modbus 연결 실패")
    exit()

SLAVE_ID = 1
ADDR = 0   # 40001 → offset 0

def send_cmd(hi, lo):
    value = (hi << 8) | lo
    rr = client.write_register(ADDR, value, slave=SLAVE_ID)
    if rr.isError():
        print("쓰기 에러:", rr)
    else:
        print(f"Sent 0x{value:04X}")

print("=== 모터 제어 ===")
print("s: X축 +방향 연속 드라이브 (속도 1)")
print("r: X축 -방향 연속 드라이브 (속도 1)")
print("q: X축 감속 정지")
print("x: 프로그램 종료")
print("================")

while True:
    if msvcrt.kbhit():
        key = msvcrt.getch().decode('utf-8').lower()
        
        if key == 's':
            # 속도 1단계 설정 후 X축 +방향 연속 드라이브
            send_cmd(0x04, 0x10)  # 속도선택: X축 속도 1
            time.sleep(0.1)
            send_cmd(0x01, 0x20)  # 연속 드라이브: X축 +방향
            print("→ X축 +방향 연속 드라이브 시작 (속도 1)")
            
        elif key == 'r':
            # 속도 1단계 설정 후 X축 -방향 연속 드라이브
            send_cmd(0x04, 0x10)  # 속도선택: X축 속도 1
            time.sleep(0.1)
            send_cmd(0x01, 0x10)  # 연속 드라이브: X축 -방향
            print("← X축 -방향 연속 드라이브 시작 (속도 1)")
            
        elif key == 'q':
            # X축 감속 정지
            send_cmd(0x05, 0x01)
            print("■ X축 감속 정지")
            
        elif key == 'x':
            print("프로그램 종료")
            break
    
    time.sleep(0.05)  # CPU 부하 감소

client.close()
