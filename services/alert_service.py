"""告警服务 - 通过短信和电话通知家人。"""

try:
    from plyer import sms
    HAS_SMS = True
except ImportError:
    HAS_SMS = False

try:
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")
    SmsManager = autoclass("android.telephony.SmsManager")
    PendingIntent = autoclass("android.app.PendingIntent")
    HAS_JNIUS = True
except ImportError:
    HAS_JNIUS = False


class AlertService:
    """告警服务，负责发送短信和拨打电话。"""

    def __init__(self):
        self._sms_sent = set()

    def send_alert(self, contacts, alert_type, detail, location_desc):
        """向所有紧急联系人发送告警短信。"""
        message = self._build_message(alert_type, detail, location_desc)
        for phone in contacts:
            if phone and phone.strip():
                self._send_sms(phone.strip(), message)

    def _build_message(self, alert_type, detail, location_desc):
        type_text = {
            "distance": "⚠️ 老人离家过远告警",
            "time": "⏰ 老人外出时间过长告警",
            "route": "🔄 老人偏离路线告警",
        }.get(alert_type, "⚠️ 老人安全告警")

        lines = [type_text, ""]

        if "distance_to_home" in detail:
            lines.append(f"离家距离：约 {detail['distance_to_home']} 米")
            lines.append(f"安全距离：{detail['max_distance']} 米")
        if "away_minutes" in detail:
            lines.append(f"已外出：约 {detail['away_minutes']} 分钟")
        if "route_deviation" in detail:
            lines.append(f"偏离路线：约 {detail['route_deviation']} 米")

        lines.append("")
        lines.append("【当前位置信息】")
        lines.append(location_desc)
        lines.append("")
        lines.append("请尽快联系老人确认安全。")

        return "\n".join(lines)

    def _send_sms(self, phone, message):
        """发送短信。"""
        dedup_key = f"{phone}:{hash(message)}"
        if dedup_key in self._sms_sent:
            return
        self._sms_sent.add(dedup_key)

        # 方法 1：Android SmsManager 直接发送（最可靠）
        if HAS_JNIUS:
            try:
                sent_intent = PendingIntent.getBroadcast(
                    PythonActivity.mActivity, 0, Intent(), 0
                )
                manager = SmsManager.getDefault()
                # 长短信分条发送
                if len(message) > 160:
                    parts = manager.divideMessage(message)
                    manager.sendMultipartTextMessage(
                        phone, None, parts, None, None
                    )
                else:
                    manager.sendTextMessage(
                        phone, None, message, sent_intent, None
                    )
                return
            except Exception:
                pass

        # 方法 2：Plyer 发送
        if HAS_SMS:
            try:
                sms.send(recipient=phone, message=message)
                return
            except Exception:
                pass

        # 方法 3：Intent 打开短信应用（预填内容，需用户手动发送）
        if HAS_JNIUS:
            try:
                intent = Intent(Intent.ACTION_VIEW)
                intent.setData(Uri.parse(f"sms:{phone}"))
                intent.putExtra("sms_body", message)
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                PythonActivity.mActivity.startActivity(intent)
                return
            except Exception:
                pass

    def make_call(self, phone):
        """拨打电话。"""
        if not phone or not phone.strip():
            return False
        phone = phone.strip()
        if not HAS_JNIUS:
            return False

        try:
            intent = Intent(Intent.ACTION_CALL)
            intent.setData(Uri.parse(f"tel:{phone}"))
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            PythonActivity.mActivity.startActivity(intent)
            return True
        except Exception:
            pass

        try:
            intent = Intent(Intent.ACTION_DIAL)
            intent.setData(Uri.parse(f"tel:{phone}"))
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            PythonActivity.mActivity.startActivity(intent)
            return True
        except Exception:
            return False

    def clear_sent_cache(self):
        self._sms_sent.clear()
