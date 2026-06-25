import os
import sys
import threading
import time
import hashlib
from datetime import datetime
import customtkinter as ctk
import json
from PIL import Image, ImageTk, ImageGrab

CONFIG_FILE = "settings.json"

# Set Theme & Style
ctk.set_appearance_mode("Dark")  # Options: "System", "Dark", "Light"
ctk.set_default_color_theme("green")  # Options: "blue", "green", "dark-blue"

class ImageSaverApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Load Application Settings
        self.save_dir = os.path.abspath("./dataset")
        self.file_prefix = "img_"
        self.start_index = 1
        self.load_config()
        
        self.title("📷 Clipboard Image Auto-Saver (CustomTkinter)")
        self.geometry("680x580")
        self.minsize(600, 500)
        
        # Configure Grid layout
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Build UI Elements
        self.init_ui()
        
        # Clipboard monitor: 백그라운드 스레드는 신호만 보냄
        # 실제 grabclipboard()는 메인 스레드(after 콜백)에서만 호출
        self.running = True
        self.last_image_hash = None  # 이미지 해시 기반 중복 체크
        self._check_clipboard_requested = False  # 스레드→메인 신호 플래그
        self._auto_save_enabled = True  # ✅ 스레드 안전 bool (StringVar 대신 사용)

        self.monitor_thread = threading.Thread(target=self._monitor_tick, daemon=True)
        self.monitor_thread.start()

        # 메인 스레드에서 주기적으로 클립보드 체크
        self._schedule_clipboard_check()

        # Keyboard Bindings (Ctrl+V)
        self.bind("<Control-v>", self.on_ctrl_v)
        self.bind("<Control-V>", self.on_ctrl_v)
        
        self.log_action("프로그램이 실행되었습니다. 저장 경로를 확인하세요.")
        self.update_image_counter()

    def _monitor_tick(self):
        """백그라운드 스레드: 500ms마다 신호만 보냄 (grabclipboard 직접 호출 X)"""
        while self.running:
            if self._auto_save_enabled:  # ✅ bool 플래그 읽기 (Tkinter StringVar 접근 X)
                self._check_clipboard_requested = True
            time.sleep(0.5)

    def _schedule_clipboard_check(self):
        """메인 스레드에서 클립보드 실제 체크 (COM 안전)"""
        if self.running:
            if self._check_clipboard_requested:
                self._check_clipboard_requested = False
                self._grab_and_save_if_new()
            # 500ms 후 다시 예약
            self.after(500, self._schedule_clipboard_check)

    def _grab_and_save_if_new(self):
        """메인 스레드에서 안전하게 클립보드 이미지 읽기 (재시도 포함)"""
        img = None
        last_err = None
        # 클립보드 읽기 최대 3회 재시도 (Win+Shift+S 직후 아직 기록 중일 수 있음)
        for attempt in range(3):
            try:
                img = ImageGrab.grabclipboard()
                if img is not None:
                    break  # 성공
            except Exception as e:
                last_err = e
            time.sleep(0.15)  # 150ms 대기 후 재시도

        if last_err and img is None:
            self.log_action(f"[자동감지 오류] {str(last_err)}")
            return

        if isinstance(img, Image.Image):
            img_hash = self._image_hash(img)
            # img_hash가 None인 경우(해시 계산 실패)도 저장 시도
            # last_image_hash 갱신은 저장 성공 후 save_image() 내부에서 수행
            if img_hash is None or img_hash != self.last_image_hash:
                self.save_image(img, img_hash)
        elif isinstance(img, list):
            # 파일 경로 리스트인 경우 (드래그앤드롭 등) — 무시
            pass

    def _image_hash(self, img):
        """이미지 해시 (크기+샘플 픽셀 기반, 빠르고 안정적)"""
        try:
            # 작은 크기로 리샘플 후 해시 → 빠르고 메모리 절약
            thumb = img.copy()
            thumb.thumbnail((64, 64))
            return hashlib.md5(thumb.tobytes()).hexdigest()
        except Exception:
            return None

    def init_ui(self):
        # Header Layout
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(header_frame, text="📷 Clipboard Image Auto-Saver", font=ctk.CTkFont(size=18, weight="bold"))
        title_lbl.grid(row=0, column=0, sticky="w")

        self.count_lbl = ctk.CTkLabel(header_frame, text="수집된 이미지: 0 장", font=ctk.CTkFont(size=14, weight="bold"), text_color="#2ecc71")
        self.count_lbl.grid(row=0, column=1, sticky="e")

        # Folder Path Config Frame
        path_frame = ctk.CTkFrame(self)
        path_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        self.dir_lbl = ctk.CTkLabel(path_frame, text=f"저장 경로: {self.save_dir}", font=ctk.CTkFont(size=12))
        self.dir_lbl.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        # Container for path buttons
        btn_frame = ctk.CTkFrame(path_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=15, pady=10, sticky="e")

        dir_btn = ctk.CTkButton(btn_frame, text="폴더 변경", width=90, command=self.change_dir)
        dir_btn.grid(row=0, column=0, padx=(0, 5))

        open_btn = ctk.CTkButton(btn_frame, text="폴더 열기", width=90, fg_color="#27ae60", hover_color="#219653", command=self.open_dir)
        open_btn.grid(row=0, column=1, padx=(5, 0))

        # Main Workspace (Preview + Settings)
        workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        workspace_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        workspace_frame.grid_rowconfigure(0, weight=1)
        workspace_frame.grid_columnconfigure(0, weight=3) # Preview
        workspace_frame.grid_columnconfigure(1, weight=2) # Settings

        # Left Column: Image Preview
        self.preview_frame = ctk.CTkFrame(workspace_frame, fg_color="#18181A")
        self.preview_frame.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_lbl = ctk.CTkLabel(
            self.preview_frame, 
            text="캡처 후 이 창을 선택한 뒤\nCtrl + V를 누르거나\n실시간 자동 감지를 활성화하세요.",
            font=ctk.CTkFont(size=13),
            text_color="#8a8a8f"
        )
        self.preview_lbl.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Right Column: Settings Panel
        settings_frame = ctk.CTkFrame(workspace_frame)
        settings_frame.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        settings_frame.grid_columnconfigure(0, weight=1)

        # Prefix setting
        ctk.CTkLabel(settings_frame, text="파일 접두어 (Prefix):", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 2), sticky="w")
        self.prefix_entry = ctk.CTkEntry(settings_frame)
        self.prefix_entry.insert(0, self.file_prefix)
        self.prefix_entry.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.prefix_entry.bind("<KeyRelease>", self.update_settings)

        # Index setting
        ctk.CTkLabel(settings_frame, text="시작 일련번호:", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, padx=15, pady=(0, 2), sticky="w")
        self.index_entry = ctk.CTkEntry(settings_frame)
        self.index_entry.insert(0, str(self.start_index))
        self.index_entry.grid(row=3, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.index_entry.bind("<KeyRelease>", self.update_settings)

        # Auto save toggle
        self.auto_save_var = ctk.StringVar(value="on")
        self.auto_save_switch = ctk.CTkSwitch(
            settings_frame, text="실시간 자동 감지 저장",
            variable=self.auto_save_var, onvalue="on", offvalue="off",
            command=self._on_auto_save_toggle  # ✅ 스위치 변경 시 bool 플래그 동기화
        )
        self.auto_save_switch.grid(row=4, column=0, padx=15, pady=10, sticky="w")

        # Bottom Section: Logs History
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, padx=20, pady=(10, 5), sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_frame, text="최근 저장 기록", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=15, pady=(8, 2), sticky="w")
        
        self.log_textbox = ctk.CTkTextbox(log_frame, height=90, activate_scrollbars=True, text_color="#A0A0AA")
        self.log_textbox.grid(row=1, column=0, padx=15, pady=(0, 8), sticky="ew")
        self.log_textbox.configure(state="disabled")

        # Footer Status Bar with Creator Credit
        self.status_lbl = ctk.CTkLabel(self, text="준비 완료. 화면 캡처(Win+Shift+S) 후 진행하세요.", font=ctk.CTkFont(size=11), text_color="#71717A")
        self.status_lbl.grid(row=4, column=0, padx=20, pady=(2, 10), sticky="w")
        
        creator_lbl = ctk.CTkLabel(self, text="제작자: 코드깎는 kd", font=ctk.CTkFont(size=11, weight="bold"), text_color="#48C9B0")
        creator_lbl.grid(row=4, column=0, padx=20, pady=(2, 10), sticky="e")

    def _on_auto_save_toggle(self):
        """스위치 토글 시 메인 스레드에서 bool 플래그 동기화 (스레드 안전)"""
        self._auto_save_enabled = (self.auto_save_var.get() == "on")
        state = "활성화" if self._auto_save_enabled else "비활성화"
        self.log_action(f"자동 감지 저장 {state}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    loaded_dir = os.path.abspath(config.get("save_dir", self.save_dir))

                    # 드라이브/경로 유효성 검사: 존재하지 않는 드라이브면 기본 경로로 리셋
                    drive = os.path.splitdrive(loaded_dir)[0]
                    if drive and not os.path.exists(drive + "\\"):
                        print(f"[경고] 저장 경로의 드라이브({drive})가 없습니다. 기본 경로로 초기화합니다.")
                        self.save_dir = os.path.abspath("./dataset")
                    else:
                        self.save_dir = loaded_dir

                    self.file_prefix = config.get("file_prefix", self.file_prefix)
                    self.start_index = config.get("start_index", self.start_index)
            except Exception as e:
                print(f"설정 로드 실패: {e}")

    def save_config(self):
        try:
            config = {
                "save_dir": self.save_dir,
                "file_prefix": self.file_prefix,
                "start_index": self.start_index
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_action(f"설정 저장 실패: {e}")

    def change_dir(self):
        folder = QFileDialog_fallback()
        if folder:
            self.save_dir = os.path.abspath(folder)
            self.dir_lbl.configure(text=f"저장 경로: {self.save_dir}")
            self.update_image_counter()
            self.save_config()
            self.log_action(f"저장 경로 변경됨: {self.save_dir}")

    def open_dir(self):
        try:
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
            os.startfile(self.save_dir)
            self.log_action(f"폴더 열기: {self.save_dir}")
        except Exception as e:
            self.log_action(f"폴더 열기 실패: {str(e)}")

    def update_settings(self, event=None):
        self.file_prefix = self.prefix_entry.get()
        try:
            self.start_index = int(self.index_entry.get())
        except ValueError:
            self.start_index = 1
        self.save_config()

    def update_image_counter(self):
        if not os.path.exists(self.save_dir):
            return
        files = [f for f in os.listdir(self.save_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        self.count_lbl.configure(text=f"수집된 이미지: {len(files)} 장")

    def log_action(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("0.0", f"[{timestamp}] {text}\n")
        self.log_textbox.configure(state="disabled")

    # Handle Ctrl+V Event
    def on_ctrl_v(self, event):
        self.log_action("수동 Ctrl+V 감지")
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                img_hash = self._image_hash(img)
                # 저장 성공 후 save_image() 내부에서 해시 갱신
                self.save_image(img, img_hash)
            else:
                self.log_action("오류: 클립보드에 이미지가 없습니다.")
        except Exception as e:
            self.log_action(f"클립보드 읽기 에러: {str(e)}")

    # Save logic
    def save_image(self, img, img_hash=None):
        if not os.path.exists(self.save_dir):
            try:
                os.makedirs(self.save_dir)
                self.log_action(f"저장 폴더 생성: {self.save_dir}")
            except Exception as e:
                self.log_action(f"폴더 생성 실패: {str(e)}")
                return

        # 이미지 모드 자동 변환 (RGBA/P → RGB → PNG 저장 가능)
        try:
            if img.mode in ("RGBA", "LA"):
                # 투명 배경을 흰색으로 합성
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
        except Exception as conv_err:
            self.log_action(f"[경고] 이미지 모드 변환 실패 ({img.mode}): {conv_err}")

        # Get unique sequence filename
        while True:
            filename = f"{self.file_prefix}{self.start_index:04d}.png"
            filepath = os.path.join(self.save_dir, filename)
            if not os.path.exists(filepath):
                break
            self.start_index += 1

        # Show thumbnail preview
        try:
            max_w, max_h = 320, 240
            preview_img = img.copy()
            preview_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)
            
            ctk_img = ctk.CTkImage(light_image=preview_img, dark_image=preview_img, size=preview_img.size)
            self.preview_lbl.configure(image=ctk_img, text="")
            self.preview_lbl.image = ctk_img  # Reference retention
        except Exception as preview_err:
            self.log_action(f"미리보기 로드 오류: {preview_err}")

        # Save to disk — 최대 3회 재시도 (백신/클라우드 동기화 잠금 대응)
        saved = False
        last_save_err = None
        for attempt in range(3):
            try:
                img.save(filepath, "PNG")
                saved = True
                break
            except Exception as e:
                last_save_err = e
                time.sleep(0.2)  # 200ms 대기 후 재시도

        if saved:
            # ✅ 저장 성공 후에만 해시 갱신 — 실패 시 다음 폴링에서 재시도 가능
            self.last_image_hash = img_hash
            self.log_action(f"저장 성공: {filename}")
            # Auto increment sequence index
            self.start_index += 1
            self.index_entry.delete(0, ctk.END)
            self.index_entry.insert(0, str(self.start_index))
            self.update_image_counter()
            self.save_config()
            self.status_lbl.configure(text=f"최근 저장 완료: {filename} ({datetime.now().strftime('%M:%S')})", text_color="#2ecc71")
        else:
            err_type = type(last_save_err).__name__
            err_msg = str(last_save_err)
            self.log_action(f"❌ 저장 실패 (3회 시도 후 포기) [{err_type}]: {err_msg}")
            self.log_action(f"   경로: {filepath}")
            # ✅ 저장 실패 시 해시를 갱신하지 않음 → 다음 폴링에서 자동 재시도
            if isinstance(last_save_err, PermissionError):
                self.status_lbl.configure(text="⚠ 저장 실패: 파일 접근 권한 오류", text_color="#e74c3c")
            else:
                self.status_lbl.configure(text=f"⚠ 저장 실패: {err_msg[:60]}", text_color="#e74c3c")
            self.bell()  # 시스템 경고음으로 실패 알림

    def destroy(self):
        self.running = False
        super().destroy()

# Fallback UI file dialog without PyQt dependency
def QFileDialog_fallback():
    from tkinter import filedialog
    return filedialog.askdirectory()

if __name__ == "__main__":
    app = ImageSaverApp()
    app.mainloop()
