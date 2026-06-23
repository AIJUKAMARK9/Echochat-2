import flet as ft

class UserBubble(ft.Container):
    def __init__(self, text: str, is_me: bool = False):
        super().__init__(
            content=ft.Text(text, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.PURPLE_500 if is_me else ft.Colors.GREEN_700,
            border_radius=10,
            padding=10,
            margin=ft.margin.only(right=10 if is_me else 0, left=0 if is_me else 10, bottom=5),
            alignment=ft.alignment.center_right if is_me else ft.alignment.center_left,
        )
