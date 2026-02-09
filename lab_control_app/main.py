"""
Lab Control System - Flet 기반 통합 제어 앱
메인 화면: Motorized Pulling Control / Gas Control
"""
import flet as ft
from datetime import datetime
from views.home_view import HomeView
from views.scheduler_view import SchedulerView
from views.device_settings_view import DeviceSettingsView
import threading
import time
import sys
import io

# Windows 콘솔 인코딩 설정 (emoji 출력 문제 해결)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def main(page: ft.Page):
    # 페이지 설정
    page.title = "Lab Control System"
    page.window_width = 1200
    page.window_height = 800
    page.bgcolor = "#f8f9fc"
    page.padding = 0
    
    # 현재 시간 표시
    clock_text = ft.Text(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        size=14,
        color="#666666"
    )
    
    # 뷰 인스턴스
    home_view = HomeView(page)
    scheduler_view = SchedulerView(page)
    device_settings_view = DeviceSettingsView(page)
    
    # 네비게이션 함수
    def navigate_to(view_name: str):
        page.controls.clear()
        
        if view_name == "home":
            page.controls.append(home_view.build(navigate_to, clock_text))
        elif view_name == "scheduler":
            page.controls.append(scheduler_view.build(navigate_to))
        elif view_name == "device_settings":
            page.controls.append(device_settings_view.build(navigate_to))
        
        page.update()
    
    # 시계 업데이트 스레드
    def clock_thread():
        while True:
            time.sleep(1)
            try:
                clock_text.value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                page.update()
            except:
                break
    
    # 백그라운드 스레드 시작
    threading.Thread(target=clock_thread, daemon=True).start()
    
    # 초기 화면
    navigate_to("home")


if __name__ == "__main__":
    ft.run(target=main)
