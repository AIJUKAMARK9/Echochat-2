import flet as ft
import aiohttp
from config import settings

class ContactsScreen(ft.Column):
    def __init__(self, page: ft.Page, token: str, on_chat_open):
        super().__init__(expand=True)
        self.page = page
        self.token = token
        self.on_chat_open = on_chat_open
        self.search_field = ft.TextField(hint_text="Search contacts...", on_change=self.search)
        self.contacts_list = ft.ListView(expand=True)
        self.controls = [self.search_field, self.contacts_list]
        self.all_users = []
        self.page.run_task(self.load_users)

    async def load_users(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{settings.API_BASE}/social/contacts", headers=headers) as resp:
                    if resp.status == 200:
                        self.all_users = await resp.json()
                        self.display_users(self.all_users)
        except: pass

    def display_users(self, users):
        self.contacts_list.controls.clear()
        for user in users:
            self.contacts_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PERSON),
                    title=ft.Text(user["username"]),
                    subtitle=ft.Text(user.get("email", "")),
                    on_click=lambda e, uid=user["id"]: self.on_chat_open(uid)
                )
            )
        self.page.update()

    def search(self, e):
        query = self.search_field.value.lower()
        filtered = [u for u in self.all_users if query in u["username"].lower()]
        self.display_users(filtered)
