import flet as ft
import aiohttp
from config import settings
from chat_screen import ChatScreen
from contacts_screen import ContactsScreen

class EchoChatApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "EchoChat"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.token = None
        self.current_user = None
        self.show_login()

    def show_login(self):
        self.page.controls.clear()
        self.page.add(
            ft.Column([
                ft.Text("Welcome to EchoChat", size=32, weight=ft.FontWeight.BOLD),
                ft.TextField(label="Username", ref="username"),
                ft.TextField(label="Password", password=True, ref="password"),
                ft.ElevatedButton("Login", on_click=self.login),
                ft.TextButton("Register", on_click=lambda e: self.show_register()),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        )
        self.page.update()

    def show_register(self):
        self.page.controls.clear()
        self.page.add(
            ft.Column([
                ft.Text("Register", size=24, weight=ft.FontWeight.BOLD),
                ft.TextField(label="Username", ref="reg_username"),
                ft.TextField(label="Email", ref="reg_email"),
                ft.TextField(label="Password", password=True, ref="reg_password"),
                ft.ElevatedButton("Create Account", on_click=self.register),
                ft.TextButton("Back to Login", on_click=lambda e: self.show_login()),
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        )
        self.page.update()

    async def login(self, e):
        username = self.page.refs["username"].value
        password = self.page.refs["password"].value
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{settings.API_BASE}/auth/login", data={"username": username, "password": password}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data["access_token"]
                    async with session.get(f"{settings.API_BASE}/auth/me", headers={"Authorization": f"Bearer {self.token}"}) as me_resp:
                        if me_resp.status == 200:
                            self.current_user = await me_resp.json()
                            self.show_main()
                else:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("Login failed")))

    async def register(self, e):
        username = self.page.refs["reg_username"].value
        email = self.page.refs["reg_email"].value
        password = self.page.refs["reg_password"].value
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{settings.API_BASE}/auth/register", json={"username": username, "email": email, "password": password}) as resp:
                if resp.status == 201:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("Account created! Login now.")))
                    self.show_login()
                else:
                    self.page.show_snack_bar(ft.SnackBar(content=ft.Text("Registration failed")))

    def show_main(self):
        self.page.controls.clear()
        self.page.appbar = ft.AppBar(title=ft.Text("EchoChat"), actions=[ft.IconButton(ft.Icons.ACCOUNT_CIRCLE, on_click=self.show_profile)])
        self.tabs = ft.Tabs(selected_index=0, on_change=self.tab_changed,
                             tabs=[ft.Tab(text="Chats", icon=ft.Icons.CHAT), ft.Tab(text="Profile", icon=ft.Icons.PERSON)])
        self.page.add(self.tabs)
        self.load_tab(0)
        self.page.update()

    def tab_changed(self, e):
        self.load_tab(e.control.selected_index)

    def load_tab(self, idx):
        if len(self.page.controls) > 1: self.page.controls.pop()
        if idx == 0:
            chat_screen = ChatScreen(self.page, self.token)
            self.page.add(chat_screen)
        elif idx == 1:
            if self.current_user:
                self.page.add(ft.Column([
                    ft.Text(f"Username: {self.current_user['username']}", size=20),
                    ft.Text(f"Email: {self.current_user['email']}"),
                    ft.ElevatedButton("Logout", on_click=lambda e: self.logout()),
                ]))
        self.page.update()

    def show_profile(self, e):
        # already in Profile tab, just switch
        self.tabs.selected_index = 1
        self.load_tab(1)

    def logout(self, dlg=None):
        if dlg: dlg.open = False
        self.page.clean()
        self.token = None
        self.current_user = None
        self.show_login()

def main(page: ft.Page):
    EchoChatApp(page)

def build_flet_app():
    return ft.app(target=main)
