"""GPS 定位服务 - 获取设备精确坐标。"""

try:
    from plyer import gps
    HAS_GPS = True
except ImportError:
    HAS_GPS = False


class GPSService:
    """GPS 定位服务，封装 Plyer GPS 接口。"""

    def __init__(self):
        self._callback = None
        self._latest = None
        self._running = False
        self._error = None

    @property
    def latest(self):
        """返回最新定位数据: {lat, lon, accuracy, timestamp} 或 None。"""
        return self._latest

    @property
    def running(self):
        return self._running

    @property
    def error(self):
        return self._error

    def start(self, callback, min_time=10000, min_distance=5):
        """
        启动 GPS 定位。

        :param callback: 当获取到新位置时调用 callback(location_dict)
        :param min_time: 最小更新间隔（毫秒），默认 10 秒
        :param min_distance: 最小移动距离（米），默认 5 米
        """
        if not HAS_GPS:
            self._error = "GPS 模块不可用"
            return False

        self._callback = callback
        self._error = None

        try:
            gps.configure(on_location=self._on_location, on_status=self._on_status)
            gps.start(minTime=min_time, minDistance=min_distance)
            self._running = True
            return True
        except Exception as e:
            self._error = str(e)
            return False

    def stop(self):
        """停止 GPS 定位。"""
        if HAS_GPS and self._running:
            try:
                gps.stop()
            except Exception:
                pass
        self._running = False
        self._callback = None

    def _on_location(self, **kwargs):
        loc = {
            "lat": kwargs.get("lat"),
            "lon": kwargs.get("lon"),
            "accuracy": kwargs.get("accuracy"),
            "altitude": kwargs.get("altitude"),
            "timestamp": kwargs.get("timestamp"),
        }
        self._latest = loc
        if self._callback:
            self._callback(loc)

    def _on_status(self, stype, status):
        if stype == "gps" and status == "provider-disabled":
            self._error = "GPS 未开启，请打开定位服务"
        elif stype == "gps" and status == "provider-enabled":
            self._error = None
