"""最小化测试应用 - 验证基础编译链是否正常。"""
import traceback
import sys
import os

# 记录崩溃日志
import logging
logging.basicConfig(
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
)

def log_uncaught(exc_type, exc_value, exc_tb):
    logging.critical("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc_value, exc_tb))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log"), "a") as f:
        f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

sys.excepthook = log_uncaught

logging.info("App starting...")

try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen, ScreenManager
    logging.info("Kivy imports OK")
except Exception as e:
    logging.error(f"Kivy import failed: {e}")

try:
    from services.gps_service import GPSService
    logging.info("GPS import OK")
except Exception as e:
    logging.error(f"GPS import failed: {e}")

try:
    from services.voice_service import VoiceService
    logging.info("Voice import OK")
except Exception as e:
    logging.error(f"Voice import failed: {e}")

try:
    from services.alert_service import AlertService
    logging.info("Alert import OK")
except Exception as e:
    logging.error(f"Alert import failed: {e}")

try:
    from utils.config_manager import load_config
    logging.info("Config import OK")
except Exception as e:
    logging.error(f"Config import failed: {e}")


class TestScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = BoxLayout(orientation="vertical", padding=40, spacing=20)
        layout.add_widget(Label(
            text="安全守护\n测试模式",
            font_size="28sp", bold=True, halign="center"
        ))
        self._status = Label(text="正在检查...", font_size="20sp", halign="center")
        layout.add_widget(self._status)
        btn = Button(text="点击测试", font_size="30sp", bold=True,
                     size_hint=(1, 0.3))
        btn.bind(on_press=self.do_test)
        layout.add_widget(btn)
        self.add_widget(layout)

    def do_test(self, instance):
        msgs = []
        try:
            from plyer import gps
            msgs.append("plyer.gps OK")
        except Exception as e:
            msgs.append(f"plyer.gps: {e}")
        try:
            from plyer import tts
            msgs.append("plyer.tts OK")
        except Exception as e:
            msgs.append(f"plyer.tts: {e}")
        try:
            from jnius import autoclass
            autoclass("java.lang.System")
            msgs.append("jnius OK")
        except Exception as e:
            msgs.append(f"jnius: {e}")
        try:
            cfg = load_config()
            msgs.append(f"config loaded: {bool(cfg)}")
        except Exception as e:
            msgs.append(f"config: {e}")
        self._status.text = "\n".join(msgs)
        logging.info("Test results: " + str(msgs))


class TestApp(App):
    def build(self):
        try:
            logging.info("build() started")
            self.title = "安全守护测试"
            sm = ScreenManager()
            sm.add_widget(TestScreen(name="test"))
            logging.info("build() OK")
            return sm
        except Exception as e:
            logging.error(f"build() failed: {e}")
            return Label(text=f"启动失败: {e}", font_size="20sp")


if __name__ == "__main__":
    logging.info("Running TestApp...")
    TestApp().run()
