"""
它会不断检查，直到可以开机，然后它会执行开机
一般情况下，运行它，然后喝一杯热牛奶，刷刷视频或者干点别的，直到它成功开机。
有可能是几分钟，也有可能是1小时，也许是4小时。不过，它总能在其他同学关机的第一时间执行开机，然后那位同学会发出尖锐的爆鸣。
"""

import os
import time
import random
import requests

def get_headers():
    token = os.environ.get('AUTODL_TOKEN')
    if not token:
        raise ValueError("请先设置AUTODL_TOKEN环境变量")
        
    return {
        'authority': 'www.autodl.com',
        'authorization': token,
        'content-type': 'application/json;charset=UTF-8',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
        'accept': '*/*',
        'origin': 'https://www.autodl.com',
        'referer': 'https://www.autodl.com/console/instance/list'
    }

def get_instances():
    url = 'https://www.autodl.com/api/v1/instance'
    data = {
        "date_from": "",
        "date_to": "",
        "page_index": 1,
        "page_size": 10,
        "status": [],
        "charge_type": []
    }
    
    response = requests.post(url, headers=get_headers(), json=data)
    return response.json()

def power_on_instance(instance_uuid):
    url = 'https://www.autodl.com/api/v1/instance/power_on'
    data = {"instance_uuid": instance_uuid}
    
    response = requests.post(url, headers=get_headers(), json=data)
    return response.json()

def main():
    # 获取用户输入
    target = input("请输入要启动的机器 (格式: 区域/机器名称, 例如: V100专区/01机): ")
    region, machine = [x.strip() for x in target.split('/')]
    
    print(f"开始监控机器: {target}")
    
    while True:
        try:
            response = get_instances()
            if response['code'] != 'Success':
                print(f"获取实例列表失败: {response['msg']}")
                continue
                
            # 查找目标机器
            for instance in response['data']['list']:
                if instance['region_name'] == region and instance['machine_alias'] == machine:
                    print(f"找到目标机器, UUID: {instance['uuid']}, 所需GPU: {instance['req_gpu_amount']}, 当前GPU: {instance['gpu_idle_num']}")
                    
                    if instance['gpu_idle_num'] >= instance['req_gpu_amount']:
                        print("GPU可用，尝试启动机器...")
                        power_result = power_on_instance(instance['uuid'])
                        
                        if power_result['code'] == 'Success':
                            print("机器启动成功！")
                            return
                        else:
                            print(f"机器启动失败: {power_result['msg']}")
                    else:
                        print("GPU暂不可用，继续等待...")
                    break
            else:
                print(f"未找到机器: {target}")
                
        except Exception as e:
            print(f"发生错误: {e}")
            
        # 随机等待1-5秒
        wait_time = random.uniform(1, 5)
        print(f"等待 {wait_time:.1f} 秒后重试...")
        time.sleep(wait_time)

if __name__ == "__main__":
    main()
