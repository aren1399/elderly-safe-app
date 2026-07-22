# 老年防走失安全守护 - 完整测试方案

## 一、测试环境

| 项目 | 要求 |
|------|------|
| 测试手机 1（老人端） | Android 8.0+，支援 GPS，安装安全守护 APK |
| 测试手机 2（家人端） | 任意手机，可接收短信和电话 |
| PC 端 | Windows/Linux/macOS + Python 3.9+ + Kivy 2.x |
| 网络 | 手机需连接网络（GPS A-GPS 辅助 + 逆地理编码 API） |
| 定位环境 | 室外空旷处（GPS 信号良好） |

---

## 二、单元测试（PC 端，不依赖 Android）

### 2.1 配置管理测试

```python
# test_config_manager.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.config_manager import load_config, save_config, update_config, DEFAULT_CONFIG

def test_load_default_config():
    """首次加载返回默认配置。"""
    cfg = load_config()
    assert cfg["max_distance_meters"] == 500
    assert cfg["max_time_minutes"] == 60
    assert cfg["voice_enabled"] is True
    assert cfg["home_lat"] is None
    assert cfg["emergency_contacts"] == []
    print("✓ test_load_default_config")

def test_update_and_persist():
    """更新配置后能正确读出。"""
    update_config("home_lat", 39.9042)
    update_config("home_lon", 116.4074)
    cfg = load_config()
    assert cfg["home_lat"] == 39.9042
    assert cfg["home_lon"] == 116.4074
    # 恢复
    update_config("home_lat", None)
    update_config("home_lon", None)
    print("✓ test_update_and_persist")

def test_emergency_contacts():
    """紧急联系人增删。"""
    update_config("emergency_contacts", ["13800138000"])
    cfg = load_config()
    assert "13800138000" in cfg["emergency_contacts"]
    update_config("emergency_contacts", [])
    print("✓ test_emergency_contacts")

def test_preset_routes():
    """预设路线存储。"""
    route = [(39.9042, 116.4074, "途经点1"), (39.9142, 116.4174, "途经点2")]
    update_config("preset_routes", route)
    cfg = load_config()
    assert len(cfg["preset_routes"]) == 2
    assert cfg["preset_routes"][0][2] == "途经点1"
    update_config("preset_routes", [])
    print("✓ test_preset_routes")

if __name__ == "__main__":
    test_load_default_config()
    test_update_and_persist()
    test_emergency_contacts()
    test_preset_routes()
    print("\n全部配置管理测试通过")
```

### 2.2 地理围栏 + 导航单元测试

```python
# test_geofence.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from services.geofence_service import GeofenceService, _haversine, _bearing, _bearing_diff

# ---- 距离计算 ----

def test_haversine_known_distance():
    """北京天安门到故宫午门约 900 米。"""
    # 天安门: 39.9087, 116.3975
    # 午门: 39.9163, 116.3972
    dist = _haversine(39.9087, 116.3975, 39.9163, 116.3972)
    assert 800 < dist < 1000, f"距离 {dist} 不在预期范围"
    print(f"✓ test_haversine_known_distance ({dist:.0f}m)")

def test_haversine_same_point():
    dist = _haversine(39.9, 116.4, 39.9, 116.4)
    assert dist == 0
    print("✓ test_haversine_same_point")

# ---- 方位角 ----

def test_bearing_north():
    brg = _bearing(39.9, 116.4, 40.0, 116.4)
    assert brg < 5 or brg > 355  # 接近正北
    print(f"✓ test_bearing_north ({brg:.1f}°)")

def test_bearing_east():
    brg = _bearing(39.9, 116.4, 39.9, 116.5)
    assert 85 < brg < 95
    print(f"✓ test_bearing_east ({brg:.1f}°)")

def test_bearing_south():
    brg = _bearing(40.0, 116.4, 39.9, 116.4)
    assert 175 < brg < 185
    print(f"✓ test_bearing_south ({brg:.1f}°)")

def test_bearing_diff():
    """方位差计算。"""
    assert abs(_bearing_diff(90, 100) - 10) < 1
    assert abs(_bearing_diff(350, 10) - 20) < 1
    assert abs(_bearing_diff(10, 350) - (-20)) < 1
    assert abs(_bearing_diff(180, 0) - 180) < 2
    print("✓ test_bearing_diff")

# ---- 地理围栏检测 ----

def test_geofence_distance_alert():
    """离家超过设定距离触发告警。"""
    svc = GeofenceService()
    svc.configure(home_lat=39.9, home_lon=116.4, max_distance_m=200)

    # 当前位置离家 250m
    lat, lon = 39.9, 116.4025  # 约 215m
    is_safe, alert_type, detail = svc.check(lat, lon)
    assert not is_safe
    assert alert_type == "distance"
    assert detail["distance_to_home"] > 200
    print("✓ test_geofence_distance_alert")

def test_geofence_safe_when_near():
    """在家附近不触发告警。"""
    svc = GeofenceService()
    svc.configure(home_lat=39.9, home_lon=116.4, max_distance_m=500)
    lat, lon = 39.9, 116.4005  # 约 43m
    is_safe, alert_type, _ = svc.check(lat, lon)
    assert is_safe
    assert alert_type is None
    print("✓ test_geofence_safe_when_near")

def test_geofence_route_deviation():
    """偏离预设路线触发告警。"""
    svc = GeofenceService()
    route = [(39.9, 116.4, "起点"), (39.905, 116.405, "途经1"), (39.91, 116.41, "终点")]
    svc.configure(home_lat=39.9, home_lon=116.4, preset_routes=route)

    # 偏离路线 >200m 的位置
    lat, lon = 39.93, 116.43  # 远离路线
    is_safe, alert_type, detail = svc.check(lat, lon)
    assert not is_safe
    assert alert_type == "route"
    assert detail["route_deviation"] > 200
    print("✓ test_geofence_route_deviation")

def test_geofence_alert_once():
    """同一告警类型只触发一次。"""
    svc = GeofenceService()
    svc.configure(home_lat=39.9, home_lon=116.4, max_distance_m=200)

    lat, lon = 39.9, 116.403
    is_safe1, _, _ = svc.check(lat, lon)
    is_safe2, alert_type2, _ = svc.check(lat, lon)
    assert not is_safe1  # 第一次触发
    assert is_safe2      # 第二次不重复触发
    assert alert_type2 is None
    print("✓ test_geofence_alert_once")

# ---- 路线导航 ----

def test_navigation_basic():
    """基本导航指引。"""
    svc = GeofenceService()
    route = [(39.9, 116.4, "起点"), (39.902, 116.402, "路口"), (39.905, 116.405, "终点")]
    svc.configure(home_lat=39.9, home_lon=116.4, preset_routes=route)

    nav = svc.get_navigation(39.9, 116.4)
    assert nav is not None
    assert nav["instruction_type"] in ("first_step", "straight", "approach_waypoint")
    assert nav["should_announce"] is True
    assert "路口" in nav["next_waypoint_desc"]
    print(f"✓ test_navigation_basic: {nav['instruction_text']}")

def test_navigation_arrived():
    """到达终点检测。"""
    svc = GeofenceService()
    route = [(39.9, 116.4, "起点"), (39.905, 116.405, "终点")]
    svc.configure(home_lat=39.9, home_lon=116.4, preset_routes=route)

    nav = svc.get_navigation(39.905, 116.405)
    assert nav is not None
    assert nav["instruction_type"] == "arrived"
    print(f"✓ test_navigation_arrived: {nav['instruction_text']}")

def test_navigation_off_route():
    """偏离路线提示。"""
    svc = GeofenceService()
    route = [(39.9, 116.4, "起点"), (39.905, 116.405, "终点")]
    svc.configure(home_lat=39.9, home_lon=116.4, preset_routes=route)

    nav = svc.get_navigation(39.93, 116.43)
    assert nav is not None
    assert nav["instruction_type"] == "off_route"
    print(f"✓ test_navigation_off_route: {nav['instruction_text']}")

def test_navigation_throttle():
    """导航节流：同类型提示间隔至少 20 秒。"""
    svc = GeofenceService()
    route = [(39.9, 116.4, "起点"), (39.905, 116.405, "终点")]
    svc.configure(home_lat=39.9, home_lon=116.4, preset_routes=route)

    nav1 = svc.get_navigation(39.901, 116.401)
    assert nav1["should_announce"] is True

    # 紧接着再调用，不应重复播报
    nav2 = svc.get_navigation(39.901, 116.401)
    assert nav2["should_announce"] is False
    print("✓ test_navigation_throttle")

if __name__ == "__main__":
    test_haversine_known_distance()
    test_haversine_same_point()
    test_bearing_north()
    test_bearing_east()
    test_bearing_south()
    test_bearing_diff()
    test_geofence_distance_alert()
    test_geofence_safe_when_near()
    test_geofence_route_deviation()
    test_geofence_alert_once()
    test_navigation_basic()
    test_navigation_arrived()
    test_navigation_off_route()
    test_navigation_throttle()
    print("\n全部地理围栏 + 导航测试通过")
```

### 2.3 地标服务测试

```python
# test_landmark.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.landmark import reverse_geocode, get_nearby_landmarks, format_location_description, _haversine

def test_reverse_geocode_beijing():
    """北京天安门逆地理编码。"""
    geo = reverse_geocode(39.9087, 116.3975)
    if geo is None:
        print("⚠ test_reverse_geocode_beijing: API 不可达，跳过")
        return
    assert "display_name" in geo
    print(f"✓ test_reverse_geocode_beijing: {geo['display_name'][:60]}...")

def test_nearby_landmarks_beijing():
    """北京天安门周边地标。"""
    landmarks = get_nearby_landmarks(39.9087, 116.3975, radius=100)
    if not landmarks:
        print("⚠ test_nearby_landmarks_beijing: 无结果或 API 不可达")
        return
    assert len(landmarks) > 0
    print(f"✓ test_nearby_landmarks_beijing: 找到 {len(landmarks)} 个地标")
    for lm in landmarks[:3]:
        print(f"  - {lm['name']} ({lm['category']}) 约 {lm['distance']}m")

def test_format_location_description():
    """位置描述格式化。"""
    desc = format_location_description(39.9087, 116.3975)
    assert "坐标" in desc
    print(f"✓ test_format_location_description:\n{desc[:200]}...")

if __name__ == "__main__":
    test_reverse_geocode_beijing()
    test_nearby_landmarks_beijing()
    test_format_location_description()
    print("\n全部地标服务测试完成")
```

---

## 三、集成测试（桌面端 Kivy 运行）

### 3.1 桌面端启动测试

```bash
cd elderly_safe_app
python main.py
```

**检查点：**
- [ ] 应用窗口正常启动
- [ ] 显示「安全守护」标题
- [ ] 绿色「开始守护」大按钮可见
- [ ] 红色「安全到家」按钮灰色禁用
- [ ] 「设置」按钮可见
- [ ] 状态区显示「未开启守护」
- [ ] 无崩溃/报错

### 3.2 设置页面测试

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 点击「设置」 | 进入设置页面，显示所有配置项 |
| 2 | 查看家的位置 | 首次显示「未设置」 |
| 3 | 点击「设为家的位置」 | GPS 不可用时提示，可用时更新坐标 |
| 4 | 输入手机号 `13800138000` 点「添加」 | 联系人列表显示该号码 |
| 5 | 再输入 `13900139000` 点「添加」 | 两个号码都显示 |
| 6 | 拖动安全距离滑块到 800 | 显示「800 米」 |
| 7 | 拖动外出时间滑块到 120 | 显示「120 分钟」 |
| 8 | 开关语音播报 | 正常切换 |
| 9 | 点击「保存并返回」 | 回到主页面 |

### 3.3 路线设置测试

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 进入设置 → 预设路线区域 | 初始显示「未设置路线」 |
| 2 | 点击「📍 添加途经点」 | GPS 可用时添加当前坐标为途经点1 |
| 3 | 移动到新位置，再次点击「添加途经点」 | 添加途经点2，列表显示两个点 |
| 4 | 重复添加 3-5 个途经点 | 路线列表正确编号显示 |
| 5 | 点击「🗑 清空路线」 | 路线清空，显示「未设置路线」 |

### 3.4 告警流程测试（桌面端模拟）

由于桌面端无真实 GPS，修改 `main.py` 注入模拟坐标进行测试：

```python
# 在 ElderlySafeApp._monitor_tick 中注入测试坐标
# 模拟离家 600m（超过默认 500m）

# 修改测试：将 geofence_service.configure() 的距离改为 100m
# 用实际桌面坐标模拟离家远的情况
```

| 场景 | 模拟 | 预期 |
|------|------|------|
| 离家过远 | 距离 > max_distance | 告警页弹出，红色背景，SMS 发送 |
| 离家过久 | 时间 > max_time | 告警页弹出，显示已外出时间 |
| 偏离路线 | 距离路线 > 200m | 告警页弹出，显示偏离距离 |

---

## 四、真机测试（Android 设备）

### 4.1 安装与启动

```bash
buildozer android debug deploy run
# 或手动安装 bin/elderlysafe-1.0.0-debug.apk
```

- [ ] APK 安装成功，无签名/权限错误
- [ ] 应用图标出现在桌面
- [ ] 首次启动请求权限（定位、短信、电话）——全部允许
- [ ] 应用进入主页面，界面正常显示

### 4.2 GPS 定位测试

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 到室外空旷处 | — |
| 2 | 打开应用，等待 10-30 秒 | 状态区显示坐标数据 |
| 3 | 走到不同位置（>10 米） | 坐标更新 |
| 4 | 关闭手机定位服务 | 提示「GPS 未开启」 |
| 5 | 重新开启定位 | 恢复正常 |

### 4.3 家的位置设置测试（真机）

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 在家中打开应用 | GPS 获取当前位置 |
| 2 | 设置 → 「📍 设为家的位置」 | 显示坐标，语音播报「家的位置已设置成功」 |
| 3 | 关闭并重启应用 | 家的位置仍然保存 |

### 4.4 路线设置测试（真机，家人操作）

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 在家中设置家的位置 | ✓ |
| 2 | 走到小区门口，点击「添加途经点」 | 添加「小区门口」 |
| 3 | 走到路口，点击「添加途经点」 | 添加「XX路口」 |
| 4 | 走到菜市场，点击「添加途经点」 | 添加「菜市场」 |
| 5 | 走到公园，点击「添加途经点」 | 添加「XX公园」 |
| 6 | 查看路线列表 | 所有途经点按序显示 |
| 7 | 保存并返回 | 路线保存成功 |

### 4.5 守护功能测试（真机）

| 测试场景 | 老人位置 | 预期行为 |
|----------|----------|----------|
| **正常守护** | 在家中（离家 <30m） | 显示「🟢 守护中」，离家距离 ~0m |
| **正常外出（近距离）** | 离家 200m（设 max=500m） | 显示距离，无告警 |
| **离家过远告警** | 离家 600m（设 max=500m） | ① 语音「请注意，您已离家过远」② 屏幕变红 ③ 家人收到 SMS ④ 可点按钮呼叫家人 |
| **离家过久告警** | 离家 200m 停留 >60min（设 max=60min） | ① 语音「您已外出较长时间」② 告警页面 ③ 家人收到 SMS |
| **安全到家** | 按「安全到家」按钮 | 守护关闭，语音播报「安全守护已关闭」 |

### 4.6 预设路线导航测试（真机）

| 测试场景 | 老人位置 | 预期语音播报 |
|----------|----------|-------------|
| **出发** | 在家中开启守护 | 「安全守护已开启」+「路线导航已开启，请按语音提示行走」 |
| **第一步** | 离家出发 | 「请向XX方向出发，前往小区门口，约 XX 米」 |
| **正常行进** | 在路线上步行 | 「继续直行，向XX方向，约 XX 米到达XX路口」 |
| **接近途经点** | 距下一途经点 <50m | 「前方约 XX 米到达XX路口」 |
| **到达途经点** | 距途经点 <30m | 「即将到达XX路口，请继续前行」 |
| **偏离路线** | 离开路线 >100m | 「您已偏离路线，请调头返回或沿原路返回」 |
| **需要左转** | 前进方向偏右，目标在左 | 「请注意向左调整方向，向XX方向前进」 |
| **需要右转** | 前进方向偏左，目标在右 | 「请注意向右调整方向，向XX方向前进」 |
| **到达终点** | 距离最终途经点 <30m | 「您已到达目的地」 |

### 4.7 短信告警测试（真机）

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 触发离家过远告警 | — |
| 2 | 检查家人手机短信 | 收到包含以下内容的短信：告警类型、离家距离、安全距离、位置坐标 |
| 3 | 检查短信中的位置描述 | 包含逆地理编码地址 |
| 4 | 检查短信中的地标信息 | 包含 30-50m 内标志性建筑名称、类别、距离 |

### 4.8 电话告警测试（真机）

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 告警触发后，点「📞 呼叫 138xxxx」 | 弹出拨号界面或直接拨出 |
| 2 | 测试所有联系人按钮 | 每个都可正确拨号 |

### 4.9 语音播报测试（真机）

| 场景 | 预期语音 |
|------|----------|
| 开启守护 | 「安全守护已开启，请随身携带手机」 |
| 关闭守护 | 「安全守护已关闭」 |
| 离家过远 | 「请注意，您已离家过远，正在通知家人」 |
| 离家过久 | 「请注意，您已外出较长时间，正在通知家人」 |
| 偏离路线 | 「请注意，您已偏离预设路线，正在通知家人」 |
| 设置家位置 | 「家的位置已设置成功」 |
| 添加途经点 | 「已添加途经点X」 |

- [ ] 所有语音播报均为中文
- [ ] 音量适中，老人可听清
- [ ] 语速合适

### 4.10 边界/异常测试

| 测试场景 | 操作 | 预期 |
|----------|------|------|
| GPS 信号丢失 | 进入地下室/隧道 | 保持上一个已知位置，不误报 |
| 快速切换开关 | 快速按「开始守护」→「安全到家」→「开始守护」 | 状态正确切换，不崩溃 |
| 未设家位置直接开始 | 不设置家位置，点「开始守护」 | 提示先设置家位置 |
| 未添加联系人直接开始 | 设了家位置但不加联系人 | 提示先添加联系人 |
| 低电量 | 电量 5% 以下 | 应用继续工作（不应崩溃） |
| 网络断开 | 关闭 WiFi/移动数据 | GPS 继续工作，地标 API 返回空，短信仍发送 |
| 短信权限拒绝 | 拒绝 SEND_SMS 权限 | 打开短信应用预填内容 |
| 电话权限拒绝 | 拒绝 CALL_PHONE 权限 | 打开拨号盘预填号码 |
| 屏幕旋转 | 旋转手机 | 保持竖屏（不旋转） |
| 后台运行 | 按 Home 键 | 不崩溃（但 GPS 可能暂停，这是已知限制） |
| 多个联系人 | 添加 5 个联系人 | 告警时全部收到短信 |

---

## 五、性能测试

| 指标 | 目标 | 测试方法 |
|------|------|----------|
| GPS 定位延迟 | < 15 秒（冷启动） | 关闭 GPS → 打开 → 计时到首次获取坐标 |
| 监控响应时间 | < 16 秒 | 模拟偏离路线 → 计时到告警触发（8s×2） |
| 内存占用 | < 150 MB | Android Profiler / adb shell dumpsys meminfo |
| CPU 使用率 | < 15%（待机） | Android Profiler |
| 电池消耗 | < 8%/小时（持续 GPS） | 从 100% 开始跑 1 小时监测 |
| APK 大小 | < 30 MB | 检查 bin/*.apk 文件大小 |
| 短信到达时间 | < 30 秒 | 触发告警 → 家人手机收到短信 |

---

## 六、兼容性测试

| 测试设备 | Android 版本 | 结果 |
|----------|-------------|------|
| 低端机（2GB RAM） | 8.0 | □ |
| 中端机（4GB RAM） | 10.0 | □ |
| 高端机（8GB RAM） | 13.0 | □ |
| 华为（EMUI） | 9.0+ | □ |
| 小米（MIUI） | 10.0+ | □ |
| OPPO/vivo | 10.0+ | □ |
| 三星（One UI） | 10.0+ | □ |

---

## 七、用户验收测试（UAT）

### 老人端

| 测试 | 通过标准 |
|------|----------|
| 能否独立打开应用 | 30 秒内完成 |
| 能否找到「开始守护」按钮 | 10 秒内找到 |
| 能否理解语音提示 | 理解所有语音内容 |
| 能否看清屏幕文字 | 不需要老花镜即可阅读 |
| 告警时能否按「呼叫」按钮 | 5 秒内完成 |
| 能否完成一次完整外出+回家流程 | 全程无需帮助 |

### 家人端

| 测试 | 通过标准 |
|------|----------|
| 能否完成初始设置 | 5 分钟内设好家位置+联系人+路线 |
| 能否设置预设路线 | 3 分钟内完成 3-5 个途经点设置 |
| 能否理解告警短信 | 看短信即可定位老人位置 |
| 能否根据短信找到老人 | 根据地址+地标在 10 分钟内找到 |

---

## 八、测试执行清单

### 阶段 1：桌面端（开发过程中）
- [ ] 单元测试全部通过（test_config_manager.py）
- [ ] 单元测试全部通过（test_geofence.py）
- [ ] 单元测试全部通过（test_landmark.py）
- [ ] Kivy 桌面启动正常
- [ ] 设置页面功能正常

### 阶段 2：模拟器/单设备（功能完成）
- [ ] APK 构建成功
- [ ] 在 Android 模拟器上安装运行
- [ ] GPS 模拟注入测试（使用模拟器的 GPS 模拟功能）
- [ ] 所有功能可用

### 阶段 3：双设备真机（真实环境）
- [ ] 老人手机安装运行
- [ ] 家人手机可接收短信/电话
- [ ] 完整流程测试（设家→设路线→外出→告警→回家）
- [ ] 各种边界条件测试

### 阶段 4：用户验收
- [ ] 邀请 2-3 位老人试用
- [ ] 收集反馈
- [ ] 修正确认的问题

---

## 九、回滚方案

如测试中发现严重问题需要回退：

```bash
# 回退到某个已知良好状态
git stash
git checkout <last-stable-commit>

# 或直接恢复关键文件
cp backups/main.py.bak elderly_safe_app/main.py
cp backups/geofence_service.py.bak elderly_safe_app/services/geofence_service.py
```
