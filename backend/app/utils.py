# 通用小工具：JSON 文本字段解析（读接口统一转成结构化数据）
import json


def parse_json(value, default):
    """把 JSON 文本解析成对象；失败或为空时返回 default"""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def parse_standard(s: dict) -> dict:
    s = dict(s)
    s["allowed_values"] = parse_json(s.get("allowed_values"), [])
    s["check_rules"] = parse_json(s.get("check_rules"), {})
    return s


def parse_resource(r: dict) -> dict:
    r = dict(r)
    r["related_standards"] = parse_json(r.get("related_standards"), [])
    return r
