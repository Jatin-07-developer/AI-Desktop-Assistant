import sys
import os
import webbrowser
import datetime
import threading

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from config import apikey
except ImportError:
    apikey = os.getenv("OPENAI_API_KEY", "")

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF
from PyQt5.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QLinearGradient,
    QRadialGradient, QPainterPath
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QTextEdit, QLineEdit,
    QSizePolicy, QMessageBox
)


# ============================================================
# JARVIS CONFIG
# ============================================================

OPENAI_MODEL = "gpt-5.5"


# ============================================================
# TEXT TO SPEECH
# ============================================================

class Speaker:
    def __init__(self):
        self.engine = None
        if pyttsx3:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", 175)
            except Exception:
                self.engine = None

    def say(self, text):
        if not text:
            return

        def speak():
            try:
                if self.engine:
                    self.engine.say(text)
                    self.engine.runAndWait()
                elif sys.platform == "win32":
                    # Windows fallback: built-in PowerShell speech
                    safe = text.replace("'", "''")[:1500]
                    command = (
                        "Add-Type -AssemblyName System.Speech; "
                        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Speak('{safe}')"
                    )
                    os.system(f'powershell -NoProfile -Command "{command}"')
                elif sys.platform == "darwin":
                    os.system(f'say "{text.replace(chr(34), chr(39))}"')
                else:
                    os.system(f'espeak "{text.replace(chr(34), chr(39))}"')
            except Exception:
                pass

        threading.Thread(target=speak, daemon=True).start()


# ============================================================
# JARVIS CORE
# ============================================================

class JarvisCore:
    def __init__(self):
        self.chat_history = []

    def ask_ai(self, query):
        if not OpenAI:
            return "OpenAI package is not installed. Run: pip install openai"

        if not apikey:
            return "OpenAI API key is missing. Put apikey in config.py."

        try:
            client = OpenAI(api_key=apikey)

            self.chat_history.append({
                "role": "user",
                "content": query
            })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are JARVIS, a concise and intelligent AI assistant. "
                        "Address the user politely as Sir. Give useful answers "
                        "without unnecessary repetition."
                    )
                }
            ] + self.chat_history[-12:]

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages
            )

            answer = response.choices[0].message.content or "I have nothing to report, Sir."

            self.chat_history.append({
                "role": "assistant",
                "content": answer
            })

            return answer

        except Exception as e:
            return f"OpenAI connection error: {e}"

    def reset_chat(self):
        self.chat_history.clear()

    def execute_command(self, query):
        q = query.lower().strip()

        if "open youtube" in q:
            webbrowser.open("https://www.youtube.com")
            return "Opening YouTube, Sir."

        if "open wikipedia" in q:
            webbrowser.open("https://www.wikipedia.org")
            return "Opening Wikipedia, Sir."

        if "open google" in q:
            webbrowser.open("https://www.google.com")
            return "Opening Google, Sir."

        if "open github" in q:
            webbrowser.open("https://github.com")
            return "Opening GitHub, Sir."

        if "the time" in q or q == "time" or "what time" in q:
            now = datetime.datetime.now().strftime("%I:%M %p")
            return f"Sir, the time is {now}."

        if "open music" in q or "play music" in q:
            music_paths = [
                os.path.expanduser("~/Downloads/downfall-21371.mp3"),
                os.path.expanduser("~/Music/downfall-21371.mp3"),
            ]

            for path in music_paths:
                if os.path.exists(path):
                    if sys.platform == "win32":
                        os.startfile(path)
                    elif sys.platform == "darwin":
                        os.system(f'open "{path}"')
                    else:
                        os.system(f'xdg-open "{path}"')
                    return "Playing your music, Sir."

            return "I could not find the music file in your Downloads or Music folder."

        if "open notepad" in q:
            if sys.platform == "win32":
                os.system("start notepad")
            elif sys.platform == "darwin":
                os.system("open -a TextEdit")
            else:
                os.system("gedit >/dev/null 2>&1 &")
            return "Opening the text editor, Sir."

        if "open calculator" in q:
            if sys.platform == "win32":
                os.system("start calc")
            elif sys.platform == "darwin":
                os.system("open -a Calculator")
            else:
                os.system("gnome-calculator >/dev/null 2>&1 &")
            return "Opening calculator, Sir."

        if "reset chat" in q:
            self.reset_chat()
            return "Conversation memory has been reset, Sir."

        if "jarvis quit" in q or q == "quit jarvis" or q == "exit jarvis":
            return "__QUIT__"

        return None


# ============================================================
# VOICE THREAD
# ============================================================

class VoiceWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def run(self):
        if sr is None:
            self.error.emit(
                "SpeechRecognition is not installed.\n"
                "Run: pip install SpeechRecognition PyAudio"
            )
            return

        try:
            recognizer = sr.Recognizer()

            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=7, phrase_time_limit=12)

            query = recognizer.recognize_google(audio, language="en-in")
            self.result.emit(query)

        except sr.WaitTimeoutError:
            self.error.emit("I did not hear anything, Sir.")
        except sr.UnknownValueError:
            self.error.emit("I could not understand that, Sir.")
        except Exception as e:
            self.error.emit(f"Microphone error: {e}")


# ============================================================
# AI THREAD
# ============================================================

class AIWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, core, query):
        super().__init__()
        self.core = core
        self.query = query

    def run(self):
        command_result = self.core.execute_command(self.query)

        if command_result is not None:
            self.finished.emit(command_result)
        else:
            self.finished.emit(self.core.ask_ai(self.query))


# ============================================================
# ARC REACTOR WIDGET
# ============================================================

class ReactorWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.phase = 0
        self.listening = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)

    def animate(self):
        self.phase += 2
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        radius = min(w, h) * 0.30

        # Outer glow
        for glow_radius, alpha in [
            (radius * 1.55, 18),
            (radius * 1.35, 28),
            (radius * 1.15, 38),
        ]:
            gradient = QRadialGradient(cx, cy, glow_radius)
            gradient.setColorAt(0, QColor(0, 210, 255, alpha))
            gradient.setColorAt(0.55, QColor(0, 130, 255, alpha // 2))
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(cx - glow_radius, cy - glow_radius,
                       glow_radius * 2, glow_radius * 2)
            )

        # Rotating rings
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.phase * 0.35)

        for r, width, gap in [
            (radius * 1.48, 2, 40),
            (radius * 1.30, 3, 60),
            (radius * 1.10, 2, 25),
        ]:
            pen = QPen(QColor(0, 205, 255, 180), width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            for start in range(0, 360, gap + 15):
                painter.drawArc(
                    QRectF(-r, -r, 2 * r, 2 * r),
                    start * 16,
                    gap * 16
                )

        painter.restore()

        # Main reactor
        core_gradient = QRadialGradient(cx, cy, radius)
        core_gradient.setColorAt(0, QColor(255, 255, 255))
        core_gradient.setColorAt(0.15, QColor(140, 240, 255))
        core_gradient.setColorAt(0.40, QColor(0, 180, 255))
        core_gradient.setColorAt(0.72, QColor(0, 55, 110))
        core_gradient.setColorAt(1, QColor(0, 10, 25))

        painter.setBrush(QBrush(core_gradient))
        painter.setPen(QPen(QColor(70, 220, 255), 3))
        painter.drawEllipse(
            QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        )

        # Reactor segments
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.phase * 0.7)

        for i in range(12):
            painter.save()
            painter.rotate(i * 30)
            painter.setBrush(QColor(100, 235, 255, 230))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                QRectF(-5, -radius * 0.92, 10, radius * 0.25),
                4, 4
            )
            painter.restore()

        painter.restore()

        # Inner circle
        painter.setBrush(QColor(220, 250, 255))
        painter.setPen(QPen(QColor(0, 150, 255), 4))
        painter.drawEllipse(
            QRectF(cx - radius * .30, cy - radius * .30,
                   radius * .60, radius * .60)
        )

        # Center
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            QRectF(cx - radius * .12, cy - radius * .12,
                   radius * .24, radius * .24)
        )


# ============================================================
# MAIN WINDOW
# ============================================================

class JarvisWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.core = JarvisCore()
        self.speaker = Speaker()
        self.voice_worker = None
        self.ai_worker = None

        self.setWindowTitle("J.A.R.V.I.S — Just A Rather Very Intelligent System")
        self.setMinimumSize(1200, 760)
        self.resize(1450, 850)

        self.build_ui()
        self.start_clock()

        self.add_message(
            "JARVIS",
            "Good evening, Sir. All systems are online. How may I assist you?"
        )

    # ---------------- UI ----------------

    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        main = QVBoxLayout(root)
        main.setContentsMargins(18, 14, 18, 14)
        main.setSpacing(12)

        # Header
        header = QFrame()
        header.setObjectName("panel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 18, 10)

        logo = QLabel("◉")
        logo.setObjectName("reactorLogo")

        title_box = QVBoxLayout()
        title = QLabel("J.A.R.V.I.S")
        title.setObjectName("title")
        subtitle = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        subtitle.setObjectName("subtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.status = QLabel("●  SYSTEM ONLINE")
        self.status.setObjectName("status")

        self.clock = QLabel()
        self.clock.setObjectName("clock")

        header_layout.addWidget(logo)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        header_layout.addWidget(self.status)
        header_layout.addSpacing(30)
        header_layout.addWidget(self.clock)

        main.addWidget(header)

        # Body
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left panel
        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 16, 14, 16)
        left_layout.setSpacing(8)

        assistant = QLabel("◉  AI ASSISTANT\n\n"
                           "      ONLINE\n"
                           "      Voice Ready")
        assistant.setObjectName("assistantCard")
        left_layout.addWidget(assistant)

        left_layout.addWidget(self.section_label("NAVIGATION"))

        for text, action in [
            ("⌂   HOME", lambda: None),
            ("◎   WEB", lambda: self.submit_command("open google")),
            ("♫   MUSIC", lambda: self.submit_command("play music")),
            ("◷   TIME", lambda: self.submit_command("what is the time")),
            ("▦   APPS", lambda: self.submit_command("open calculator")),
        ]:
            btn = self.nav_button(text)
            btn.clicked.connect(action)
            left_layout.addWidget(btn)

        left_layout.addStretch()

        settings = self.nav_button("⚙   SETTINGS")
        settings.clicked.connect(self.show_settings)
        left_layout.addWidget(settings)

        # Center
        center = QFrame()
        center.setObjectName("centerPanel")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(10, 0, 10, 0)

        greeting = QLabel("GOOD EVENING, SIR")
        greeting.setObjectName("greeting")
        center_layout.addWidget(greeting)

        sub = QLabel("I AM <span style='color:#20d8ff;'>J.A.R.V.I.S</span> — "
                     "YOUR PERSONAL AI ASSISTANT")
        sub.setObjectName("greetingSub")
        sub.setTextFormat(Qt.RichText)
        center_layout.addWidget(sub)

        center_layout.addStretch()

        self.reactor = ReactorWidget()
        self.reactor.clicked.connect(self.start_listening)
        center_layout.addWidget(self.reactor, alignment=Qt.AlignCenter)

        self.listen_label = QLabel("CLICK THE REACTOR TO SPEAK")
        self.listen_label.setObjectName("listenLabel")
        self.listen_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.listen_label)

        # Quick commands
        quick = QFrame()
        quick.setObjectName("quickPanel")
        qlayout = QVBoxLayout(quick)
        qlayout.setContentsMargins(12, 10, 12, 10)

        qtitle = QLabel("QUICK COMMANDS")
        qtitle.setObjectName("panelTitle")
        qlayout.addWidget(qtitle)

        qrow = QHBoxLayout()
        commands = [
            ("YOUTUBE", "open youtube"),
            ("GOOGLE", "open google"),
            ("WIKIPEDIA", "open wikipedia"),
            ("TIME", "what is the time"),
            ("RESET", "reset chat"),
        ]

        for label, command in commands:
            btn = QPushButton(label)
            btn.setObjectName("quickButton")
            btn.clicked.connect(lambda checked=False, c=command: self.submit_command(c))
            qrow.addWidget(btn)

        qlayout.addLayout(qrow)
        center_layout.addWidget(quick)

        # Right console
        right = QFrame()
        right.setObjectName("panel")
        right.setMinimumWidth(390)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 14, 14, 14)

        console_title = QLabel("◈  JARVIS CONSOLE")
        console_title.setObjectName("panelTitle")
        right_layout.addWidget(console_title)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setObjectName("console")
        right_layout.addWidget(self.console)

        input_row = QHBoxLayout()

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Type your command...")
        self.command_input.setObjectName("commandInput")
        self.command_input.returnPressed.connect(self.send_typed_command)

        send_btn = QPushButton("➤")
        send_btn.setObjectName("sendButton")
        send_btn.setFixedWidth(55)
        send_btn.clicked.connect(self.send_typed_command)

        input_row.addWidget(self.command_input)
        input_row.addWidget(send_btn)
        right_layout.addLayout(input_row)

        body.addWidget(left)
        body.addWidget(center, 1)
        body.addWidget(right)

        main.addLayout(body, 1)

        # Footer
        footer = QLabel(
            "J.A.R.V.I.S v1.0   •   VOICE CONTROL ENABLED   •   "
            "OPENAI CORE CONNECTED"
        )
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignCenter)
        main.addWidget(footer)

        self.apply_styles()

    def section_label(self, text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def nav_button(self, text):
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCursor(Qt.PointingHandCursor)
        return button

    # ---------------- Clock ----------------

    def start_clock(self):
        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        self.update_clock()

    def update_clock(self):
        now = datetime.datetime.now()
        self.clock.setText(now.strftime("%a  %d %b %Y    %I:%M:%S %p"))

    # ---------------- Chat ----------------

    def add_message(self, sender, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if sender == "JARVIS":
            color = "#18d7ff"
        else:
            color = "#7dd3fc"

        html = (
            f"<div style='margin:7px 0;'>"
            f"<span style='color:#53657a;'>[{timestamp}]</span> "
            f"<b style='color:{color};'>{sender}</b>"
            f"<span style='color:#7890a5;'>  ›  </span>"
            f"<span style='color:#d9f4ff;'>{self.escape_html(message)}</span>"
            f"</div>"
        )

        self.console.append(html)
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def escape_html(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    # ---------------- Commands ----------------

    def send_typed_command(self):
        query = self.command_input.text().strip()

        if not query:
            return

        self.command_input.clear()
        self.submit_command(query)

    def submit_command(self, query):
        self.add_message("YOU", query)
        self.listen_label.setText("PROCESSING...")
        self.status.setText("●  PROCESSING")
        self.status.setObjectName("processingStatus")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

        self.ai_worker = AIWorker(self.core, query)
        self.ai_worker.finished.connect(self.handle_response)
        self.ai_worker.start()

    def handle_response(self, answer):
        if answer == "__QUIT__":
            self.speaker.say("Goodbye, Sir.")
            QApplication.quit()
            return

        self.add_message("JARVIS", answer)
        self.speaker.say(answer)

        self.listen_label.setText("CLICK THE REACTOR TO SPEAK")
        self.status.setText("●  SYSTEM ONLINE")
        self.status.setObjectName("status")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # ---------------- Voice ----------------

    def start_listening(self):
        if self.voice_worker and self.voice_worker.isRunning():
            return

        self.listen_label.setText("●  LISTENING...")
        self.status.setText("●  LISTENING")
        self.status.setObjectName("listeningStatus")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

        self.voice_worker = VoiceWorker()
        self.voice_worker.result.connect(self.voice_received)
        self.voice_worker.error.connect(self.voice_error)
        self.voice_worker.start()

    def voice_received(self, query):
        self.add_message("YOU", query)
        self.listen_label.setText("COMMAND RECEIVED...")
        self.submit_command_without_duplicate(query)

    def submit_command_without_duplicate(self, query):
        self.ai_worker = AIWorker(self.core, query)
        self.ai_worker.finished.connect(self.handle_response)
        self.ai_worker.start()

    def voice_error(self, error):
        self.add_message("JARVIS", error)
        self.speaker.say(error)
        self.listen_label.setText("CLICK THE REACTOR TO SPEAK")
        self.status.setText("●  SYSTEM ONLINE")
        self.status.setObjectName("status")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def show_settings(self):
        QMessageBox.information(
            self,
            "JARVIS Settings",
            "JARVIS is using:\n\n"
            f"AI Model: {OPENAI_MODEL}\n"
            "Voice: SpeechRecognition\n"
            "TTS: pyttsx3 / system fallback\n\n"
            "Edit OPENAI_MODEL at the top of jarvis_gui.py if needed."
        )

    # ---------------- Styling ----------------

    def apply_styles(self):
        self.setStyleSheet("""
        * {
            font-family: "Segoe UI", Arial, sans-serif;
        }

        #root {
            background:
                qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #020817,
                    stop:0.45 #061425,
                    stop:1 #02050d
                );
        }

        #panel, #quickPanel {
            background: rgba(3, 16, 31, 245);
            border: 1px solid #0b75a8;
            border-radius: 12px;
        }

        #centerPanel {
            background: transparent;
            border: none;
        }

        #reactorLogo {
            color: #21dcff;
            font-size: 30px;
            border: 2px solid #0ebcf0;
            border-radius: 22px;
            padding: 2px 8px;
        }

        #title {
            color: #e5faff;
            font-size: 27px;
            font-weight: 800;
            letter-spacing: 7px;
        }

        #subtitle {
            color: #3aa8cc;
            font-size: 9px;
            letter-spacing: 3px;
        }

        #status {
            color: #22e6a5;
            font-size: 11px;
            font-weight: 700;
        }

        #processingStatus {
            color: #ffd166;
            font-size: 11px;
            font-weight: 700;
        }

        #listeningStatus {
            color: #19dfff;
            font-size: 11px;
            font-weight: 700;
        }

        #clock {
            color: #82cde7;
            font-size: 11px;
        }

        #assistantCard {
            color: #9beaff;
            background: #061d31;
            border: 1px solid #0c91c9;
            border-radius: 9px;
            padding: 15px;
            font-size: 12px;
            line-height: 150%;
        }

        #sectionLabel {
            color: #3e8da9;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 2px;
            padding-top: 8px;
        }

        #navButton {
            text-align: left;
            color: #7ebbd1;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 11px 12px;
            font-size: 11px;
        }

        #navButton:hover {
            color: #e5fbff;
            background: #07304a;
            border: 1px solid #0da9df;
        }

        #greeting {
            color: #e7fbff;
            font-size: 31px;
            font-weight: 700;
            letter-spacing: 2px;
            padding-top: 5px;
        }

        #greetingSub {
            color: #6799ad;
            font-size: 11px;
            letter-spacing: 2px;
        }

        #listenLabel {
            color: #31dfff;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 3px;
            padding-bottom: 8px;
        }

        #panelTitle {
            color: #31dfff;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 2px;
        }

        #quickPanel {
            background: rgba(4, 22, 38, 230);
        }

        #quickButton {
            color: #8bd9ef;
            background: #061a2a;
            border: 1px solid #0a719a;
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 9px;
            font-weight: 700;
        }

        #quickButton:hover {
            color: white;
            background: #073957;
            border: 1px solid #16d5ff;
        }

        #console {
            background: #010914;
            color: #ccefff;
            border: 1px solid #083e5c;
            border-radius: 7px;
            padding: 9px;
            font-family: Consolas, "Courier New", monospace;
            font-size: 11px;
        }

        #commandInput {
            background: #031321;
            color: #e5faff;
            border: 1px solid #0b739c;
            border-radius: 7px;
            padding: 11px;
            font-size: 11px;
        }

        #commandInput:focus {
            border: 1px solid #16d9ff;
        }

        #sendButton {
            color: #05131e;
            background: #16d9ff;
            border: none;
            border-radius: 7px;
            font-size: 18px;
            font-weight: bold;
        }

        #sendButton:hover {
            background: #6beaff;
        }

        #footer {
            color: #315c70;
            font-size: 8px;
            letter-spacing: 2px;
            padding: 4px;
        }

        QScrollBar:vertical {
            background: #020a12;
            width: 7px;
            border-radius: 3px;
        }

        QScrollBar::handle:vertical {
            background: #0c7197;
            border-radius: 3px;
        }
        """)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")

    window = JarvisWindow()
    window.show()

    sys.exit(app.exec_())