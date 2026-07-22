"""语音播报服务 - 为老人提供语音提示和路线导航播报。"""

try:
    from plyer import tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False


class VoiceService:
    """文字转语音服务，用于语音播报提示和路线导航。"""

    def __init__(self):
        self._enabled = True

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value

    def speak(self, text):
        """播报指定文本。"""
        if not self._enabled or not HAS_TTS:
            return
        if not text:
            return
        try:
            tts.speak(message=text)
        except Exception:
            pass

    # ---- 守护状态 ----

    def speak_start(self):
        self.speak("安全守护已开启，请随身携带手机")

    def speak_stop(self):
        self.speak("安全守护已关闭")

    def speak_home_set(self):
        self.speak("家的位置已设置成功")

    # ---- 告警 ----

    def speak_warning_distance(self):
        self.speak("请注意，您已离家过远，正在通知家人")

    def speak_warning_time(self):
        self.speak("请注意，您已外出较长时间，正在通知家人")

    def speak_warning_route(self):
        self.speak("请注意，您已偏离预设路线，正在通知家人")

    # ---- 路线导航 ----

    def speak_navigation(self, nav):
        """根据导航指引播报。"""
        if nav and nav.get("should_announce") and nav.get("instruction_text"):
            self.speak(nav["instruction_text"])

    def speak_route_start(self):
        """开始路线导航。"""
        self.speak("路线导航已开启，请按语音提示行走")

    def speak_route_end(self):
        self.speak("路线导航已结束")
