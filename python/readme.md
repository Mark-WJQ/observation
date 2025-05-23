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
采用 JSON 格式，支持以下语法（新增完整资源类型示例）：

#### 🔄 资源类型完整示例
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
      {"host": "10.0.0.1", "weight": 100}
    ]
  },
  "consumers": {
    "id": "prod_consumer",   // 指定新ID
    "plugins": {
      "key-auth": {          // 更新认证插件
        "key": "new_api_key"
      }
    }
  },
  "plugin_configs": {
    "id": "prod_plugin_conf",// 指定新ID
    "plugins": {
      "jwt": {               // 完整插件配置覆盖
        "secret": "new_secret_key"
      }
    }
  },
  "services": {
    "id": "prod_service",    // 指定新ID
    "timeout": {             // 修改超时设置
      "connect": 6000,
      "read": 6000
    }
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
        "routes": {"id": "prod_route_001"},
        "upstreams": {
          "id": "prod_upstream",
          "nodes": [{"host": "10.0.0.1"}]
        },
        "consumers": {
          "id": "prod_consumer",
          "plugins": {
            "key-auth": {"key": "new_api_key"}
          }
        },
        "plugin_configs": {
          "plugins": {
            "jwt": {"secret": "new_secret_key"}
          }
        }
      }
    },
    {
      "routeid": "route_002",
      "override": {
        "routes": {
          "host": "h5.prod.com",
          "plugins": {
            "redirect": {
              "http_to_https": true
            }
          }
        },
        "services": {
          "timeout": {
            "connect": 5000
          }
        }
      }
    }
  ]
}
```

---

## 📚 使用示例

### 示例4：同步消费者配置
```bash
python apisix_sync.py \
    --routeid dev_route_001 \
    --override '{
        "consumers": {
            "id": "prod_consumer",
            "plugins": {
                "key-auth": {
                    "key": "new_api_key"
                }
            }
        }
    }'
```
同步时：
- 将消费者ID改为 `prod_consumer`
- 更新认证密钥为 `new_api_key`

### 示例5：同步插件配置
```bash
python apisix_sync.py \
    --routeid dev_route_001 \
    --override '{
        "plugin_configs": {
            "plugins": {
                "jwt": {
                    "secret": "new_secret_key",
                    "exp": 3600
                }
            }
        }
    }'
```
同步时：
- 使用新ID创建插件配置
- 更新JWT签名密钥和过期时间

---

## ⚠️ 注意事项

### 新增资源类型处理说明
1. **消费者冲突**  
   ```bash
   !!!!!!!!!!!!!!!! 冲突报告 !!!!!!!!!!!!!!!!
   - consumers: prod_consumer
   请通过 --override 参数修改消费者ID：
   {
     "consumers": {"id": "new_prod_consumer"}
   }
   ```

2. **插件配置冲突**  
   ```bash
   !!!!!!!!!!!!!!!! 冲突报告 !!!!!!!!!!!!!!!!
   - plugin_configs: dev_plugin_conf
   请通过 --override 参数修改插件配置ID：
   {
     "plugin_configs": {"id": "new_plugin_conf"}
   }
   ```

3. **字段覆盖优先级**  
   所有字段覆盖遵循：
   - 先应用ID映射
   - 再合并其他字段
   - 插件配置深度合并

---

## 🧪 常见问题排查

### 新增资源类型问题
1. **消费者缺失**  
   ```bash
   "Failed to get route dependencies: consumer_id not found"
   ```
   解决方案：确认路由是否启用了认证插件（如jwt/key-auth）

2. **插件配置无效字段**  
   ```bash
   "同步失败：400 - invalid configuration"
   ```
   解决方案：检查插件配置字段是否符合插件要求（如jwt需要secret字段）

---

## 📐 同步顺序（完整版）
1. 消费者（Consumers）
2. 上游服务（Upstreams）
3. 插件配置（Plugin Configs）
4. 服务（Services）
5. 路由（Routes）

---

## 📝 输出日志说明（新增资源类型）
| 日志前缀 | 示例输出 | 说明 |
|----------|---------|------|
| `[INFO]` | `正在查询线下consumers/prod_consumer...` | 显示各资源类型处理 |
| `[SUCCESS]` | `获取到有效配置\n{"username": "test_user"}` | 展示各资源原始配置 |
| `[OVERRIDE]` | `应用自定义配置覆盖：{"plugins": {"key-auth": {"key": "new_api_key"}}` | 显示各资源类型覆盖 |

---

## 💡 最佳实践（新增部分）
1. **消费者管理**  
   ```bash
   # 批量任务文件中统一修改消费者ID
   {
     "tasks": [
       {
         "routeid": "route_001",
         "override": {
           "consumers": {
             "id": "prod_${consumer_id}",  // 使用原始ID作为前缀
             "plugins": {
               "key-auth": {
                 "key": "prod_${consumer_id}_key"  // 动态生成密钥
               }
             }
           }
         }
       }
     ]
   }
   ```

2. **插件配置版本控制**  
   ```bash
   # 为不同环境指定插件版本
   {
     "override": {
       "plugin_configs": {
         "plugins": {
           "rate-limiting": {
             "rate": 500,  // 开发环境限制较低
             "burst": 100
           }
         }
       }
     }
   }
   ```

---

## 📚 相关文档
- [APISIX Consumer 文档](https://apisix.apache.org/docs/apisix/consumer/)
- [APISIX Plugin Config 文档](https://apisix.apache.org/docs/apisix/plugin-config/)
- [APISIX Plugin List](https://apisix.apache.org/docs/apisix/plugins/bundled-plugins/)