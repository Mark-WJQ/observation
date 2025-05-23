# nginx2apisix_final.py
import re
import json
import argparse
import shlex
from pathlib import Path

class NginxConverter:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.upstreams = {}
        self.routes = []

    def parse_configs(self):
        print(f"\n=== 正在解析配置文件 ===")

        conf_files = list(self.config_dir.glob('*.conf'))
        print(f"找到 {len(conf_files)} 个配置文件: {[f.name for f in conf_files]}")
    
        # 提取所有upstream
        for conf_file in self.config_dir.glob('*.conf'):
            self._parse_upstreams(conf_file)
        
        # 处理路由规则
        for conf_file in self.config_dir.glob('*.conf'):
            self._parse_servers(conf_file)
        print(f"\n=== 解析结果 ===")
        print(f"Upstream数量: {len(self.upstreams)}")
        for name, servers in self.upstreams.items():
            print(f"  - {name}: {servers}")
        print(f"路由数量: {len(self.routes)}")
        for route in self.routes:
            print(f"  - {route['hosts']} -> {route['path']}")

    def _parse_upstreams(self, file: Path):
        content = file.read_text(encoding='utf-8-sig')  # 处理BOM头
            # 增强upstream正则，支持多行和注释
        upstream_pattern = re.compile(
            r'upstream\s+(\w+)\s*{'
            r'([^{}]*?(?:/\*.*?\*/)?[^{}]*?)}', 
            re.DOTALL
        )
        for match in upstream_pattern.finditer(content):
            name = match.group(1)
            servers = re.findall(
                r'server\s+([\d.]+):(\d+);/*[^\n]*', 
                match.group(2)
            )
            if servers:
                self.upstreams[name] = servers
                print(f"✅ 发现upstream: {name} → {servers}")


    def _parse_servers(self, file: Path):
        content = file.read_text()
        for server in re.finditer(r'server\s*{([^}]+)}', content, re.DOTALL):
            self._parse_server(server.group(1))

    def _parse_server(self, server_block: str):
        # 提取server配置
        server_name = re.search(r'server_name\s+([^;]+);', server_block)
        ssl_on = 'ssl on;' in server_block or 'listen 443 ssl' in server_block
        
        if not server_name:
            return
        
        # 处理location块
        for loc in re.finditer(r'location\s+([^{]+)\s*{([^}]+)}', server_block):
            self._parse_location(
                path=loc.group(1).strip(),
                config=loc.group(2),
                hosts=server_name.group(1).split(),
                ssl=ssl_on
            )

    def _parse_location(self, path: str, config: str, hosts: list, ssl: bool):
        # 提取关键配置
        proxy_pass = re.search(r'proxy_pass\s+(.+?);', config)
        if not proxy_pass:
            return
        
        # 解析upstream信息
        upstream, path_prefix = self._parse_proxy_pass(proxy_pass.group(1))
        if not upstream:
            return

        # 记录路由规则
        self.routes.append({
            "hosts": [h.strip() for h in hosts],
            "path": path,
            "upstream": upstream,
            "path_prefix": path_prefix,
            "ssl": ssl,
            "timeout": self._extract_timeout(config),
            "body_size": self._extract_body_size(config)
        })

    def _parse_proxy_pass(self, value: str) -> tuple:
        """解析proxy_pass结构，返回(upstream名称, 路径前缀)"""
        match = re.match(r'^(?:https?://)?([^/]+?)(?::\d+)?(/.+)?/?$', value)
        if not match:
            return None, None
        return match.group(1), (match.group(2) or '').rstrip('/')

    def _extract_timeout(self, config: str) -> dict:
        timeout = {}
        if connect := re.search(r'proxy_connect_timeout\s+(\d+)', config):
            timeout['connect'] = int(connect.group(1))
        if read := re.search(r'proxy_read_timeout\s+(\d+)', config):
            timeout['read'] = int(read.group(1))
        return timeout

    def _extract_body_size(self, config: str) -> str:
        if size := re.search(r'client_max_body_size\s+([\d]+[MmKk]?);', config):
            return size.group(1).upper()
        return None

    def generate_apisix_config(self) -> dict:
        return {
            "upstreams": self._generate_upstreams(),
            "routes": self._generate_routes()
        }

    def _generate_upstreams(self) -> list:
        upstreams = []
        for name, servers in self.upstreams.items():
            upstreams.append({
                "id": name,
                "name": name,
                "type": "roundrobin",
                "nodes": [{"host": s[0], "port": int(s[1]), "weight": 1} for s in servers],
                "timeout": {"connect": 6, "send": 6, "read": 6}
            })
        return upstreams

    def _generate_routes(self) -> list:
        routes = []
        for idx, route in enumerate(self.routes, 1000):
            # 自动补全缺失的upstream
            if route['upstream'] not in self.upstreams:
                self.upstreams[route['upstream']] = [("待配置", 80)]
                print(f"⚠️ 自动生成占位upstream: {route['upstream']}")

            # 构造路由配置
            routes.append({
                "id": f"route-{idx}",
                "name": f"{route['hosts'][0]} - {route['path']}",
                **self._build_uri_match(route['path']),
                "hosts": route['hosts'],
                "upstream_id": route['upstream'],
                "plugins": self._build_plugins(route),
                **self._build_timeout(route['timeout'])
            })
        return routes

    def _build_uri_match(self, path: str) -> dict:
        """构造路径匹配规则"""
        if path.startswith('='):
            return {"uri": path[1:]}
        elif path.startswith('~*'):
            return {"uri": f"/*{path[2:].strip()}*", "vars": [[ "uri", "~~*", path[2:].strip() ]]}
        elif path.startswith('~'):
            return {"uri": f"/*{path[1:].strip()}*", "vars": [[ "uri", "~~", path[1:].strip() ]]}
        else:
            return {"uri": f"{path.rstrip('/')}/*" if '/' in path else path}

    def _build_plugins(self, route: dict) -> dict:
        plugins = {}
        
        # 路径重写
        if route['path_prefix']:
            base_path = route['path'].rstrip('/') if not route['path'].startswith(('=','~')) else ''
            plugins["proxy-rewrite"] = {
                "regex_uri": [f"^{base_path}(/.*)$", f"{route['path_prefix']}\\1"]
            }

        # SSL处理
        if route['ssl']:
            plugins["ssl"] = { "https": True }

        # 请求体限制
        if route['body_size']:
            plugins["request-validation"] = {
                "body_size": route['body_size']
            }

        return plugins

    def _build_timeout(self, timeout: dict) -> dict:
        return {"timeout": timeout} if timeout else {}

def main():
    parser = argparse.ArgumentParser(
        description='Nginx到APISIX配置迁移工具',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='''示例用法:
  # 基本用法
  python nginx2apisix.py -d ./nginx_conf -o deploy.sh
  
  # 自定义Admin API
  python nginx2apisix.py -d /etc/nginx/conf.d \\
    --admin-url http://apisix-admin:9180 \\
    --admin-key my-secret-key'''
    )
    parser.add_argument('-d', '--dir', required=True, help='Nginx配置目录路径')
    parser.add_argument('-o', '--output', default='deploy_apisix.sh', help='输出脚本文件名')
    parser.add_argument('--admin_url', default='http://ci-apisix-admin.nucarf.tech', help='APISIX Admin API地址')
    parser.add_argument('--admin_key', default='edd1c9f034335f136f87ad84b625c8f1', help='APISIX Admin API密钥')
    args = parser.parse_args()

    # 执行转换
    converter = NginxConverter(Path(args.dir))
    converter.parse_configs()
    config = converter.generate_apisix_config()

    # 生成部署脚本
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(f"""#!/bin/bash
export ADMIN_KEY={shlex.quote(args.admin_key)}
export ADMIN_URL={shlex.quote(args.admin_url)}

# 创建上游
""")
        for up in config['upstreams']:
            f.write(f"""curl -sSf -X PUT "$ADMIN_URL/apisix/admin/upstreams/{up['id']}" \\
  -H "X-API-KEY: $ADMIN_KEY" \\
  -d '{json.dumps(up, ensure_ascii=False)}' || exit 1

""")

        f.write("\n# 创建路由\n")
        for route in config['routes']:
            f.write(f"""curl -sSf -X PUT "$ADMIN_URL/apisix/admin/routes/{route['id']}" \\
  -H "X-API-KEY: $ADMIN_KEY" \\
  -d '{json.dumps(route, ensure_ascii=False)}' || exit 1

""")

    # 输出使用提示
    safe_output = shlex.quote(str(Path(args.output).resolve()))
    print(f"\n✅ 迁移脚本已生成: {safe_output}")
    print(f"执行以下命令应用配置:")
    print(f"chmod +x {safe_output}")
    print(f"./{safe_output}")

if __name__ == '__main__':
    main()
