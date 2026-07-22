"""地理围栏服务 - 监控老人是否超出安全范围或偏离路线，并提供路线导航指引。"""

import math
import time


def _haversine(lat1, lon1, lat2, lon2):
    """计算两点间距离（米）。"""
    r = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1, lon1, lat2, lon2):
    """计算从点 1 到点 2 的方位角（0-360 度，正北为 0）。"""
    dlon = math.radians(lon2 - lon1)
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlon)
    brg = math.degrees(math.atan2(x, y))
    return (brg + 360) % 360


def _bearing_diff(b1, b2):
    """两个方位角之间的最小差值（-180 到 180，正=右转，负=左转）。"""
    diff = (b2 - b1 + 180) % 360 - 180
    if diff > 180:
        diff -= 360
    return diff


class GeofenceService:
    """地理围栏监控服务 + 路线导航。

    检测三种异常：
    1. 离家过远（超出设定半径）
    2. 离家时间过长（超出设定时长）
    3. 偏离预设路线（偏离 200 米以上）

    提供导航指引：
    - 距离下一途经点的距离和方向
    - 直行/左转/右转指引
    - 接近途经点提醒
    """

    def __init__(self):
        self._home_lat = None
        self._home_lon = None
        self._max_distance = 500
        self._max_time = 60 * 60
        self._preset_routes = []  # [(lat, lon, description), ...]

        # 告警状态
        self._leave_time = None
        self._alert_sent_distance = False
        self._alert_sent_time = False
        self._alert_sent_route = False
        self._last_check_time = 0
        self._near_home_threshold = 30

        # 导航状态
        self._last_position = None
        self._last_waypoint_index = -1
        self._last_announce_time = 0
        self._last_announce_type = None
        self._announce_throttle = 20  # 同类型导航提示至少间隔 20 秒
        self._waypoint_approach_threshold = 30  # 30 米内视为到达途经点
        self._waypoint_name_index = 0  # 途经点自动命名计数器

    def configure(self, home_lat, home_lon, max_distance_m=500, max_time_min=60, preset_routes=None):
        """配置围栏参数和路线。"""
        self._home_lat = home_lat
        self._home_lon = home_lon
        self._max_distance = max_distance_m
        self._max_time = max_time_min * 60
        self._preset_routes = preset_routes or []
        self._reset_alerts()

    def add_route_point(self, lat, lon, description=""):
        """添加一个路线途经点（由家人设置）。"""
        if not description:
            self._waypoint_name_index += 1
            description = f"途经点{self._waypoint_name_index}"
        self._preset_routes.append((lat, lon, description))

    def clear_routes(self):
        self._preset_routes = []
        self._waypoint_name_index = 0

    def _reset_alerts(self):
        self._leave_time = None
        self._alert_sent_distance = False
        self._alert_sent_time = False
        self._alert_sent_route = False
        # 重置导航状态
        self._last_waypoint_index = -1
        self._last_announce_time = 0
        self._last_announce_type = None
        self._last_position = None

    @property
    def is_configured(self):
        return self._home_lat is not None and self._home_lon is not None

    @property
    def has_route(self):
        return len(self._preset_routes) >= 2

    # ---- 安全检测 ----

    def check(self, current_lat, current_lon):
        """
        检查当前位置是否安全。

        :return: (is_safe, alert_type, detail_dict)
        """
        if not self.is_configured:
            return True, None, {}

        now = time.time()
        self._last_check_time = now

        dist_to_home = _haversine(
            self._home_lat, self._home_lon, current_lat, current_lon
        )

        detail = {
            "distance_to_home": round(dist_to_home, 1),
            "max_distance": self._max_distance,
            "current_lat": current_lat,
            "current_lon": current_lon,
        }

        is_away = dist_to_home > self._near_home_threshold

        # 1. 距离检测
        if dist_to_home > self._max_distance and not self._alert_sent_distance:
            self._alert_sent_distance = True
            return False, "distance", detail

        # 2. 时间检测
        if is_away:
            if self._leave_time is None:
                self._leave_time = now
            away_duration = now - self._leave_time
            detail["away_minutes"] = round(away_duration / 60, 1)
            if away_duration > self._max_time and not self._alert_sent_time:
                self._alert_sent_time = True
                return False, "time", detail
        else:
            self._leave_time = None
            self._alert_sent_time = False

        # 3. 路线偏离检测
        if self._preset_routes and not self._alert_sent_route:
            min_dist = min(
                _haversine(current_lat, current_lon, rlat, rlon)
                for rlat, rlon, _desc in self._preset_routes
            )
            detail["route_deviation"] = round(min_dist, 1)
            if min_dist > 200:
                self._alert_sent_route = True
                return False, "route", detail

        return True, None, detail

    # ---- 路线导航 ----

    def get_navigation(self, current_lat, current_lon):
        """
        获取导航指引。有预设路线时提供方向的语音指引。

        :return: dict 或 None（无路线或无有效指引）
            {
                "should_announce": bool,
                "instruction_type": "straight"/"turn_left"/"turn_right"/
                                    "approach_waypoint"/"arrived"/"off_route"/"first_step",
                "instruction_text": str,        # 完整播报文本
                "next_waypoint_desc": str,      # 下一途经点描述
                "distance_to_next": float,      # 到下一途经点的距离（米）
                "bearing_direction": str,       # 方向描述（东/南/西/北/东北等）
                "total_remaining": float,       # 剩余总距离（米）
                "current_waypoint_index": int,  # 当前前往的途经点索引
            }
        """
        if len(self._preset_routes) < 2:
            return None

        now = time.time()

        # 找到最近的路线点
        distances = [
            (_haversine(current_lat, current_lon, rlat, rlon), i)
            for i, (rlat, rlon, _desc) in enumerate(self._preset_routes)
        ]
        nearest_dist, nearest_idx = min(distances, key=lambda x: x[0])

        # 判断下一目标途经点
        if nearest_idx < len(self._preset_routes) - 1:
            candidate_next = nearest_idx + 1
        else:
            candidate_next = nearest_idx

        # 如果最近点不是最后一个，且距离近到可视为"到达"
        if nearest_dist < self._waypoint_approach_threshold and nearest_idx < len(self._preset_routes) - 1:
            candidate_next = nearest_idx + 1

        next_lat, next_lon, next_desc = self._preset_routes[candidate_next]
        dist_to_next = _haversine(current_lat, current_lon, next_lat, next_lon)

        # 计算方向
        brg = _bearing(current_lat, current_lon, next_lat, next_lon)
        direction = self._bearing_to_direction(brg)

        # 计算总剩余距离
        total_remaining = 0.0
        for i in range(candidate_next, len(self._preset_routes) - 1):
            rlat1, rlon1, _ = self._preset_routes[i]
            rlat2, rlon2, _ = self._preset_routes[i + 1]
            total_remaining += _haversine(rlat1, rlon1, rlat2, rlon2)
        total_remaining += dist_to_next

        # 确定指引类型和文本
        result = {
            "should_announce": False,
            "instruction_type": "straight",
            "instruction_text": "",
            "next_waypoint_desc": next_desc,
            "distance_to_next": round(dist_to_next, 1),
            "bearing_direction": direction,
            "total_remaining": round(total_remaining, 1),
            "current_waypoint_index": candidate_next,
        }

        # 到达终点
        if candidate_next == len(self._preset_routes) - 1 and dist_to_next < self._waypoint_approach_threshold:
            result["instruction_type"] = "arrived"
            result["instruction_text"] = "您已到达目的地"
            result["should_announce"] = self._should_announce(now, "arrived")
        # 接近途经点
        elif dist_to_next < self._waypoint_approach_threshold:
            result["instruction_type"] = "approach_waypoint"
            result["instruction_text"] = f"即将到达{next_desc}，请继续前行"
            result["should_announce"] = self._should_announce(now, "approach_waypoint")
        # 接近途经点（50 米提醒）
        elif dist_to_next < 50 and self._last_waypoint_index != candidate_next:
            result["instruction_type"] = "approach_waypoint"
            result["instruction_text"] = f"前方约 {int(dist_to_next)} 米到达{next_desc}"
            result["should_announce"] = self._should_announce(now, "approach_waypoint")
            self._last_waypoint_index = candidate_next
        # 偏离路线
        elif nearest_dist > 100:
            result["instruction_type"] = "off_route"
            result["instruction_text"] = "您已偏离路线，请调头返回或沿原路返回"
            result["should_announce"] = self._should_announce(now, "off_route")
        # 正常导航 - 判断是否需要转向
        elif self._last_position is not None:
            prev_lat, prev_lon = self._last_position
            movement_dist = _haversine(prev_lat, prev_lon, current_lat, current_lon)

            if movement_dist > 3:  # 有足够移动量才判断方向
                movement_brg = _bearing(prev_lat, prev_lon, current_lat, current_lon)
                diff = _bearing_diff(movement_brg, brg)

                if abs(diff) < 30:
                    result["instruction_type"] = "straight"
                    result["instruction_text"] = f"继续直行，向{direction}方向，约 {int(dist_to_next)} 米到达{next_desc}"
                elif diff > 0:
                    result["instruction_type"] = "turn_right"
                    result["instruction_text"] = f"请注意向右调整方向，向{direction}方向前进"
                else:
                    result["instruction_type"] = "turn_left"
                    result["instruction_text"] = f"请注意向左调整方向，向{direction}方向前进"

                result["should_announce"] = (
                    self._should_announce(now, result["instruction_type"])
                    and dist_to_next > self._waypoint_approach_threshold
                )
        else:
            # 首次指引
            result["instruction_type"] = "first_step"
            result["instruction_text"] = f"请向{direction}方向出发，前往{next_desc}，约 {int(dist_to_next)} 米"
            result["should_announce"] = self._should_announce(now, "first_step")

        # 更新导航状态
        self._last_position = (current_lat, current_lon)

        if result["should_announce"]:
            self._last_announce_time = now
            self._last_announce_type = result["instruction_type"]

        return result

    def _should_announce(self, now, announce_type):
        """节流：同类型提示至少间隔指定秒数。"""
        if announce_type == "off_route":
            # 偏离路线提示更频繁（10 秒）
            return (now - self._last_announce_time) > 10
        if announce_type == "arrived":
            return True
        if announce_type != self._last_announce_type:
            return True
        return (now - self._last_announce_time) > self._announce_throttle

    @staticmethod
    def _bearing_to_direction(brg):
        """将方位角转为中文方向描述。"""
        dirs = [
            (0, "北"), (22.5, "东北偏北"), (45, "东北"), (67.5, "东北偏东"),
            (90, "东"), (112.5, "东南偏东"), (135, "东南"), (157.5, "东南偏南"),
            (180, "南"), (202.5, "西南偏南"), (225, "西南"), (247.5, "西南偏西"),
            (270, "西"), (292.5, "西北偏西"), (315, "西北"), (337.5, "西北偏北"),
            (360, "北"),
        ]
        for threshold, name in dirs:
            if brg <= threshold + 11.25:
                return name
        return "北"

    def reset_alerts(self):
        """重置所有告警和导航状态（用于下一次外出）。"""
        self._reset_alerts()
        self._last_position = None
