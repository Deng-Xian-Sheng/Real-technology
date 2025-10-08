"""
用于关机，比如：
train command ; AUTODL_TOKEN='xxx' python autodl_off.py "xx区/xx机"
"""

import os
import sys
import requests

# 可选：若安装了 python-dotenv，会自动加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_BASE = "https://www.autodl.com/api/v1"


def get_token():
    # 优先 AUTODL_TOKEN，兼容 Authorization
    token = os.getenv("AUTODL_TOKEN") or os.getenv("Authorization") or os.getenv("AUTHORIZATION")
    if not token:
        sys.exit("未找到令牌，请先设置环境变量：AUTODL_TOKEN 或 Authorization")
    return token


def get_headers():
    token = get_token()
    return {
        "authorization": token,
        "content-type": "application/json;charset=UTF-8",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "accept": "*/*",
        "origin": "https://www.autodl.com",
        "referer": "https://www.autodl.com/console/instance/list",
    }


def fetch_instances(page_index=1, page_size=100):
    url = f"{API_BASE}/instance"
    data = {
        "date_from": "",
        "date_to": "",
        "page_index": page_index,
        "page_size": page_size,
        "status": [],
        "charge_type": [],
    }
    r = requests.post(url, headers=get_headers(), json=data, timeout=10)
    j = r.json()
    if j.get("code") != "Success":
        raise RuntimeError(f"获取实例列表失败: {j.get('msg') or j}")
    return j["data"]["list"]


def find_instance_by_region_and_alias(region, alias):
    page = 1
    while True:
        items = fetch_instances(page_index=page, page_size=100)
        if not items:
            break
        for inst in items:
            if str(inst.get("region_name", "")).strip() == region and str(inst.get("machine_alias", "")).strip() == alias:
                return inst
        page += 1
    return None


def power_off_instance(instance_uuid):
    url = f"{API_BASE}/instance/power_off"
    data = {"instance_uuid": instance_uuid}
    r = requests.post(url, headers=get_headers(), json=data, timeout=10)
    return r.json()


def main():
    if len(sys.argv) != 2:
        print("用法: python autodl_off.py 区域/机器名称")
        print('示例: python autodl_off.py "V100专区/01机"')
        sys.exit(2)

    target = sys.argv[1].strip()
    if "/" not in target:
        print('参数格式错误，应为: 区域/机器名称  例如: V100专区/01机')
        sys.exit(2)

    region, alias = [x.strip() for x in target.split("/", 1)]
    print(f"准备关闭机器: {region}/{alias}")

    try:
        inst = find_instance_by_region_and_alias(region, alias)
        if not inst:
            print(f"未找到机器: {region}/{alias}")
            sys.exit(1)

        uuid = inst.get("uuid")
        status = str(inst.get("status", ""))
        print(f"找到目标机器，UUID: {uuid}，当前状态: {status}")

        # 即便已关机，仍尝试一次，API 会返回实际结果
        resp = power_off_instance(uuid)
        if resp.get("code") == "Success":
            print("机器关机成功")
            sys.exit(0)
        else:
            print(f"机器关机失败: {resp.get('msg') or resp}")
            sys.exit(1)

    except requests.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
