import base64
import io
import os
import socket
import threading
import time
from tkinter import filedialog
from urllib.parse import urlparse
from urllib.request import getproxies

import websocket  # pip install websocket-client
from PIL import Image, ImageTk  # встановлюється разом із customtkinter
from customtkinter import *

SERVER_URL = 'wss://corncob-greasily-semifinal.ngrok-free.dev'
MAX_IMAGE_BYTES = 700_000  # ліміт після стиснення, щоб повідомлення не було завеликим для сервера
IMAGE_MAX_SIDE = 1280  # фото зменшуються до цього розміру по довшій стороні
THUMB_SIZE = (260, 260)  # розмір превʼю в чаті
RECEIVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received')
EMOJIS = ['😀', '😂', '😍', '😎', '😢', '😡', '👍', '👎', '❤️', '🔥',
          '🎉', '🙏', '😊', '🤔', '😴', '👋', '💯', '✅', '❌', '⭐']


def proxy_settings():
    # Беремо системний проксі Windows (якщо він є), бо websocket сам його не бачить
    proxies = getproxies()
    proxy = proxies.get('https') or proxies.get('http')
    if not proxy:
        return {}
    p = urlparse(proxy if '://' in proxy else 'http://' + proxy)
    return {'http_proxy_host': p.hostname, 'http_proxy_port': p.port or 8080, 'proxy_type': 'http'}


def where_is_server():
    # Показує, в яку IP-адресу перетворюється домен (для діагностики)
    try:
        return socket.gethostbyname(urlparse(SERVER_URL).hostname)
    except Exception as e:
        return f"не вдалося знайти адресу ({e})"


def prepare_image(path):
    # Стискає фото в JPEG, щоб його можна було надіслати текстом через сервер
    img = Image.open(path)
    img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return buf.getvalue()


class MainWindow(CTk):
    def __init__(self):
        super().__init__()
        self.geometry('400x300')
        self.menu_widgets = []  # віджети бічного меню, які створюються при відкритті
        self.image_refs = []  # тримаємо посилання на зображення, інакше їх прибере збирач сміття
        self.image_count = 0
        self.emoji_win = None  # вікно вибору смайлів
        # menu frame
        self.menu_frame = CTkFrame(self, width=30, height=300)
        self.menu_frame.pack_propagate(False)
        self.menu_frame.place(x=0, y=0)
        self.is_show_menu = False
        self.speed_animate_menu = -5
        self.btn = CTkButton(self, text='▶️', command=self.toggle_show_menu, width=30)
        self.btn.place(x=0, y=0)
        # main
        self.chat_field = CTkTextbox(self, font=('Arial', 14, 'bold'), state='disable')
        self.chat_field.place(x=0, y=0)
        self.message_entry = CTkEntry(self, placeholder_text='Введіть повідомлення:', height=40)
        self.message_entry.place(x=0, y=0)
        self.message_entry.bind('<Return>', self.send_message)  # Enter відправляє повідомлення
        self.emoji_button = CTkButton(self, text='🙂', width=50, height=40, command=self.open_emoji_picker)
        self.emoji_button.place(x=0, y=0)
        self.photo_button = CTkButton(self, text='📷', width=50, height=40, command=self.send_photo)
        self.photo_button.place(x=0, y=0)
        self.send_button = CTkButton(self, text='>', width=50, height=40, command=self.send_message)
        self.send_button.place(x=0, y=0)

        self.username = 'Artem'
        self.sock = None
        try:
            self.sock = websocket.create_connection(
                SERVER_URL, header=["ngrok-skip-browser-warning: true"], **proxy_settings())
            hello = f"TEXT@{self.username}@[SYSTEM] {self.username} приєднався(лась) до чату!"
            self.sock.send(hello)
            threading.Thread(target=self.recv_message, daemon=True).start()
        except Exception as e:
            self.add_message(f"Не вдалося підключитися до сервера: {e}")
            self.add_message(f"IP сервера: {where_is_server()}, проксі: {proxy_settings() or 'немає'}")

        self.adaptive_ui()

    def toggle_show_menu(self):
        if self.is_show_menu:
            self.is_show_menu = False
            self.speed_animate_menu *= -1
            self.btn.configure(text='▶️')
            self.show_menu()
        else:
            self.is_show_menu = True
            self.speed_animate_menu *= -1
            self.btn.configure(text='◀️')
            self.show_menu()
            # setting menu widgets
            label = CTkLabel(self.menu_frame, text='Імʼя')
            label.pack(pady=30)
            self.entry = CTkEntry(self.menu_frame, placeholder_text=self.username)
            self.entry.pack()
            self.entry.bind('<Return>', self.change_name)  # Enter теж зберігає ім'я
            button = CTkButton(self.menu_frame, text='Зберегти', width=100, command=self.change_name)
            button.pack(pady=10)
            self.menu_widgets = [label, self.entry, button]

    def show_menu(self):
        self.menu_frame.configure(width=self.menu_frame.winfo_width() + self.speed_animate_menu)
        if not self.menu_frame.winfo_width() >= 200 and self.is_show_menu:
            self.after(10, self.show_menu)
        elif self.menu_frame.winfo_width() >= 40 and not self.is_show_menu:
            self.after(10, self.show_menu)
            for widget in self.menu_widgets:
                widget.destroy()
            self.menu_widgets = []

    def change_name(self, event=None):
        if not hasattr(self, 'entry'):
            return
        new_name = self.entry.get().strip().replace('@', '')  # '@' є роздільником у протоколі
        self.entry.delete(0, END)
        if not new_name or new_name == self.username:
            return
        old_name = self.username
        self.username = new_name
        self.entry.configure(placeholder_text=self.username)
        self.send_raw(f"TEXT@{new_name}@[SYSTEM] {old_name} тепер відомий(а) як {new_name}")

    def adaptive_ui(self):
        self.menu_frame.configure(height=self.winfo_height())
        self.chat_field.place(x=self.menu_frame.winfo_width())
        self.chat_field.configure(width=self.winfo_width() - self.menu_frame.winfo_width(),
                                  height=self.winfo_height() - 40)
        self.send_button.place(x=self.winfo_width() - 50, y=self.winfo_height() - 40)
        self.photo_button.place(x=self.winfo_width() - 100, y=self.winfo_height() - 40)
        self.emoji_button.place(x=self.winfo_width() - 150, y=self.winfo_height() - 40)
        self.message_entry.place(x=self.menu_frame.winfo_width(), y=self.send_button.winfo_y())
        self.message_entry.configure(
            width=self.winfo_width() - self.menu_frame.winfo_width() - 150)

        self.after(50, self.adaptive_ui)

    def add_message(self, text):
        self.chat_field.configure(state='normal')
        self.chat_field.insert(END, text + '\n')
        self.chat_field.see(END)  # прокрутка до останнього повідомлення
        self.chat_field.configure(state='disable')

    def add_image(self, author, path):
        # Показує превʼю фото в чаті; клік відкриває його у повному розмірі
        img = Image.open(path)
        thumb = img.copy()
        thumb.thumbnail(THUMB_SIZE)
        photo = ImageTk.PhotoImage(thumb)
        self.image_refs.append(photo)

        text_widget = self.chat_field._textbox  # внутрішній tkinter Text, у ньому можна вставляти картинки
        self.chat_field.configure(state='normal')
        text_widget.insert(END, f"{author}:\n")
        start = text_widget.index("end-1c")
        text_widget.image_create(start, image=photo)
        self.image_count += 1
        tag = f"img{self.image_count}"
        text_widget.tag_add(tag, start, f"{start}+1c")
        text_widget.tag_bind(tag, '<Button-1>', lambda e, p=path: self.open_image(p))
        text_widget.tag_bind(tag, '<Enter>', lambda e: text_widget.config(cursor='hand2'))
        text_widget.tag_bind(tag, '<Leave>', lambda e: text_widget.config(cursor=''))
        text_widget.insert(END, '\n')
        text_widget.see(END)
        self.chat_field.configure(state='disable')

    def open_image(self, path):
        # Відкриває фото у окремому вікні в повному розмірі
        win = CTkToplevel(self)
        win.title(os.path.basename(path))
        img = Image.open(path)
        img.thumbnail((1000, 800))
        photo = CTkImage(light_image=img, dark_image=img, size=img.size)
        label = CTkLabel(win, image=photo, text='')
        label.image = photo  # тримаємо посилання
        label.pack(padx=10, pady=10)

    def open_emoji_picker(self):
        # Вікно з сіткою смайлів; клік вставляє смайл у поле вводу
        if self.emoji_win is not None and self.emoji_win.winfo_exists():
            self.emoji_win.focus()
            return
        win = CTkToplevel(self)
        win.title('Смайли')
        win.resizable(False, False)
        for i, emoji in enumerate(EMOJIS):
            btn = CTkButton(win, text=emoji, width=44, height=36, font=('Segoe UI Emoji', 18),
                            command=lambda em=emoji: self.insert_emoji(em))
            btn.grid(row=i // 5, column=i % 5, padx=4, pady=4)
        self.emoji_win = win

    def insert_emoji(self, emoji):
        self.message_entry.insert(END, emoji)
        self.message_entry.focus()

    def send_raw(self, data):
        if self.sock is None:
            self.add_message("[SYSTEM] Немає з'єднання з сервером")
            return False
        try:
            self.sock.send(data)
            return True
        except Exception:
            self.add_message("[SYSTEM] Не вдалося надіслати повідомлення")
            return False

    def send_message(self, event=None):
        message = self.message_entry.get().strip()
        if message:
            if self.send_raw(f"TEXT@{self.username}@{message}"):
                self.add_message(f"{self.username}: {message}")
        self.message_entry.delete(0, END)

    def send_photo(self):
        path = filedialog.askopenfilename(
            title='Оберіть фото',
            filetypes=[('Зображення', '*.jpg *.jpeg *.png *.gif *.bmp *.webp'), ('Усі файли', '*.*')])
        if not path:
            return
        try:
            data = prepare_image(path)
        except Exception as e:
            self.add_message(f"[SYSTEM] Не вдалося відкрити зображення: {e}")
            return
        if len(data) > MAX_IMAGE_BYTES:
            self.add_message(f"[SYSTEM] Фото завелике ({len(data) // 1000} КБ), оберіть інше")
            return
        name = os.path.splitext(os.path.basename(path))[0].replace('@', '') + '.jpg'
        payload = base64.b64encode(data).decode('ascii')  # base64 не містить '@'
        if self.send_raw(f"IMAGE@{self.username}@{name}@{payload}"):
            self.show_image("Ви", name, payload)

    def save_image(self, filename, payload):
        os.makedirs(RECEIVED_DIR, exist_ok=True)
        path = os.path.join(RECEIVED_DIR, f"{int(time.time() * 1000)}_{os.path.basename(filename)}")
        with open(path, 'wb') as f:
            f.write(base64.b64decode(payload))
        return path

    def show_image(self, author, filename, payload):
        try:
            path = self.save_image(filename, payload)
            self.add_image(author, path)
        except Exception as e:
            self.add_message(f"{author} надіслав(ла) зображення, але не вдалося показати: {e}")

    def recv_message(self):
        while True:
            try:
                data = self.sock.recv()
                if not data:
                    break
                # передаємо в головний потік (tkinter не любить інші потоки)
                self.after(0, self.handle_line, data.strip())
            except:
                break
        self.after(0, self.add_message, "[SYSTEM] З'єднання з сервером розірвано")
        self.sock.close()

    def handle_line(self, line):
        if not line:
            return
        msg_type = line.split("@", 1)[0]

        if msg_type == "TEXT":
            # максимум 2 розділники: тип, автор і весь решта тексту (він може містити '@')
            parts = line.split("@", 2)
            if len(parts) >= 3:
                self.add_message(f"{parts[1]}: {parts[2]}")
        elif msg_type == "IMAGE":
            parts = line.split("@", 3)
            if len(parts) >= 4:
                self.show_image(parts[1], parts[2], parts[3])
        else:
            self.add_message(line)


win = MainWindow()
win.mainloop()