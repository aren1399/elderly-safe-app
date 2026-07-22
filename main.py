"""老年防走失安全守护 - 主程序入口。"""

import threading
from functools import partial

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen, ScreenManager

from utils.config_manager import load_config, save_config


class SafeApp(App):
    """安全守护应用 - 防崩溃启动架构。

    设计原则：UI 先渲染，硬件服务按需初始化。
    GPS/TTS/SMS 等需要运行时权限的服务不在 build() 中触发，
    改为用户点击「开始守护」时才启动。
    """

    def build(self):
        self.title = "安全守护"

        # 导入放在 build() 内，避免 import 异常导致闪退
        try:
            from services.gps_service import GPSService
            from services.geofence_service import GeofenceService
            from services.alert_service import AlertService
            from services.voice_service import VoiceService
            self.gps_service = GPSService()
            self.geofence_service = GeofenceService()
            self.alert_service = AlertService()
            self.voice_service = VoiceService()
            self._services_ok = True
        except Exception as e:
            self._services_ok = False
            self._init_error = str(e)

        self._guard_active = False
        self._gps_ready = False
        self._monitor_event = None
        self._alert_in_progress = False
        self._nav_info = None

        try:
            self._load_and_apply_config()
        except Exception:
            pass

        self.sm = ScreenManager()
        self.sm.add_widget(MainScreen(name="main"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        self.sm.add_widget(AlertScreen(name="alert"))

        # 延迟初始化 GPS（给 Android 权限弹窗时间）
        Clock.schedule_once(lambda dt: self._safe_init_gps(), 1)

        return self.sm

    def _safe_init_gps(self):
        """安全的 GPS 初始化 - 失败不影响 UI。"""
        if not self._services_ok:
            return
        try:
            self.gps_service.start(
                callback=self._on_gps_update, min_time=10000, min_distance=5
            )
        except Exception:
            pass

    def _load_and_apply_config(self):
        cfg = load_config()
        if self._services_ok:
            self.voice_service.enabled = cfg.get("voice_enabled", True)
        self._configure_geofence()

    def _configure_geofence(self):
        cfg = load_config()
        if not self._services_ok:
            return
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

    def _on_gps_update(self, location):
        if not location or location.get("lat") is None:
            return
        self._gps_ready = True
        try:
            cfg = load_config()
            if cfg.get("first_launch") and cfg.get("home_lat") is None:
                cfg["home_lat"] = location["lat"]
                cfg["home_lon"] = location["lon"]
                cfg["home_address"] = f"纬度 {location['lat']:.5f}, 经度 {location['lon']:.5f}"
                cfg["first_launch"] = False
                save_config(cfg)
                self._configure_geofence()
                Clock.schedule_once(lambda dt: self._speak_safe("首次使用，已将当前位置设为家的位置"))
        except Exception:
            pass
        if not self._guard_active:
            return
        Clock.schedule_once(lambda dt: self._update_main_status(location))

    def _update_main_status(self, location):
        main_screen = self.sm.get_screen("main")
        if not main_screen:
            return
        try:
            lat = location.get("lat")
            lon = location.get("lon")
            info = f"位置：{lat:.5f}, {lon:.5f}"
            cfg = load_config()
            home_lat = cfg.get("home_lat")
            home_lon = cfg.get("home_lon")
            if home_lat and home_lon:
                from services.geofence_service import _haversine
                dist = _haversine(home_lat, home_lon, lat, lon)
                info += f"\n离家约 {dist:.0f} 米"
            if self._nav_info:
                n = self._nav_info
                info += f"\n下一站: {n['next_waypoint_desc']}\n距离: {n['distance_to_next']:.0f} 米 ({n['bearing_direction']})"
                if n.get("total_remaining"):
                    info += f"\n剩余: {n['total_remaining']:.0f} 米"
            main_screen.ids.status_label.text = "守护中" if self._guard_active else "未开启守护\n\n请点击下方按钮开始"
            main_screen.ids.info_label.text = info
        except Exception:
            pass

    def start_guard(self):
        if not self._services_ok:
            self._toast("服务初始化失败，请重启应用")
            return
        try:
            cfg = load_config()
            if cfg.get("home_lat") is None:
                self._toast("请先在设置中设置家的位置")
                return
            if not cfg.get("emergency_contacts"):
                self._toast("请先在设置中添加紧急联系人")
                return
            self._guard_active = True
            self._alert_in_progress = False
            self.geofence_service.reset_alerts()
            self.alert_service.clear_sent_cache()
            self._configure_geofence()
            main_screen = self.sm.get_screen("main")
            main_screen.ids.start_btn.disabled = True
            main_screen.ids.start_btn.opacity = 0.4
            main_screen.ids.stop_btn.disabled = False
            main_screen.ids.stop_btn.opacity = 1
            main_screen.ids.status_label.text = "正在获取位置..."
            main_screen.ids.info_label.text = ""
            self._speak_safe("安全守护已开启，请随身携带手机")
            if self.geofence_service.has_route:
                self._speak_safe("路线导航已开启，请按语音提示行走")
            self._monitor_event = Clock.schedule_interval(self._monitor_tick, 8)
        except Exception as e:
            self._toast(f"启动失败: {e}")

    def stop_guard(self):
        self._guard_active = False
        if self._monitor_event:
            self._monitor_event.cancel()
            self._monitor_event = None
        main_screen = self.sm.get_screen("main")
        main_screen.ids.start_btn.disabled = False
        main_screen.ids.start_btn.opacity = 1
        main_screen.ids.stop_btn.disabled = True
        main_screen.ids.stop_btn.opacity = 0.4
        main_screen.ids.status_label.text = "未开启守护\n\n请点击下方按钮开始"
        main_screen.ids.info_label.text = ""
        if self._services_ok and self.geofence_service.has_route:
            self._speak_safe("路线导航已结束")
        self._speak_safe("安全守护已关闭")
        self._nav_info = None

    def _monitor_tick(self, dt):
        if not self._guard_active or self._alert_in_progress:
            return
        try:
            latest = self.gps_service.latest
            if not latest or latest.get("lat") is None:
                return
            lat, lon = latest["lat"], latest["lon"]
            is_safe, alert_type, detail = self.geofence_service.check(lat, lon)
            self._nav_info = None
            if self.geofence_service.has_route:
                nav = self.geofence_service.get_navigation(lat, lon)
                if nav:
                    self._nav_info = nav
                    if nav.get("should_announce"):
                        self.voice_service.speak_navigation(nav)
            self._update_main_status(latest)
            if not is_safe:
                self._trigger_alert(alert_type, detail)
        except Exception:
            pass

    def _trigger_alert(self, alert_type, detail):
        self._alert_in_progress = True
        try:
            cfg = load_config()
            contacts = cfg.get("emergency_contacts", [])
            voice_map = {
                "distance": self.voice_service.speak_warning_distance,
                "time": self.voice_service.speak_warning_time,
                "route": self.voice_service.speak_warning_route,
            }
            fn = voice_map.get(alert_type)
            if fn:
                fn()
            alert_screen = self.sm.get_screen("alert")
            alert_screen.populate(alert_type, detail, contacts)
            self.sm.current = "alert"
        except Exception:
            pass

    def _speak_safe(self, text):
        try:
            if self._services_ok:
                self.voice_service.speak(text)
        except Exception:
            pass

    def _toast(self, message):
        self._speak_safe(message)
        try:
            main_screen = self.sm.get_screen("main")
            if main_screen:
                main_screen.ids.info_label.text = message
        except Exception:
            pass

    def on_stop(self):
        try:
            if self._services_ok:
                self.gps_service.stop()
        except Exception:
            pass


class MainScreen(Screen):
    def start_guard(self):
        App.get_running_app().start_guard()
    def stop_guard(self):
        App.get_running_app().stop_guard()
    def go_settings(self):
        self.manager.current = "settings"


class SettingsScreen(Screen):
    def on_enter(self):
        try:
            self._refresh()
        except Exception:
            pass

    def _refresh(self):
        app = App.get_running_app()
        cfg = load_config()
        self.ids.home_address_label.text = cfg.get("home_address") or "未设置 — 请点击下方按钮设置"
        contacts = cfg.get("emergency_contacts", [])
        self.ids.contacts_label.text = "\n".join(contacts) if contacts else "未设置联系人"
        routes = cfg.get("preset_routes", [])
        if routes:
            lines = [f"{i+1}. {d} ({lt:.5f},{ln:.5f})" for i, (lt, ln, d) in enumerate(routes)]
            self.ids.route_label.text = "\n".join(lines)
        else:
            self.ids.route_label.text = "未设置路线"
        self.ids.distance_slider.value = cfg.get("max_distance_meters", 500)
        self.ids.time_slider.value = cfg.get("max_time_minutes", 60)
        self.ids.voice_switch.active = cfg.get("voice_enabled", True)

    def _update_slider_labels(self):
        self.ids.distance_label.text = f"{int(self.ids.distance_slider.value)} 米"
        self.ids.time_label.text = f"{int(self.ids.time_slider.value)} 分钟"

    def on_distance_slider(self, *args):
        self._update_slider_labels()
    def on_time_slider(self, *args):
        self._update_slider_labels()

    def set_home_location(self):
        app = App.get_running_app()
        if not app._services_ok:
            self.ids.home_address_label.text = "服务未就绪，请稍后重试"
            return
        latest = app.gps_service.latest
        if not latest or latest.get("lat") is None:
            self.ids.home_address_label.text = "GPS 还未获取到位置，请稍后再试"
            return
        try:
            cfg = load_config()
            cfg["home_lat"] = latest["lat"]
            cfg["home_lon"] = latest["lon"]
            cfg["home_address"] = f"纬度 {latest['lat']:.5f}, 经度 {latest['lon']:.5f}"
            cfg["first_launch"] = False
            save_config(cfg)
            self.ids.home_address_label.text = cfg["home_address"]
            app._speak_safe("家的位置已设置成功")
            app._configure_geofence()
        except Exception:
            self.ids.home_address_label.text = "设置失败，请重试"

    def add_contact(self, phone):
        phone = phone.strip()
        if not phone or len(phone) < 11 or not phone.isdigit():
            self.ids.contacts_label.text = "请输入正确的手机号码"
            return
        try:
            cfg = load_config()
            contacts = cfg.get("emergency_contacts", [])
            if phone not in contacts:
                contacts.append(phone)
                cfg["emergency_contacts"] = contacts
                save_config(cfg)
            self.ids.contacts_label.text = "\n".join(contacts)
            self.ids.phone_input.text = ""
        except Exception:
            self.ids.contacts_label.text = "添加失败"

    def add_route_point(self):
        app = App.get_running_app()
        if not app._services_ok:
            self.ids.route_label.text = "服务未就绪"
            return
        latest = app.gps_service.latest
        if not latest or latest.get("lat") is None:
            self.ids.route_label.text = "GPS 还未获取到位置"
            return
        try:
            cfg = load_config()
            routes = cfg.get("preset_routes", [])
            idx = len(routes) + 1
            desc = f"途经点{idx}"
            routes.append((latest["lat"], latest["lon"], desc))
            cfg["preset_routes"] = routes
            save_config(cfg)
            app._configure_geofence()
            lines = [f"{i+1}. {d} ({lt:.5f},{ln:.5f})" for i, (lt, ln, d) in enumerate(routes)]
            self.ids.route_label.text = "\n".join(lines)
            app._speak_safe(f"已添加{desc}")
            threading.Thread(target=self._update_route_point_name, args=(idx - 1, latest["lat"], latest["lon"]), daemon=True).start()
        except Exception:
            self.ids.route_label.text = "添加失败"

    def _update_route_point_name(self, index, lat, lon):
        try:
            from utils.landmark import reverse_geocode
            geo = reverse_geocode(lat, lon)
            name = (geo.get("road") or geo.get("building") or f"途经点{index+1}")
            if geo.get("suburb"):
                name = geo["suburb"] + name
        except Exception:
            name = f"途经点{index+1}"
        try:
            cfg = load_config()
            routes = cfg.get("preset_routes", [])
            if index < len(routes):
                routes[index] = (routes[index][0], routes[index][1], name)
                cfg["preset_routes"] = routes
                save_config(cfg)
                Clock.schedule_once(lambda dt: self._refresh())
        except Exception:
            pass

    def clear_route(self):
        try:
            cfg = load_config()
            cfg["preset_routes"] = []
            save_config(cfg)
            self.ids.route_label.text = "未设置路线"
            app = App.get_running_app()
            if app._services_ok:
                app.geofence_service.clear_routes()
                app._configure_geofence()
                app._speak_safe("路线已清空")
        except Exception:
            pass

    def save_and_back(self):
        try:
            cfg = load_config()
            cfg["max_distance_meters"] = int(self.ids.distance_slider.value)
            cfg["max_time_minutes"] = int(self.ids.time_slider.value)
            cfg["voice_enabled"] = self.ids.voice_switch.active
            save_config(cfg)
            app = App.get_running_app()
            if app._services_ok:
                app.voice_service.enabled = cfg["voice_enabled"]
                app._configure_geofence()
        except Exception:
            pass
        self.manager.current = "main"


class AlertScreen(Screen):
    def populate(self, alert_type, detail, contacts):
        app = App.get_running_app()
        type_text = {
            "distance": "老人已离家过远！",
            "time": "老人外出时间过长！",
            "route": "老人已偏离路线！",
        }.get(alert_type, "需要关注老人安全！")
        self.ids.alert_title.text = f" {type_text}"
        msg_lines = []
        if "distance_to_home" in detail:
            msg_lines.append(f"当前离家约 {detail['distance_to_home']} 米")
        if "away_minutes" in detail:
            msg_lines.append(f"已外出约 {detail['away_minutes']} 分钟")
        self.ids.alert_message.text = "\n".join(msg_lines)

        latest = app.gps_service.latest if app._services_ok else None
        if latest and latest.get("lat"):
            threading.Thread(target=self._fetch_location_info, args=(latest["lat"], latest["lon"]), daemon=True).start()

        container = self.ids.contact_buttons
        container.clear_widgets()
        for phone in contacts:
            btn = Button(
                text=f" 呼叫 {phone}",
                font_size="24sp", bold=True,
                size_hint=(0.85, None), height="80dp",
                pos_hint={"center_x": 0.5},
                background_normal="", background_color=(0.2, 0.6, 0.9, 1),
                color=(1, 1, 1, 1),
            )
            btn.bind(on_press=partial(self._make_call, phone))
            container.add_widget(btn)

        threading.Thread(target=self._send_alerts, args=(alert_type, detail, contacts), daemon=True).start()

    def _fetch_location_info(self, lat, lon):
        try:
            from utils.landmark import format_location_description
            desc = format_location_description(lat, lon)
            Clock.schedule_once(lambda dt: setattr(self.ids.alert_location, "text", desc))
        except Exception:
            Clock.schedule_once(lambda dt: setattr(self.ids.alert_location, "text", f"坐标：{lat:.6f}, {lon:.6f}"))

    def _send_alerts(self, alert_type, detail, contacts):
        app = App.get_running_app()
        if not app._services_ok:
            return
        latest = app.gps_service.latest
        if not latest or not latest.get("lat"):
            return
        try:
            from utils.landmark import format_location_description
            desc = format_location_description(latest["lat"], latest["lon"])
        except Exception:
            desc = f"坐标：{latest['lat']:.6f}, {latest['lon']:.6f}"
        app.alert_service.send_alert(contacts, alert_type, detail, desc)

    def _make_call(self, phone, instance):
        app = App.get_running_app()
        if app._services_ok:
            app.alert_service.make_call(phone)

    def dismiss_alert(self):
        self.manager.current = "main"


if __name__ == "__main__":
    SafeApp().run()
