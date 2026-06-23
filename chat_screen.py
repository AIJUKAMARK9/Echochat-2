import flet as ft
import aiohttp, asyncio, json
from urllib.parse import urlparse
from config import settings
from ui_components import UserBubble
from contacts_screen import ContactsScreen

class ChatScreen(ft.Column):
    def __init__(self, page: ft.Page, token: str):
        super().__init__(expand=True, spacing=10)
        self.page = page
        self.token = token
        self.user_id = None
        self.http_session = aiohttp.ClientSession()
        self.ws = None
        self.current_conversation_id = None
        self.tabs = ft.Tabs(selected_index=0, on_change=self.tab_changed,
                             tabs=[ft.Tab(text="Chats"), ft.Tab(text="Contacts")])
        self.controls.append(self.tabs)
        # Chats tab
        self.chat_list = ft.ListView(expand=True, auto_scroll=True)
        self.chat_empty = ft.Text("No conversations yet.", color=ft.Colors.GREY)
        self.chats_panel = ft.Column([self.chat_list, self.chat_empty])
        # Conversation panel (hidden initially)
        self.conv_title = ft.Text("", size=18, weight=ft.FontWeight.BOLD)
        self.msg_list = ft.ListView(expand=True, auto_scroll=True)
        self.msg_empty = ft.Text("No messages yet.", color=ft.Colors.GREY)
        self.input_field = ft.TextField(hint_text="Type a message...", expand=True, on_submit=self.send_msg)
        self.send_btn = ft.IconButton(icon=ft.Icons.SEND, on_click=self.send_msg)
        self.back_btn = ft.TextButton("← Back", on_click=self.back_to_chats)
        self.reconnect_label = ft.Text("", size=12, color=ft.Colors.YELLOW, visible=False)
        self.conv_panel = ft.Column([
            ft.Row([self.back_btn, self.conv_title]),
            self.msg_list, self.msg_empty,
            ft.Row([self.input_field, self.send_btn]),
            self.reconnect_label
        ], visible=False)
        self.controls.append(ft.Stack([self.chats_panel, self.conv_panel]))
        self.page.run_task(self.init_data)

    async def init_data(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.http_session.get(f"{settings.API_BASE}/auth/me", headers=headers) as resp:
                if resp.status == 200:
                    me = await resp.json()
                    self.user_id = str(me["id"])
        except: pass
        await self.load_chats()

    async def load_chats(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.http_session.get(f"{settings.API_BASE}/social/conversations", headers=headers) as resp:
                if resp.status == 200:
                    convs = await resp.json()
                    self.chat_list.controls.clear()
                    self.chat_empty.visible = len(convs) == 0
                    for c in convs:
                        self.chat_list.controls.append(
                            ft.TextButton(text=c["other_user"], on_click=lambda e, cid=c["id"]: self.open_conversation(cid))
                        )
                    self.page.update()
        except: pass

    async def open_conversation(self, conv_id):
        self.current_conversation_id = conv_id
        self.chats_panel.visible = False
        self.conv_panel.visible = True
        self.page.update()
        self.conv_title.value = f"Chat {conv_id[:8]}"
        self.msg_list.controls.clear()
        self.msg_empty.visible = False
        self.page.update()
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self.http_session.get(f"{settings.API_BASE}/social/messages/{conv_id}?limit=50", headers=headers) as resp:
                if resp.status == 200:
                    msgs = await resp.json()
                    self.msg_empty.visible = len(msgs) == 0
                    for m in msgs:
                        is_me = m["sender_id"] == int(self.user_id)
                        self.msg_list.controls.append(
                            UserBubble(f"{m['sender_username']}: {m['content']}", is_me=is_me)
                        )
                    self.page.update()
        except: pass
        await self.connect_ws()

    async def connect_ws(self):
        if self.ws: await self.ws.close(); self.ws = None
        proto = "wss://" if settings.API_BASE.startswith("https") else "ws://"
        host = urlparse(settings.API_BASE).netloc
        ws_url = f"{proto}{host}/social/ws/chat?token={self.token}"
        retry_delay = 1
        while self.current_conversation_id:
            try:
                self.ws = await aiohttp.ClientSession().ws_connect(ws_url)
                self.reconnect_label.visible = False; self.page.update()
                self.page.run_task(self.listen_ws)
                return
            except:
                self.reconnect_label.value = "Reconnecting..."; self.reconnect_label.visible = True; self.page.update()
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay*2, 30)

    async def listen_ws(self):
        while self.current_conversation_id:
            try:
                async for msg in self.ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if ("conversation_id" in data and data["conversation_id"] == self.current_conversation_id) or \
                           ("group_id" in data and data.get("group_id") == self.current_conversation_id):
                            if data.get("sender_id") != int(self.user_id):
                                self.msg_list.controls.append(
                                    UserBubble(f"{data['sender_username']}: {data['content']}", is_me=False)
                                )
                                self.msg_empty.visible = False; self.page.update()
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR): break
            except: pass
            if self.current_conversation_id: await self.connect_ws()
            else: break

    async def send_msg(self, e):
        text = self.input_field.value.strip()
        if not text or not self.ws: return
        await self.ws.send_json({"action": "send_message", "conversation_id": self.current_conversation_id, "content": text})
        self.msg_list.controls.append(UserBubble(text, is_me=True))
        self.input_field.value = ""; self.msg_empty.visible = False; self.page.update()

    async def back_to_chats(self, e):
        self.conv_panel.visible = False; self.chats_panel.visible = True
        if self.ws: await self.ws.close(); self.ws = None
        self.current_conversation_id = None; self.page.update()

    def tab_changed(self, e):
        if e.control.selected_index == 0:
            self.chats_panel.visible = True; self.conv_panel.visible = False
            self.page.run_task(self.load_chats())
        else:
            self.chats_panel.visible = False; self.conv_panel.visible = False
            # Contacts tab handled by main shell

    async def dispose(self):
        if self.http_session: await self.http_session.close()
        if self.ws: await self.ws.close()
