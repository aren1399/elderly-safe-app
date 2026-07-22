"""老年防走失安全守护 - 主程序入口。"""

import threading
import time
from functools import partial

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen, ScreenManager

from services.gps_service import GPSService
from services.geofence_service import GeofenceService
from services.alert_service import AlertService
from services.voice_service import VoiceService
from utils.config_manager import load_config, save_config, update_config
from utils.landmark import format_location_description


class MainScreen(Screen):
    """主页面 - 守护开启/关闭。"""

    def start_guard(self):
        app = App.get_running_app()
        app.start_guard()

    def stop_guard(self):
        app = App.get_running_app()
        app.stop_guard()

    def go_settings(self):
        self.manager.current = "settings"


class SettingsScreen(Screen):
    """设置页面 - 配置家位置、联系人、安全参数。"""

    def on_enter(self):
        """进入页面时加载当前配置。"""
        app = App.get_running_app()
        cfg = load_config()

        if cfg.get("home_address"):
            self.ids.home_address_label.text = cfg["home_address"]
        else:
            self.ids.home_address_label.text = "未设置 — 请点击下方按钮设置"

        contacts = cfg.get("emergency_contacts", [])
        if contacts:
            self.ids.contacts_label.text = "\n".join(contacts)
        else:
            self.ids.contacts_label.text = "未设置联系人"

        routes = cfg.get("preset_routes", [])
        if routes:
            lines = [f"{i+1}. {desc} ({lat:.5f},{lon:.5f})"
                     for i, (lat, lon, desc) in enumerate(routes)]
            self.ids.route_label.text = "\n".join(lines)
        else:
            self.ids.route_label.text = "未设置路线"

        self.ids.distance_slider.value = cfg.get("max_distance_meters", 500)
        self.ids.time_slider.value = cfg.get("max_time_minutes", 60)
        self.ids.voice_switch.active = cfg.get("voice_enabled", True)

        self._update_slider_labels()

    def _update_slider_labels(self):
        dist = int(self.ids.distance_slider.value)
        self.ids.distance_label.text = f"{dist} 米"
        mins = int(self.ids.time_slider.value)
        self.ids.time_label.text = f"{mins} 分钟"

    def on_distance_slider(self, *args):
        self._update_slider_labels()

    def on_time_slider(self, *args):
        self._update_slider_labels()

    def set_home_location(self):
        """使用当前 GPS 位置设置家的位置。"""
        app = App.get_running_app()
        latest = app.gps_service.latest
        if latest and latest.get("lat") and latest.get("lon"):
            cfg = load_config()
            cfg["home_lat"] = latest["lat"]
            cfg["home_lon"] = latest["lon"]
            cfg["home_address"] = f"纬度 {latest['lat']:.5f}, 经度 {latest['lon']:.5f}"
            cfg["first_launch"] = False
            save_config(cfg)
            self.ids.home_address_label.text = cfg["home_address"]
            app.voice_service.speak_home_set()
            app._configure_geofence()
        else:
            self.ids.home_address_label.text = "GPS 还未获取到位置，请稍后再试"

    def add_contact(self, phone):
        """添加紧急联系人。"""
        phone = phone.strip()
        if not phone:
            return
        if len(phone) < 11 or not phone.isdigit():
            self.ids.contacts_label.text = "请输入正确的手机号码"
            return

        cfg = load_config()
        contacts = cfg.get("emergency_contacts", [])
        if phone not in contacts:
            contacts.append(phone)
            cfg["emergency_contacts"] = contacts
            save_config(cfg)
        self.ids.contacts_label.text = "\n".join(contacts)
        self.ids.phone_input.text = ""

    def add_route_point(self):
        """添加当前 GPS 位置为路线途经点（由家人边走边设置）。"""
        app = App.get_running_app()
        latest = app.gps_service.latest
        if not latest or latest.get("lat") is None:
            self.ids.route_label.text = "GPS 还未获取到位置，请稍后再试"
            return

        cfg = load_config()
        routes = cfg.get("preset_routes", [])
        idx = len(routes) + 1
        desc = f"途经点{idx}"

        # 逆地理编码获取描述（后台线程，先用坐标显示）
        routes.append((latest["lat"], latest["lon"], desc))
        cfg["preset_routes"] = routes
        save_config(cfg)

        app._configure_geofence()

        lines = [f"{i+1}. {d} ({lt:.5f},{ln:.5f})"
                 for i, (lt, ln, d) in enumerate(routes)]
        self.ids.route_label.text = "\n".join(lines)
        app.voice_service.speak(f"已添加{desc}")

        # 后台获取地址描述并更新路线点名称
        threading.Thread(
            target=self._update_route_point_name,
            args=(idx - 1, latest["lat"], latest["lon"]),
            daemon=True,
        ).start()

    def _update_route_point_name(self, index, lat, lon):
        """后台获取途经点的地址描述。"""
        try:
            from utils.landmark import reverse_geocode
            geo = reverse_geocode(lat, lon)
            name = geo.get("road", "") or geo.get("building", "") or f"途经点{index+1}"
            if geo.get("suburb"):
                name = geo["suburb"] + name
        except Exception:
            name = f"途经点{index+1}"

        cfg = load_config()
        routes = cfg.get("preset_routes", [])
        if index < len(routes):
            routes[index] = (routes[index][0], routes[index][1], name)
            cfg["preset_routes"] = routes
            save_config(cfg)

            def update_ui(dt):
                lines = [f"{i+1}. {d} ({lt:.5f},{ln:.5f})"
                         for i, (lt, ln, d) in enumerate(routes)]
                self.ids.route_label.text = "\n".join(lines)
            Clock.schedule_once(update_ui)

    def clear_route(self):
        """清空所有预设路线。"""
        cfg = load_config()
        cfg["preset_routes"] = []
        save_config(cfg)
        self.ids.route_label.text = "未设置路线"
        App.get_running_app().geofence_service.clear_routes()
        App.get_running_app()._configure_geofence()
        App.get_running_app().voice_service.speak("路线已清空")

    def save_and_back(self):
        """保存设置并返回主页面。"""
        cfg = load_config()
        cfg["max_distance_meters"] = int(self.ids.distance_slider.value)
        cfg["max_time_minutes"] = int(self.ids.time_slider.value)
        cfg["voice_enabled"] = self.ids.voice_switch.active
        save_config(cfg)

        app = App.get_running_app()
        app.voice_service.enabled = cfg["voice_enabled"]
        app._configure_geofence()
        self.manager.current = "main"


class AlertScreen(Screen):
    """告警页面 - 异常时显示。"""

    def populate(self, alert_type, detail, contacts):
        """填充告警信息并添加联系人按钮。"""
        app = App.get_running_app()

        type_text = {
            "distance": "老人已离家过远！",
            "time": "老人外出时间过长！",
            "route": "老人已偏离路线！",
        }.get(alert_type, "需要关注老人安全！")

        self.ids.alert_title.text = f"⚠️ {type_text}"
        msg_lines = []
        if "distance_to_home" in detail:
            msg_lines.append(f"当前离家约 {detail['distance_to_home']} 米")
        if "away_minutes" in detail:
            msg_lines.append(f"已外出约 {detail['away_minutes']} 分钟")
        self.ids.alert_message.text = "\n".join(msg_lines)

        # 开启后台获取地标信息
        latest = app.gps_service.latest
        if latest and latest.get("lat"):
            threading.Thread(
                target=self._fetch_location_info,
                args=(latest["lat"], latest["lon"]),
                daemon=True,
            ).start()

        # 动态添加联系人拨打按钮
        container = self.ids.contact_buttons
        container.clear_widgets()
        for phone in contacts:
            btn = Button(
                text=f"📞 呼叫 {phone}",
                font_size="24sp",
                bold=True,
                size_hint=(0.85, None),
                height="80dp",
                pos_hint={"center_x": 0.5},
                background_normal="",
                background_color=(0.2, 0.6, 0.9, 1),
                color=(1, 1, 1, 1),
            )
            btn.bind(on_press=partial(self._make_call, phone))
            container.add_widget(btn)

        # 发送短信告警
        threading.Thread(
            target=self._send_alerts,
            args=(alert_type, detail, contacts),
            daemon=True,
        ).start()

    def _fetch_location_info(self, lat, lon):
        """后台获取位置描述和地标信息。"""
        try:
            desc = format_location_description(lat, lon)
            Clock.schedule_once(
                lambda dt: setattr(self.ids.alert_location, "text", desc)
            )
        except Exception:
            Clock.schedule_once(
                lambda dt: setattr(
                    self.ids.alert_location,
                    "text",
                    f"坐标：{lat:.6f}, {lon:.6f}",
                )
            )

    def _send_alerts(self, alert_type, detail, contacts):
        """后台发送短信告警。"""
        app = App.get_running_app()
        latest = app.gps_service.latest
        if not latest or not latest.get("lat"):
            return

        try:
            desc = format_location_description(latest["lat"], latest["lon"])
        except Exception:
            desc = f"坐标：{latest['lat']:.6f}, {latest['lon']:.6f}"

        app.alert_service.send_alert(contacts, alert_type, detail, desc)

    def _make_call(self, phone, instance):
        """拨打指定电话。"""
        App.get_running_app().alert_service.make_call(phone)

    def dismiss_alert(self):
        """关闭告警，返回主页面。"""
        self.manager.current = "main"


class ElderlySafeApp(App):
    """老年防走失安全守护应用。"""

    def build(self):
        self.title = "安全守护"
        self.icon = "icon.png"

        # 初始化服务
        self.gps_service = GPSService()
        self.geofence_service = GeofenceService()
        self.alert_service = AlertService()
        self.voice_service = VoiceService()

        # 状态
        self._guard_active = False
        self._gps_ready = False
        self._monitor_event = None
        self._alert_in_progress = False
        self._periodic_voice_last = 0
        self._nav_info = None  # 当前导航信息

        # 加载配置
        self._load_and_apply_config()

        # 屏幕管理
        self.sm = ScreenManager()
        self.sm.add_widget(MainScreen(name="main"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        self.sm.add_widget(AlertScreen(name="alert"))

        # 初始化 GPS
        self._init_gps()

        return self.sm

    def _load_and_apply_config(self):
        cfg = load_config()
        self.voice_service.enabled = cfg.get("voice_enabled", True)
        self._configure_geofence()

    def _configure_geofence(self):
        cfg = load_config()
        home_lat = cfg.get("home_lat")
        home_lon = cfg.get("home_lon")
        if home_lat is not None and home_lon is not None:
            self.geofence_service.configure(
                home_lat=home_lat,
                home_lon=home_lon,
                max_distance_m=cfg.get("max_distance_meters", 500),
                max_time_min=cfg.get("max_time_minutes", 60),
                preset_routes=cfg.get("preset_routes", []),
            )

    def _init_gps(self):
        """初始化 GPS，开始获取位置。"""
        success = self.gps_service.start(
            callback=self._on_gps_update, min_time=8000, min_distance=5
        )
        if not success:
            Clock.schedule_once(lambda dt: self._show_gps_error(), 2)

    def _on_gps_update(self, location):
        """GPS 位置更新回调。"""
        if not location or location.get("lat") is None:
            return

        self._gps_ready = True
        cfg = load_config()

        # 首次启动自动设置家位置
        if cfg.get("first_launch") and cfg.get("home_lat") is None:
            cfg["home_lat"] = location["lat"]
            cfg["home_lon"] = location["lon"]
            cfg["home_address"] = f"纬度 {location['lat']:.5f}, 经度 {location['lon']:.5f}"
            cfg["first_launch"] = False
            save_config(cfg)
            self._configure_geofence()
            self.voice_service.speak("首次使用，已将当前位置设为家的位置")

        if not self._guard_active:
            return

        # 定期更新主页状态
        Clock.schedule_once(lambda dt: self._update_main_status(location))

    def _update_main_status(self, location):
        """更新主页面状态显示。"""
        main_screen = self.sm.get_screen("main")
        if not main_screen:
            return

        lat = location.get("lat", "---")
        lon = location.get("lon", "---")

        cfg = load_config()
        home_lat = cfg.get("home_lat")
        home_lon = cfg.get("home_lon")

        status = "🟢 守护中"
        info = f"位置：{lat:.5f}, {lon:.5f}"

        if home_lat and home_lon:
            from services.geofence_service import _haversine

            dist = _haversine(home_lat, home_lon, lat, lon)
            info += f"\n离家约 {dist:.0f} 米"

        # 如果正在导航，显示路线信息
        if self._nav_info:
            nav = self._nav_info
            info += f"\n🗺 下一站: {nav['next_waypoint_desc']}"
            info += f"\n距离: {nav['distance_to_next']:.0f} 米 ({nav['bearing_direction']})"
            if nav.get("total_remaining"):
                info += f"\n剩余全程: {nav['total_remaining']:.0f} 米"

        main_screen.ids.status_label.text = status
        main_screen.ids.info_label.text = info

    def start_guard(self):
        """开启安全守护。"""
        cfg = load_config()
        if cfg.get("home_lat") is None:
            self._toast("请先在设置中设置家的位置")
            return
        if not cfg.get("emergency_contacts"):
            self._toast("请先在设置中添加紧急联系人")
            return

        self._guard_active = True
        self._alert_in_progress = False
        self._gps_ready = self.gps_service.latest is not None

        # 重置状态
        self.geofence_service.reset_alerts()
        self.alert_service.clear_sent_cache()
        self._configure_geofence()

        # 更新 UI
        main_screen = self.sm.get_screen("main")
        main_screen.ids.start_btn.disabled = True
        main_screen.ids.start_btn.opacity = 0.4
        main_screen.ids.stop_btn.disabled = False
        main_screen.ids.stop_btn.opacity = 1
        main_screen.ids.status_label.text = "🔄 正在获取位置..."
        main_screen.ids.info_label.text = ""

        # 语音播报
        self.voice_service.speak_start()

        # 有预设路线时开启导航语音
        if self.geofence_service.has_route:
            self.voice_service.speak_route_start()

        # 启动监控定时器（每 8 秒检查一次）
        self._monitor_event = Clock.schedule_interval(self._monitor_tick, 8)

    def stop_guard(self):
        """关闭安全守护。"""
        self._guard_active = False

        if self._monitor_event:
            self._monitor_event.cancel()
            self._monitor_event = None

        # 更新 UI
        main_screen = self.sm.get_screen("main")
        main_screen.ids.start_btn.disabled = False
        main_screen.ids.start_btn.opacity = 1
        main_screen.ids.stop_btn.disabled = True
        main_screen.ids.stop_btn.opacity = 0.4
        main_screen.ids.status_label.text = "未开启守护\n\n请点击下方按钮开始"
        main_screen.ids.info_label.text = ""

        if self.geofence_service.has_route:
            self.voice_service.speak_route_end()
        self.voice_service.speak_stop()
        self._nav_info = None

    def _monitor_tick(self, dt):
        """定时监控检查（Clock 回调，运行在主线程）。"""
        if not self._guard_active or self._alert_in_progress:
            return

        latest = self.gps_service.latest
        if not latest or latest.get("lat") is None:
            return

        lat, lon = latest["lat"], latest["lon"]
        is_safe, alert_type, detail = self.geofence_service.check(lat, lon)

        # 路线导航指引
        self._nav_info = None
        if self.geofence_service.has_route:
            nav = self.geofence_service.get_navigation(lat, lon)
            if nav:
                self._nav_info = nav
                # 语音播报导航（在单独的短暂延时后播报，避免与告警冲突）
                if nav.get("should_announce"):
                    self.voice_service.speak_navigation(nav)

        # 更新 UI
        self._update_main_status(latest)

        if not is_safe:
            self._trigger_alert(alert_type, detail)

    def _trigger_alert(self, alert_type, detail):
        """触发告警流程。"""
        self._alert_in_progress = True

        cfg = load_config()
        contacts = cfg.get("emergency_contacts", [])

        # 语音播报
        voice_method = {
            "distance": self.voice_service.speak_warning_distance,
            "time": self.voice_service.speak_warning_time,
            "route": self.voice_service.speak_warning_route,
        }.get(alert_type)
        if voice_method:
            voice_method()

        # 切换到告警页面
        alert_screen = self.sm.get_screen("alert")
        alert_screen.populate(alert_type, detail, contacts)
        self.sm.current = "alert"

    def _show_gps_error(self):
        main = self.sm.get_screen("main")
        if main:
            main.ids.status_label.text = "⚠️ GPS 不可用\n请确认已开启定位服务"

    def _toast(self, message):
        """简易提示（通过语音播报 + 状态栏）。"""
        self.voice_service.speak(message)
        main_screen = self.sm.get_screen("main")
        if main_screen:
            main_screen.ids.info_label.text = message

    def on_stop(self):
        """应用退出时清理。"""
        self.gps_service.stop()


if __name__ == "__main__":
    ElderlySafeApp().run()
