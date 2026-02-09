from pymodbus.client import ModbusSerialClient
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time


class MotorControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("모터 제어 시스템")
        self.root.geometry("750x550")
        self.root.resizable(False, False)
        self.root.configure(bg='#1a1a2e')
        
        self.client = None
        self.connected = False
        
        self.SLAVE_ID = 1
        self.ADDR = 0  # 40001 → offset 0
        
        # X축 설정
        self.X_SPEED_ADDR = 0x0452  # X축 드라이브 속도 1 설정 주소
        # Y축 설정
        self.Y_SPEED_ADDR = 0x0464  # Y축 드라이브 속도 1 설정 주소
        
        self.setup_styles()
        self.create_widgets()
        
    def setup_styles(self):
        """커스텀 스타일 설정"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
    def create_widgets(self):
        """위젯 생성"""
        # 메인 컨테이너
        main_frame = tk.Frame(self.root, bg='#1a1a2e')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # 타이틀
        title_label = tk.Label(main_frame, 
                              text="⚙️ 모터 제어 시스템",
                              font=('Malgun Gothic', 20, 'bold'),
                              fg='#edf2f4',
                              bg='#1a1a2e')
        title_label.pack(pady=(0, 20))
        
        # 연결 설정 프레임
        conn_frame = tk.LabelFrame(main_frame, 
                                   text=" 연결 설정 ",
                                   font=('Malgun Gothic', 10, 'bold'),
                                   fg='#8d99ae',
                                   bg='#16213e',
                                   bd=2)
        conn_frame.pack(fill='x', pady=(0, 15))
        
        conn_inner = tk.Frame(conn_frame, bg='#16213e')
        conn_inner.pack(fill='x', padx=15, pady=10)
        
        # COM 포트 선택
        tk.Label(conn_inner, text="포트:", 
                font=('Malgun Gothic', 10),
                fg='#edf2f4', bg='#16213e').pack(side='left')
        
        self.port_var = tk.StringVar(value='COM7')
        self.port_entry = tk.Entry(conn_inner, 
                                   textvariable=self.port_var,
                                   width=10,
                                   font=('Consolas', 11),
                                   bg='#0f3460',
                                   fg='#edf2f4',
                                   insertbackground='#edf2f4',
                                   bd=0)
        self.port_entry.pack(side='left', padx=(5, 20))
        
        # 연결 버튼
        self.connect_btn = tk.Button(conn_inner,
                                    text="연결",
                                    font=('Malgun Gothic', 10, 'bold'),
                                    bg='#00b4d8',
                                    fg='white',
                                    activebackground='#0096c7',
                                    activeforeground='white',
                                    bd=0,
                                    padx=20,
                                    pady=5,
                                    cursor='hand2',
                                    command=self.toggle_connection)
        self.connect_btn.pack(side='left')
        
        # 연결 상태 표시
        self.status_indicator = tk.Label(conn_inner,
                                        text="● 연결 끊김",
                                        font=('Malgun Gothic', 10),
                                        fg='#ef233c',
                                        bg='#16213e')
        self.status_indicator.pack(side='right')
        
        # 축 제어 컨테이너 (X축과 Y축 나란히)
        axis_container = tk.Frame(main_frame, bg='#1a1a2e')
        axis_container.pack(fill='both', expand=True, pady=(0, 15))
        
        # ===== 상부 스테이지 제어 프레임 =====
        x_control_frame = tk.LabelFrame(axis_container,
                                        text=" 상부 스테이지 ",
                                        font=('Malgun Gothic', 10, 'bold'),
                                        fg='#2a9d8f',
                                        bg='#16213e',
                                        bd=2)
        x_control_frame.pack(side='left', fill='both', expand=True, padx=(0, 7))
        
        x_inner = tk.Frame(x_control_frame, bg='#16213e')
        x_inner.pack(expand=True, pady=15, padx=10)
        
        # 상부 스테이지 방향 선택
        x_dir_frame = tk.Frame(x_inner, bg='#16213e')
        x_dir_frame.pack(pady=(0, 10))
        
        self.x_direction_var = tk.StringVar(value='plus')
        
        tk.Radiobutton(x_dir_frame, text="▲ +방향", variable=self.x_direction_var,
                      value='plus', font=('Malgun Gothic', 11, 'bold'),
                      fg='#2a9d8f', bg='#16213e', activebackground='#16213e',
                      selectcolor='#0f3460', cursor='hand2').pack(side='left', padx=5)
        
        tk.Radiobutton(x_dir_frame, text="▼ -방향", variable=self.x_direction_var,
                      value='minus', font=('Malgun Gothic', 11, 'bold'),
                      fg='#e76f51', bg='#16213e', activebackground='#16213e',
                      selectcolor='#0f3460', cursor='hand2').pack(side='left', padx=5)
        
        # X축 속도값 입력
        x_speed_frame = tk.Frame(x_inner, bg='#16213e')
        x_speed_frame.pack(pady=(0, 10))
        
        tk.Label(x_speed_frame, text="속도값:",
                font=('Malgun Gothic', 10), fg='#edf2f4', bg='#16213e').pack(side='left')
        
        self.x_speed_var = tk.StringVar(value='1000')
        tk.Entry(x_speed_frame, textvariable=self.x_speed_var, width=7,
                font=('Consolas', 11), bg='#0f3460', fg='#edf2f4',
                insertbackground='#edf2f4', bd=0, justify='center').pack(side='left', padx=5)
        
        self.x_apply_btn = tk.Button(x_speed_frame, text="적용",
                                    font=('Malgun Gothic', 9, 'bold'),
                                    bg='#f77f00', fg='white', bd=0, padx=10,
                                    cursor='hand2', state='disabled',
                                    command=self.apply_x_speed)
        self.x_apply_btn.pack(side='left')
        
        # X축 시작/정지 버튼
        x_btn_frame = tk.Frame(x_inner, bg='#16213e')
        x_btn_frame.pack(pady=(5, 0))
        
        self.x_start_btn = tk.Button(x_btn_frame, text="▶ 시작",
                                    font=('Malgun Gothic', 12, 'bold'),
                                    bg='#2a9d8f', fg='white', bd=0,
                                    width=8, height=1, cursor='hand2',
                                    state='disabled', command=self.start_x_motor)
        self.x_start_btn.pack(side='left', padx=5)
        
        self.x_stop_btn = tk.Button(x_btn_frame, text="■ 정지",
                                   font=('Malgun Gothic', 12, 'bold'),
                                   bg='#e63946', fg='white', bd=0,
                                   width=8, height=1, cursor='hand2',
                                   state='disabled', command=self.stop_x_motor)
        self.x_stop_btn.pack(side='left', padx=5)
        
        # ===== 하부 스테이지 제어 프레임 =====
        y_control_frame = tk.LabelFrame(axis_container,
                                        text=" 하부 스테이지 ",
                                        font=('Malgun Gothic', 10, 'bold'),
                                        fg='#9b5de5',
                                        bg='#16213e',
                                        bd=2)
        y_control_frame.pack(side='left', fill='both', expand=True, padx=(7, 0))
        
        y_inner = tk.Frame(y_control_frame, bg='#16213e')
        y_inner.pack(expand=True, pady=15, padx=10)
        
        # 하부 스테이지 방향 선택
        y_dir_frame = tk.Frame(y_inner, bg='#16213e')
        y_dir_frame.pack(pady=(0, 10))
        
        self.y_direction_var = tk.StringVar(value='plus')
        
        tk.Radiobutton(y_dir_frame, text="▲ +방향", variable=self.y_direction_var,
                      value='plus', font=('Malgun Gothic', 11, 'bold'),
                      fg='#9b5de5', bg='#16213e', activebackground='#16213e',
                      selectcolor='#0f3460', cursor='hand2').pack(side='left', padx=5)
        
        tk.Radiobutton(y_dir_frame, text="▼ -방향", variable=self.y_direction_var,
                      value='minus', font=('Malgun Gothic', 11, 'bold'),
                      fg='#f72585', bg='#16213e', activebackground='#16213e',
                      selectcolor='#0f3460', cursor='hand2').pack(side='left', padx=5)
        
        # Y축 속도값 입력
        y_speed_frame = tk.Frame(y_inner, bg='#16213e')
        y_speed_frame.pack(pady=(0, 10))
        
        tk.Label(y_speed_frame, text="속도값:",
                font=('Malgun Gothic', 10), fg='#edf2f4', bg='#16213e').pack(side='left')
        
        self.y_speed_var = tk.StringVar(value='1000')
        tk.Entry(y_speed_frame, textvariable=self.y_speed_var, width=7,
                font=('Consolas', 11), bg='#0f3460', fg='#edf2f4',
                insertbackground='#edf2f4', bd=0, justify='center').pack(side='left', padx=5)
        
        self.y_apply_btn = tk.Button(y_speed_frame, text="적용",
                                    font=('Malgun Gothic', 9, 'bold'),
                                    bg='#f77f00', fg='white', bd=0, padx=10,
                                    cursor='hand2', state='disabled',
                                    command=self.apply_y_speed)
        self.y_apply_btn.pack(side='left')
        
        # Y축 시작/정지 버튼
        y_btn_frame = tk.Frame(y_inner, bg='#16213e')
        y_btn_frame.pack(pady=(5, 0))
        
        self.y_start_btn = tk.Button(y_btn_frame, text="▶ 시작",
                                    font=('Malgun Gothic', 12, 'bold'),
                                    bg='#9b5de5', fg='white', bd=0,
                                    width=8, height=1, cursor='hand2',
                                    state='disabled', command=self.start_y_motor)
        self.y_start_btn.pack(side='left', padx=5)
        
        self.y_stop_btn = tk.Button(y_btn_frame, text="■ 정지",
                                   font=('Malgun Gothic', 12, 'bold'),
                                   bg='#e63946', fg='white', bd=0,
                                   width=8, height=1, cursor='hand2',
                                   state='disabled', command=self.stop_y_motor)
        self.y_stop_btn.pack(side='left', padx=5)
        
        # 로그 프레임
        log_frame = tk.LabelFrame(main_frame,
                                  text=" 통신 로그 ",
                                  font=('Malgun Gothic', 10, 'bold'),
                                  fg='#8d99ae',
                                  bg='#16213e',
                                  bd=2)
        log_frame.pack(fill='x')
        
        self.log_text = tk.Text(log_frame,
                               height=5,
                               font=('Consolas', 9),
                               bg='#0f3460',
                               fg='#a8dadc',
                               bd=0,
                               state='disabled')
        self.log_text.pack(fill='x', padx=10, pady=10)
        
        # 키보드 바인딩
        self.root.bind('<Left>', lambda e: self.x_direction_var.set('minus'))
        self.root.bind('<Right>', lambda e: self.x_direction_var.set('plus'))
        self.root.bind('<Up>', lambda e: self.y_direction_var.set('plus'))
        self.root.bind('<Down>', lambda e: self.y_direction_var.set('minus'))
        
        # 창 닫기 이벤트
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def log(self, message):
        """로그 메시지 추가"""
        self.log_text.config(state='normal')
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert('end', f"[{timestamp}] {message}\n")
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        
    def toggle_connection(self):
        """연결/해제 토글"""
        if self.connected:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        """Modbus 연결"""
        port = self.port_var.get()
        
        self.client = ModbusSerialClient(
            port=port,
            baudrate=9600,
            parity='N',
            stopbits=1,
            bytesize=8,
            timeout=1
        )
        
        if self.client.connect():
            self.connected = True
            self.connect_btn.config(text="연결 해제", bg='#6c757d')
            self.status_indicator.config(text="● 연결됨", fg='#06d6a0')
            self.port_entry.config(state='disabled')
            
            # 제어 버튼 활성화
            self.x_start_btn.config(state='normal')
            self.x_stop_btn.config(state='normal')
            self.x_apply_btn.config(state='normal')
            self.y_start_btn.config(state='normal')
            self.y_stop_btn.config(state='normal')
            self.y_apply_btn.config(state='normal')
            
            self.log(f"{port} 연결 성공")
        else:
            messagebox.showerror("연결 실패", f"{port}에 연결할 수 없습니다.")
            self.log(f"{port} 연결 실패")
            
    def disconnect(self):
        """연결 해제"""
        if self.client:
            self.client.close()
            self.client = None
            
        self.connected = False
        self.connect_btn.config(text="연결", bg='#00b4d8')
        self.status_indicator.config(text="● 연결 끊김", fg='#ef233c')
        self.port_entry.config(state='normal')
        
        # 제어 버튼 비활성화
        self.x_start_btn.config(state='disabled')
        self.x_stop_btn.config(state='disabled')
        self.x_apply_btn.config(state='disabled')
        self.y_start_btn.config(state='disabled')
        self.y_stop_btn.config(state='disabled')
        self.y_apply_btn.config(state='disabled')
        
        self.log("연결 해제됨")
        
    def send_cmd(self, hi, lo):
        """명령 전송 (기본 주소)"""
        if not self.connected or not self.client:
            return False
            
        value = (hi << 8) | lo
        try:
            rr = self.client.write_register(self.ADDR, value)
            
            if rr.isError():
                self.log(f"쓰기 에러: {rr}")
                return False
            else:
                self.log(f"전송: 0x{value:04X}")
                return True
        except Exception as e:
            self.log(f"통신 오류: {e}")
            return False
    
    def write_register(self, address, value):
        """특정 주소에 값 쓰기"""
        if not self.connected or not self.client:
            return False
            
        try:
            rr = self.client.write_register(address, value)
            
            if rr.isError():
                self.log(f"쓰기 에러: {rr}")
                return False
            else:
                self.log(f"주소 0x{address:04X}에 {value} 전송")
                return True
        except Exception as e:
            self.log(f"통신 오류: {e}")
            return False
    
    # ===== 상부 스테이지 제어 =====
    def apply_x_speed(self):
        """상부 스테이지 속도값 적용"""
        if not self.connected:
            return
        try:
            speed_value = int(self.x_speed_var.get())
            if speed_value < 1 or speed_value > 8000:
                messagebox.showwarning("범위 오류", "속도값은 1~8000 사이여야 합니다.")
                return
            if self.write_register(self.X_SPEED_ADDR, speed_value):
                self.log(f"⚡ 상부 속도 설정: {speed_value}")
        except ValueError:
            messagebox.showwarning("입력 오류", "올바른 숫자를 입력하세요.")
            
    def start_x_motor(self):
        """상부 스테이지 모터 시작"""
        if not self.connected:
            return
        
        direction = self.x_direction_var.get()
        
        # 속도 1단 선택
        self.send_cmd(0x04, 0x10)  # 속도선택: X축 속도 1
        time.sleep(0.1)
        
        if direction == 'plus':
            self.send_cmd(0x01, 0x20)  # X축 +방향
            self.log("▲ 상부 +방향 연속 드라이브 시작")
        else:
            self.send_cmd(0x01, 0x10)  # X축 -방향
            self.log("▼ 상부 -방향 연속 드라이브 시작")
        
    def stop_x_motor(self):
        """상부 스테이지 모터 정지"""
        if not self.connected:
            return
        self.send_cmd(0x05, 0x01)  # X축 감속 정지
        self.log("■ 상부 스테이지 감속 정지")
    
    # ===== 하부 스테이지 제어 =====
    def apply_y_speed(self):
        """하부 스테이지 속도값 적용"""
        if not self.connected:
            return
        try:
            speed_value = int(self.y_speed_var.get())
            if speed_value < 1 or speed_value > 8000:
                messagebox.showwarning("범위 오류", "속도값은 1~8000 사이여야 합니다.")
                return
            if self.write_register(self.Y_SPEED_ADDR, speed_value):
                self.log(f"⚡ 하부 속도 설정: {speed_value}")
        except ValueError:
            messagebox.showwarning("입력 오류", "올바른 숫자를 입력하세요.")
            
    def start_y_motor(self):
        """하부 스테이지 모터 시작"""
        if not self.connected:
            return
        
        direction = self.y_direction_var.get()
        
        # 속도 1단 선택
        self.send_cmd(0x04, 0x01)  # 속도선택: Y축 속도 1
        time.sleep(0.1)
        
        if direction == 'plus':
            self.send_cmd(0x01, 0x02)  # Y축 +방향
            self.log("▲ 하부 +방향 연속 드라이브 시작")
        else:
            self.send_cmd(0x01, 0x01)  # Y축 -방향
            self.log("▼ 하부 -방향 연속 드라이브 시작")
        
    def stop_y_motor(self):
        """하부 스테이지 모터 정지"""
        if not self.connected:
            return
        self.send_cmd(0x05, 0x02)  # Y축 감속 정지
        self.log("■ 하부 스테이지 감속 정지")
        
    def on_closing(self):
        """프로그램 종료"""
        if self.connected:
            self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorControlGUI(root)
    root.mainloop()
