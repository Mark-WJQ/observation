import os
import argparse
import requests
import json

def sync_resource(offline_url, online_url, offline_key, online_key, resource_type, resource_id, override_config=None,existing_resources=None):
    
    # 从覆盖配置获取目标ID
    target_id = None
    if override_config and resource_type in override_config:
        target_id = override_config[resource_type].get("id", None)  # 提取并移除ID字段
    target_id = target_id or resource_id

    # Check if resource already exists in online environment
    check_url = f"{online_url}/apisix/admin/{resource_type}/{target_id}"
    exists = False
    try:
        check_resp = requests.get(check_url, headers={"X-API-KEY": online_key})
        if check_resp.status_code == 200:
            exists = True
            if existing_resources is not None:
                existing_resources.append( (resource_type, target_id) )
            return exists
    except requests.exceptions.RequestException as e:
        pass  # 忽略检查错误
    


    # 获取线下配置
    get_url = f"{offline_url}/apisix/admin/{resource_type}/{resource_id}"
    print(f"[INFO] 正在查询线下{resource_type}/{resource_id}...")
    try:
        resp = requests.get(get_url, headers={"X-API-KEY": offline_key})
        resp_data = resp.json()

        # 判断资源是否存在（新版APISIX响应结构）
        if resp.status_code == 404 or "Key not found" in resp_data.get("message", ""):
            raise Exception(f"线下{resource_type} {resource_id} 不存在")
        elif resp.status_code != 200:
            raise Exception(f"接口响应异常：{resp.status_code} - {resp_data.get('message', '未知错误')}")

        # 新版数据结构直接使用 value 字段
        if "value" not in resp_data:
            raise Exception("响应数据结构异常，缺少value字段")
            
        config_data = resp_data["value"]
        print(f"[SUCCESS] 获取到有效配置\n{json.dumps(config_data, indent=2, ensure_ascii=False)}")

        removed_fields = []
        for field in ['create_time', 'update_time']:
            if config_data.pop(field, None) is not None:
                removed_fields.append(field)
        
        print(f"[PROCESS] 已清理临时字段：{removed_fields or '无'}")

        if override_config:
            print(f"[OVERRIDE] 应用自定义配置覆盖：{override_config.get(resource_type, {})}")
            config_data = deep_update(config_data, override_config.get(resource_type, {}))
            print(f"合并后配置:\n{json.dumps(config_data, indent=2, ensure_ascii=False)}")

    except json.JSONDecodeError:
        raise Exception("响应数据非JSON格式，请检查APISIX服务状态")
    except Exception as e:
        raise Exception(f"配置查询失败：{str(e)}")

    # 强制启用路由状态（如果字段存在）
    if resource_type == "routes":
        config_data["status"] = 0
        print(f"[ACTION] 已设置路由状态为下线")


    # 同步到线上环境
    put_url = f"{online_url}/apisix/admin/{resource_type}/{target_id}"
    print(f"[SYNC] 开始同步到线上环境...{put_url}")
    
    try:
        resp = requests.put(
            put_url,
            json=config_data,  # 保持与查询结果相同的结构
            headers={"X-API-KEY": online_key}
        )
        
        if resp.status_code not in [200, 201]:
            err_msg = f"同步失败：{resp.status_code} - {resp.text[:200]}"
            raise Exception(err_msg)

        # 解析新版响应结构
        print(f"[SUCCESS] 同步成功到 {target_id or resource_id}")
        print(f"[SUCCESS] 同步成功 | 新版本号：{resp.json()}")
        return True

    except Exception as e:
        raise Exception(f"同步过程异常：{str(e)}")


def deep_update(original, update):
    """深度合并字典"""
    for key, value in update.items():
        print(f"[PROCESS] 应用自定义配置覆盖：{key}")
        if isinstance(value, dict) and key in original:
            original[key] = deep_update(original.get(key, {}), value)
        else:
            original[key] = value
    return original
def get_related_resources(offline_url, offline_key, route_id):
    """Automatically discover related resources from route data"""
    route_url = f"{offline_url}/apisix/admin/routes/{route_id}"
    try:
        resp = requests.get(route_url, headers={"X-API-KEY": offline_key})
        resp.raise_for_status()
        route_data = resp.json()["value"]
        
        return {
            "upstream_id": route_data.get("upstream_id"),
            "service_id": route_data.get("service_id"),
            "plugin_config_id": route_data.get("plugin_config_id"),
            "consumer_id": _get_consumer_id(route_data)
        }
    except Exception as e:
        raise Exception(f"Failed to get route dependencies: {str(e)}")

def _get_consumer_id(route_data):
    """Extract consumer ID from authentication plugins"""
    plugins = route_data.get("plugins", {})
    for auth_type in ["jwt", "key-auth", "basic-auth"]:
        if auth_type in plugins:
            return plugins[auth_type].get("consumer_id")
    return None


def process_single_task(task_config, global_config):
    """处理单个同步任务"""
    existing_resources = []
    
    # 从任务配置中获取参数
    route_id = task_config['routeid']
    ##override = task_config.get('override', {})
    
    # [原有资源获取和同步逻辑...]
      # 解析覆盖配置
    override_config = task_config.get('override', {})
    ##if override:
    #    try:
    #         override_config = json.loads(override)
    #         print(f"[CONFIG] 加载覆盖配置: {override_config}")
    #     except json.JSONDecodeError:
    #         raise Exception("覆盖配置必须是有效的JSON格式")
    
    

    try:
        print("\n" + "="*50 + " 配置同步流程开始 " + "="*50)
        print(f"[CONFIG] 加载覆盖配置: {override_config}")  # 添加调试日志

        existing_resources = []  # 新增：存储冲突资源
        
        # 获取资源ID（手动指定优先，否则自动发现）
        auto_resources = get_related_resources(global_config["offline_url"], global_config["offline_key"], route_id)
        
        final_resources = {
            "upstream_id": task_config.get('upstreamid',None) or auto_resources["upstream_id"],
            "service_id": task_config.get('serviceid',None) or auto_resources["service_id"],
            "plugin_config_id": task_config.get('pluginconfid',None) or auto_resources["plugin_config_id"],
            "consumer_id": task_config.get('consumerid',None) or auto_resources["consumer_id"]
        }

        # 验证至少有一个有效资源
        if not any(final_resources.values()):
            raise Exception("未找到任何关联资源，请检查路由配置或手动指定资源ID")

        # 定义同步顺序
        sync_sequence = [
            ("consumers", final_resources["consumer_id"]),
            ("upstreams", final_resources["upstream_id"]),
            ("plugin_configs", final_resources["plugin_config_id"]),
            ("services", final_resources["service_id"]),
            ("routes", route_id)
        ]

        for res_type, res_id in sync_sequence:
            if res_id:
                exists = sync_resource(
                    global_config["offline_url"],
                    global_config["online_url"],
                    global_config["offline_key"],
                    global_config["online_key"],
                    res_type,
                    res_id,
                    override_config=override_config,  # 传递覆盖配置
                    existing_resources=existing_resources
                )
                if exists:
                    print(f"[WARNING] {res_type}/{res_id} 在线上环境已存在")
                print("-"*50)
        if existing_resources:
            print("\n" + "!"*50 + " 冲突报告 " + "!"*50)
            for res_type, res_id in existing_resources:
                print(f"- {res_type.ljust(15)} {res_id}")
            print(f"\n请通过 --override 参数修改这些资源的ID：")
            print(json.dumps(
                {res_type: {"id": f"new_{res_id}"} for res_type, res_id in existing_resources},
                indent=2, ensure_ascii=False
            ))
            print("!"*50 + "\n")
        print("="*50 + " 同步成功 " + "="*50 + "\n")
        return existing_resources
    except Exception as e:
        print(f"\n[FAILED] 同步失败：{str(e)}")
        exit(1)




    
    return existing_resources

def print_batch_summary(success, total, existing):
    print(f"\n{'#'*30} 批量处理完成 {'#'*30}")
    print(f"成功: {success}/{total}")
    print(f"失败: {total - success}")
    
    if existing:
        print("\n冲突资源汇总:")
        for res_type, res_id in existing:
            print(f"- {res_type}: {res_id}")
        print("使用以下模板修改冲突ID:")
        print(json.dumps(
            {res_type: {"id": f"new_{res_id}"} for res_type, res_id in existing},
            indent=2, ensure_ascii=False
        ))

def main():
    parser = argparse.ArgumentParser(description='APISIX配置同步工具')
    parser.add_argument('--routeid', help="单个路由ID（与--batch-file互斥）")
    parser.add_argument('--batch-file', help="批量任务JSON文件路径")
    parser.add_argument('--upstreamid', help="手动指定upstream ID（可选）")
    parser.add_argument('--serviceid', help="手动指定service ID（可选）")
    parser.add_argument('--pluginconfid', help="手动指定plugin config ID（可选）")
    parser.add_argument('--consumerid', help="手动指定consumer ID（可选）")
    parser.add_argument('--override', type=str, help='JSON格式的配置覆盖规则，例：{"routes": {"host":"newexample.com"}, "upstreams": {"nodes": [{"host":"10.0.0.1"}]}}')

    
    args = parser.parse_args()


    config = {
        "offline_url": os.getenv("APISIX_OFFLINE_URL", ""),
        "online_url": os.getenv("APISIX_ONLINE_URL", ""),
        "offline_key": os.getenv("APISIX_OFFLINE_ADMIN_KEY", ""),
        "online_key": os.getenv("APISIX_ONLINE_ADMIN_KEY", "")
    }

     # 新增批量处理逻辑
    if args.batch_file:
        with open(args.batch_file, 'r') as f:
            batch_config = json.load(f)
        
        total = len(batch_config.get('tasks', []))
        success_count = 0
        all_existing = []
        
        print(f"\n{'#'*30} 开始批量处理 {total} 个任务 {'#'*30}")
        for idx, task in enumerate(batch_config['tasks'], 1):
            try:
                print(f"\n{'='*30} 处理任务 {idx}/{total} ({task['routeid']}) {'='*30}")
                existing = process_single_task(task, config)
                all_existing.extend(existing)
                success_count += 1
            except Exception as e:
                print(f"[SKIPPED] 任务失败: {str(e)}")
        
        print_batch_summary(success_count, total, all_existing)
    else:
        # 原有单个任务处理逻辑

        override_config = {}
        if args.override:
            try:
                override_config = json.loads(args.override)
            except json.JSONDecodeError:
                raise Exception("覆盖配置必须是有效的JSON格式")
        task_config = {
            'routeid': args.routeid,
            'upstreamid': args.upstreamid,
            'serviceid': args.serviceid,
            'pluginconfid': args.pluginconfid,
            'consumerid': args.consumerid,
            'override': override_config  # 使用转换后的字典
        }
        process_single_task(task_config, config)


if __name__ == "__main__":
    main()