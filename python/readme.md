# APISIX 配置同步工具使用手册

## 📦 简介
本工具用于在不同环境（如测试/生产）的 APISIX 实例之间同步路由及其关联资源（上游服务、插件配置、消费者等），支持：
- 自动发现路由依赖关系
- 配置字段覆盖
- ID 映射与冲突检测
- 单任务/批量任务模式

---

## ⚙️ 安装依赖
```bash
pip install requests
```

---

## 🚀 使用方式

### 单任务模式
```bash
python apisix_sync.py \
    --routeid <路由ID> \
    [--upstreamid <上游ID>] \
    [--serviceid <服务ID>] \
    [--pluginconfid <插件配置ID>] \
    [--consumerid <消费者ID>] \
    [--override <JSON格式的配置覆盖>]
```

### 批量模式
```bash
python apisix_sync.py --batch-file <批量任务文件.json>
```

---

## 🧾 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--routeid` | string | ✅ | 要同步的路由ID（必填） |
| `--upstreamid` | string | ❌ | 手动指定上游服务ID |
| `--serviceid` | string | ❌ | 手动指定服务ID |
| `--pluginconfid` | string | ❌ | 手动指定插件配置ID |
| `--consumerid` | string | ❌ | 手动指定消费者ID |
| `--override` | JSON字符串 | ❌ | 配置覆盖规则（见下方格式说明） |
| `--batch-file` | string | ❌ | 批量任务文件路径 |

### 环境变量配置
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `APISIX_OFFLINE_URL` | `http://ci-apisix-admin.nucarf.tech` | 线下环境地址 |
| `APISIX_ONLINE_URL` | `http://qa-apisix-admin.nucarf.tech` | 线上环境地址 |
| `APISIX_OFFLINE_ADMIN_KEY` | `edd1c9f034335f136f87ad84b625c8f1` | 线下环境API密钥 |
| `APISIX_ONLINE_ADMIN_KEY` | `edd1c9f034335f136f87ad84b625c8f1` | 线上环境API密钥 |

---

## 📄 参数详解

### 1. `--override` 配置覆盖规则
采用 JSON 格式，支持以下语法：
```json
{
  "routes": {
    "id": "prod_route_001",    // 指定新ID
    "host": "api.example.com", // 修改域名
    "plugins": {
      "rate-limiting": {
        "rate": 200           // 修改插件配置
      }
    }
  },
  "upstreams": {
    "id": "prod_upstream",
    "nodes": [               // 修改上游节点
      {"host": "10.0.0.1"}
    ]
  }
}
```

### 2. 批量任务文件格式
```json
{
  "tasks": [
    {
      "routeid": "route_001",
      "upstreamid": "upstream_001",
      "override": {
        "routes": {"host": "new.domain.com"},
        "upstreams": {"nodes": [{"host": "10.0.0.1"}]}
      }
    },
    {
      "routeid": "route_002",
      "override": {
        "routes": {"id": "new_route_id"} // 仅替换ID
      }
    }
  ]
}
```

---

## 📚 使用示例

### 示例1：基础同步
```bash
python apisix_sync.py --routeid dev_route_001
```
同步 dev 环境的 `dev_route_001` 路由及其关联资源（自动发现上游/服务等）

### 示例2：带配置覆盖
```bash
python apisix_sync.py \
    --routeid dev_route_001 \
    --override '{
        "routes": {
            "id": "prod_route_001",
            "host": "api.prod.com"
        },
        "upstreams": {
            "nodes": [{"host": "10.0.0.1"}]
        }
    }'
```
同步时：
- 将路由ID改为 `prod_route_001`
- 修改域名到 `api.prod.com`
- 替换上游节点IP

### 示例3：批量同步
```bash
python apisix_sync.py --batch-file batch_tasks.json
```

**batch_tasks.json** 内容：
```json
{
  "tasks": [
    {
      "routeid": "route_001",
      "override": {
        "routes": {"id": "prod_route_001"},
        "upstreams": {"nodes": [{"host": "10.0.0.1"}]}
      }
    },
    {
      "routeid": "route_002",
      "override": {
        "routes": {"host": "h5.prod.com"}
      }
    }
  ]
}
```

---

## ⚠️ 注意事项

1. **环境变量**  
   可通过环境变量自定义环境配置：
   ```bash
   export APISIX_OFFLINE_URL=http://dev.apisix.admin
   export APISIX_ONLINE_URL=http://prod.apisix.admin
   ```

2. **冲突处理**  
   如果遇到线上已存在同名资源，会输出类似提示：
   ```
   !!!!!!!!!!!!!!!! 冲突报告 !!!!!!!!!!!!!!!!
   - routes: prod_route_001
   - upstreams: dev_upstream
   请通过 --override 参数修改这些资源的ID：
   {
     "routes": {"id": "new_prod_route_001"},
     "upstreams": {"id": "new_dev_upstream"}
   }
   ```

3. **字段清理**  
   自动移除 `create_time` 和 `update_time` 等只读字段

4. **路由状态**  
   自动启用路由（设置 `status: 0`）

5. **安全机制**  
   不会覆盖已有配置，遇到冲突资源会提示重新指定ID

---

## 🧪 常见问题排查

1. **权限问题**  
   ```bash
   {"message":"invalid API key"}
   ```
   解决方案：检查 `X-API-KEY` 的值是否与 APISIX 配置一致

2. **依赖缺失**  
   ```bash
   "未找到任何关联资源"
   ```
   解决方案：确认路由是否关联了上游/插件等必要配置

3. **JSON格式错误**  
   ```bash
   "覆盖配置必须是有效的JSON格式"
   ```
   解决方案：使用 [JSON校验工具](https://jsonlint.com/) 检查格式

---

## 📐 同步顺序
1. 消费者（Consumers）
2. 上游服务（Upstreams）
3. 插件配置（Plugin Configs）
4. 服务（Services）
5. 路由（Routes）

---

## 📝 输出日志说明
| 日志前缀 | 说明 |
|----------|------|
| `[INFO]` | 操作步骤 |
| `[SUCCESS]` | 成功信息 |
| `[PROCESS]` | 处理步骤 |
| `[OVERRIDE]` | 配置覆盖 |
| `[SYNC]` | 同步操作 |
| `[WARNING]` | 冲突警告 |
| `[FAILED]` | 错误信息 |

---

## 📦 目录结构建议
```
/apisix-sync/
├── apisix_sync.py          # 主程序
├── batch_tasks.json       # 批量任务文件（示例）
└── .env                   # 环境变量配置（可选）
```

---

## 💡 最佳实践
1. **测试环境**：先用 `--override` 指定新ID进行测试
2. **生产环境**：使用批量文件集中管理同步任务
3. **版本控制**：将批量任务文件纳入 Git 管理
4. **自动化**：可配合 CI/CD 流程使用

---

## 📚 相关文档
- [APISIX Admin API 文档](https://apisix.apache.org/docs/apisix/admin-api/)
- [JSON 格式说明](https://www.json.org/json-en.html)
- [正则表达式教程](https://regex101.com/)