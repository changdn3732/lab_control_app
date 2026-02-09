"""
홈 화면 - 프리미엄 대시보드 스타일
"""
import flet as ft


class HomeView:
    def __init__(self, page: ft.Page):
        self.page = page
    
    def build(self, navigate_to, clock_text: ft.Text):
        """홈 화면 빌드 - Premium Dashboard Style"""
        
        # ==================== 왼쪽 사이드바 ====================
        sidebar = ft.Container(
            content=ft.Column(
                [
                    # 로고
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.Icons.PRECISION_MANUFACTURING, size=32, color="#5B6EE1"),
                                ft.Text("LAB", size=18, weight=ft.FontWeight.BOLD, color="#333333"),
                                ft.Text("Control", size=12, color="#888888"),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=2,
                        ),
                        padding=ft.padding.only(top=30, bottom=30),
                    ),
                    
                    # 메뉴 아이템들
                    self._sidebar_item(ft.Icons.HOME_ROUNDED, "Home", True),
                    self._sidebar_item(ft.Icons.SETTINGS_SUGGEST, "Motors", False, lambda: navigate_to("scheduler")),
                    self._sidebar_item(ft.Icons.AIR, "Gas", False, lambda: navigate_to("device_settings")),
                    self._sidebar_item(ft.Icons.ANALYTICS, "Analytics", False),
                    
                    ft.Container(expand=True),
                    
                    # 하단 메뉴
                    self._sidebar_item(ft.Icons.SETTINGS, "Settings", False),
                    ft.Container(height=20),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            width=80,
            bgcolor="#ffffff",
            border=ft.border.only(right=ft.BorderSide(1, "#f0f0f0")),
            padding=ft.padding.symmetric(vertical=10),
        )
        
        # ==================== 메인 콘텐츠 영역 ====================
        
        # 상단 헤더
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Welcome back! 👋", size=14, color="#888888"),
                            ft.Text("Lab Control Dashboard", size=24, weight=ft.FontWeight.BOLD, color="#333333"),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    # 검색 바
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.SEARCH, size=18, color="#aaaaaa"),
                                ft.Text("Search...", size=14, color="#aaaaaa"),
                            ],
                            spacing=10,
                        ),
                        bgcolor="#f8f9fa",
                        border_radius=25,
                        padding=ft.padding.symmetric(horizontal=20, vertical=12),
                        width=220,
                    ),
                    ft.Container(width=15),
                    # 알림 아이콘
                    ft.Container(
                        content=ft.Icon(ft.Icons.NOTIFICATIONS_NONE, size=22, color="#666666"),
                        bgcolor="#f8f9fa",
                        border_radius=25,
                        padding=12,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.padding.only(left=30, right=30, top=25, bottom=20),
        )
        
        # 모터 상태 카드들 (파스텔 색상)
        motor_cards = ft.Row(
            [
                self._motor_status_card("상부 스테이지", "ID: 1", "Ready", "#FFF9E6", "#F4C430", ft.Icons.ARROW_UPWARD),
                self._motor_status_card("하부 스테이지", "ID: 2", "Ready", "#E8F5E9", "#4CAF50", ft.Icons.ARROW_DOWNWARD),
                self._motor_status_card("상부 회전", "ID: 3", "Ready", "#FFF0F5", "#E91E63", ft.Icons.ROTATE_RIGHT),
                self._motor_status_card("하부 회전", "ID: 4", "Ready", "#E3F2FD", "#2196F3", ft.Icons.ROTATE_LEFT),
            ],
            spacing=20,
            scroll="auto",
        )
        
        # 퀵 액션 카드
        quick_actions = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Quick Actions", size=16, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            self._action_button("Motorized\nPulling", ft.Icons.SETTINGS_SUGGEST, "#5B6EE1", lambda: navigate_to("scheduler")),
                            self._action_button("Gas\nSettings", ft.Icons.AIR, "#17a2b8", lambda: navigate_to("device_settings")),
                            self._action_button("Import\nData", ft.Icons.FOLDER_OPEN, "#4ECDC4", lambda: self._on_import_click()),
                            self._action_button("System\nSettings", ft.Icons.TUNE, "#95A5A6", lambda: self._on_settings_click()),
                        ],
                        spacing=20,
                    ),
                ],
            ),
            bgcolor="#ffffff",
            border_radius=20,
            padding=25,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.05, "#000000"),
            ),
        )
        
        # 시스템 상태 카드
        system_status = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("System Status", size=16, weight=ft.FontWeight.BOLD, color="#333333"),
                            ft.Container(expand=True),
                            ft.Container(
                                content=ft.Text("Online", size=11, color="#ffffff"),
                                bgcolor="#4CAF50",
                                border_radius=12,
                                padding=ft.padding.symmetric(horizontal=12, vertical=4),
                            ),
                        ],
                    ),
                    ft.Container(height=20),
                    self._status_row("COM Port", "COM7", "#5B6EE1"),
                    self._status_row("Baudrate", "9600", "#4ECDC4"),
                    self._status_row("Connected", "4 devices", "#4CAF50"),
                    self._status_row("Last Sync", "Just now", "#888888"),
                ],
            ),
            bgcolor="#ffffff",
            border_radius=20,
            padding=25,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.05, "#000000"),
            ),
        )
        
        # 메인 콘텐츠 조합
        main_content = ft.Container(
            content=ft.Column(
                [
                    header,
                    ft.Container(
                        content=ft.Column(
                            [
                                # 모터 카드 섹션
                                ft.Text("Motor Status", size=16, weight=ft.FontWeight.BOLD, color="#333333"),
                                ft.Container(height=10),
                                motor_cards,
                                ft.Container(height=25),
                                
                                # 하단 섹션 (퀵 액션 + 시스템 상태)
                                ft.Row(
                                    [
                                        ft.Container(content=quick_actions, expand=2),
                                        ft.Container(width=20),
                                        ft.Container(content=system_status, expand=1),
                                    ],
                                    expand=True,
                                ),
                            ],
                            expand=True,
                        ),
                        padding=ft.padding.symmetric(horizontal=30),
                        expand=True,
                    ),
                    
                    # 푸터
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("© 2026 Lab Control System", size=11, color="#aaaaaa"),
                                ft.Container(expand=True),
                                clock_text,
                            ],
                        ),
                        padding=ft.padding.symmetric(horizontal=30, vertical=15),
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
            bgcolor="#f8f9fc",
        )
        
        # 전체 레이아웃
        return ft.Row(
            [
                sidebar,
                main_content,
            ],
            expand=True,
            spacing=0,
        )
    
    def _sidebar_item(self, icon, label, active=False, on_click=None):
        """사이드바 메뉴 아이템"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        icon, 
                        size=22, 
                        color="#5B6EE1" if active else "#888888"
                    ),
                    ft.Text(
                        label, 
                        size=9, 
                        color="#5B6EE1" if active else "#888888",
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            bgcolor="#EEF0FF" if active else None,
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            on_click=lambda _: on_click() if on_click else None,
            ink=True,
        )
    
    def _motor_status_card(self, name, sub, status, bg_color, accent_color, icon):
        """모터 상태 카드 (파스텔 스타일)"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(icon, size=18, color=accent_color),
                                bgcolor="#ffffff",
                                border_radius=10,
                                padding=8,
                            ),
                            ft.Container(expand=True),
                            ft.Container(
                                content=ft.Container(width=8, height=8, bgcolor=accent_color, border_radius=4),
                            ),
                        ],
                    ),
                    ft.Container(height=15),
                    ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color="#333333"),
                    ft.Text(sub, size=11, color="#888888"),
                    ft.Container(height=8),
                    ft.Text(status, size=12, color=accent_color, weight=ft.FontWeight.W_500),
                ],
            ),
            width=160,
            height=140,
            bgcolor=bg_color,
            border_radius=18,
            padding=18,
        )
    
    def _action_button(self, label, icon, color, on_click=None):
        """퀵 액션 버튼"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=26, color="#ffffff"),
                        bgcolor=color,
                        border_radius=16,
                        padding=18,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        label, 
                        size=12, 
                        color="#333333", 
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            on_click=lambda _: on_click() if on_click else None,
            ink=True,
            border_radius=16,
            padding=10,
        )
    
    def _status_row(self, label, value, color):
        """시스템 상태 행"""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Container(width=6, height=6, bgcolor=color, border_radius=3),
                    ),
                    ft.Text(label, size=12, color="#888888", width=80),
                    ft.Container(expand=True),
                    ft.Text(value, size=12, color="#333333", weight=ft.FontWeight.W_500),
                ],
                spacing=10,
            ),
            padding=ft.padding.symmetric(vertical=8),
            border=ft.border.only(bottom=ft.BorderSide(1, "#f5f5f5")),
        )
    
    def _on_import_click(self):
        """USB 데이터 가져오기"""
        print("Import USB Data clicked")
    
    def _on_settings_click(self):
        """시스템 설정"""
        print("System Settings clicked")
