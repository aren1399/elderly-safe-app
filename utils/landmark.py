"""地标识别 - 通过逆地理编码获取附近标志性建筑信息。"""

import json
import urllib.request
import urllib.parse


def _http_get(url, timeout=10):
    """发送 HTTP GET 并返回解析后的 JSON。"""
    req = urllib.request.Request(url, headers={"User-Agent": "ElderlySafeApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def reverse_geocode(lat, lon):
    """
    逆地理编码 - 获取坐标的地址描述（中文）。

    返回 dict: {display_name, road, suburb, city} 或 None。
    """
    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?format=json&lat={lat}&lon={lon}&accept-language=zh&zoom=18"
    )
    data = _http_get(url)
    if not data:
        return None

    addr = data.get("address", {})
    return {
        "display_name": data.get("display_name", "未知位置"),
        "road": addr.get("road", ""),
        "building": addr.get("building", ""),
        "suburb": addr.get("suburb", addr.get("neighbourhood", "")),
        "city": addr.get("city", addr.get("town", addr.get("county", ""))),
    }


def get_nearby_landmarks(lat, lon, radius=50):
    """
    获取周边指定半径内的标志性建筑（POI）。

    使用 OpenStreetMap Overpass API 查询。

    :param lat: 纬度
    :param lon: 经度
    :param radius: 搜索半径（米），默认 50
    :return: 地标名称列表，按距离排序
    """
    query = f"""
    [out:json][timeout:10];
    (
      node(around:{radius},{lat},{lon})["name"]["amenity"];
      node(around:{radius},{lat},{lon})["name"]["shop"];
      node(around:{radius},{lat},{lon})["name"]["tourism"];
      node(around:{radius},{lat},{lon})["name"]["leisure"];
      node(around:{radius},{lat},{lon})["name"]["building"]["name"~"."];
      node(around:{radius},{lat},{lon})["name"]["railway"~"station|halt|tram_stop|subway_entrance"];
      node(around:{radius},{lat},{lon})["name"]["highway"~"bus_stop|crossing"];
      node(around:{radius},{lat},{lon})["name"]["public_transport"~"platform|station"];
    );
    out body;
    """
    url = "https://overpass-api.de/api/interpreter"
    full_url = url + "?" + urllib.parse.urlencode({"data": query.strip()})

    data = _http_get(full_url, timeout=15)
    if not data:
        return []

    elements = data.get("elements", [])
    landmarks = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "")
        if not name:
            continue
        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")
        tourism = tags.get("tourism", "")
        railway = tags.get("railway", "")
        highway = tags.get("highway", "")
        leisure = tags.get("leisure", "")

        category = _translate_category(
            amenity or shop or tourism or railway or highway or leisure
        )
        lat_el = el.get("lat", 0)
        lon_el = el.get("lon", 0)
        dist = _haversine(lat, lon, lat_el, lon_el)

        landmarks.append(
            {"name": name, "category": category, "distance": round(dist, 1)}
        )

    landmarks.sort(key=lambda x: x["distance"])
    return landmarks


def format_location_description(lat, lon):
    """
    生成位置描述文本，包含地址和周边地标。

    :return: 可读的位置描述字符串
    """
    geo = reverse_geocode(lat, lon)
    landmarks = get_nearby_landmarks(lat, lon, radius=50)

    parts = []

    if geo:
        address = geo.get("display_name", "")
        if address:
            parts.append(f"📍 地址：{address}")

    if landmarks:
        nearby = ", ".join(
            f'{lm["name"]}({lm["category"]}，约{lm["distance"]}米)'
            for lm in landmarks[:5]
        )
        parts.append(f"🏠 周边标志建筑：{nearby}")
    else:
        # 尝试更大范围搜索
        landmarks_wide = get_nearby_landmarks(lat, lon, radius=100)
        if landmarks_wide:
            nearby = ", ".join(
                f'{lm["name"]}({lm["category"]}，约{lm["distance"]}米)'
                for lm in landmarks_wide[:5]
            )
            parts.append(f"🏠 周边标志建筑（100米内）：{nearby}")

    parts.append(f"📍 坐标：{lat:.6f}, {lon:.6f}")

    return "\n".join(parts)


CATEGORY_MAP = {
    "restaurant": "餐厅",
    "cafe": "咖啡馆",
    "fast_food": "快餐店",
    "bank": "银行",
    "atm": "ATM取款机",
    "pharmacy": "药店",
    "hospital": "医院",
    "clinic": "诊所",
    "school": "学校",
    "kindergarten": "幼儿园",
    "police": "派出所",
    "fire_station": "消防站",
    "post_office": "邮局",
    "library": "图书馆",
    "marketplace": "市场",
    "supermarket": "超市",
    "convenience": "便利店",
    "bakery": "面包店",
    "butcher": "肉店",
    "mall": "商场",
    "department_store": "百货商店",
    "hotel": "酒店",
    "guest_house": "旅馆",
    "museum": "博物馆",
    "park": "公园",
    "playground": "游乐场",
    "sports_centre": "体育中心",
    "stadium": "体育场",
    "swimming_pool": "游泳池",
    "bus_stop": "公交站",
    "station": "车站",
    "subway_entrance": "地铁入口",
    "tram_stop": "电车站",
    "crossing": "路口",
    "bench": "长椅",
    "toilets": "公共厕所",
    "fountain": "喷泉",
    "place_of_worship": "宗教场所",
    "town_hall": "市政厅",
    "community_centre": "社区中心",
    "parking": "停车场",
    "fuel": "加油站",
    "car_wash": "洗车店",
    "bar": "酒吧",
    "pub": "酒馆",
    "cinema": "电影院",
    "theatre": "剧院",
    "bicycle_rental": "自行车租赁点",
    "taxi": "出租车站",
}


def _translate_category(tag_value):
    return CATEGORY_MAP.get(tag_value, tag_value)


def _haversine(lat1, lon1, lat2, lon2):
    """计算两点间的距离（米）。"""
    import math

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
