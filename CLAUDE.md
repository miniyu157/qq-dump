# QQ DUMP 项目简介

## 此处定义"代码应该怎么写"，不定义"业务规则是什么"。规范服务于业务表达，而非取代业务表达

规则优先级（当两条规则冲突时）
    1. 业务明确指定的约束（来自用户需求文本）> 本文件中的任何规则
    2. KISS / 不增加不必要复杂度 > 显式约束 > 单一数据源

**模块职责分离**
每个文件只做一件事。模块间仅通过公开接口通信，不可跨界访问内部实现。

**KISS — 不增加不必要复杂度**
只有一个实现时不需要接口，只有一个调用者时不需要通用化。
同一模式重复出现时再考虑抽象（经验阈值：3次，可根据团队情况调整）。
避免提前抽象。不为假设性的未来需求设计。内联优于间接。

**区分“实现代码“与“数据模型”**
删除代码前先分类。代码按性质分为两类，删除规则不同：
    - **实现代码**（逻辑、工具函数、helper、死代码）：确定未被调用 → 可删除。
    - **数据模型**（Schema、协议字段、类型定义、接口声明）：即使当前无调用者，也必须保留。数据结构描述的是客观事实，独立于消费它的代码。禁止以“当前未被调用“为由删除。
判定标准：这段代码是在 DO something（执行动作），还是在 DESCRIBE something（描述事实）？描述型代码受保护，执行型代码可删除。

**SSoT — 单一数据源**
同一份数据在系统中只有一个权威来源。需要多种表示形式时从源头派生，而非复制。常量、配置值集中定义。

**不硬编码**
会变化的值（阈值、URL、参数）通过配置或参数注入，禁止写死在逻辑中。

**快速失败 & 隐式约束禁止**
错误在最早时刻、最靠近源头处暴露。禁止吞错误。
禁止为错误输入添加 fallback / 默认值 / 自动修正——输入错了就报错，让调用方修正。
校验集中在系统边界处（用户输入、外部 API、跨模块接口）。模块内部信任类型系统和调用链——不在每层重复校验。
业务约束必须显式。换一个人读代码，能否不靠注释看懂所有业务约束？不能就必须重构。
禁止：
    - `Math.min(Math.max(x, 0), 100)` — 为什么是 0 和 100？约束必须命名。
    - `value || 10` — 默认值 10 是业务规则却无处声明。
    - `if (!count)` — 混淆 null 和 0。

**代码自解释**
代码自解释优先。注释只解释‘为什么（Why）’和‘业务上下文’，禁止解释‘做了什么（What）’——后者应通过命名和结构自明。
禁止在注释中引用会过时的上下文（任务名称、PR 编号、”为 X 功能添加“、”被 Y 调用”）——这些属于 commit message，不属于代码。
命名必须携带信息量。禁止用类型信息填充变量名（例如 `userList`、`dataObject`、`countValue`），类型系统已经说了的事不需要名字再说一遍。
禁止装饰性注释（ASCII 边框、分隔线、banner 风格块注释）。注释是工程文档，不是视觉设计。

**检查清单**
    1. 职责单一且不跨界？
    2. 数据是否已有单一来源？
    3. 是否有硬编码？
    4. 是否悄悄修正了调用方的错误输入？
    5. 是否存在隐式业务约束？
    6. 是否因简化而遗漏了需求中明确的要求？

## 整体架构

### 可执行文件 qqdump

qqdump 为 bash 编写的 CLI 工具，实现子命令：

* key   获取 JSON 格式的密钥到标准输出
* db    内部调用 key 命令获取密钥，然后解密需要的数据库
* chat  开发中

### Python 模块 dbtools

dbtools 是操作已解密数据库的数据交互后端，不被用户直接执行。

执行/测试方式: `python -m dbtools`

使用 Typer 库实现子命令分发，blackboxprotobuf 是核心的 protobuf 解析库，
非必要不引入额外依赖。

```plaintext
Web 前端（呈现层）
  路由 · 布局 · 交互 · 搜索/过滤 · 可视化
  不了解 QQNT 数据库结构、不知道 protobuf
      ↕ HTTP / WebSocket（结构化 JSON）
API Server（薄胶水层）
  端点路由 · 请求校验 · 响应序列化 · 缓存 · CORS
  不解析 protobuf、不直接写 SQL
      ↕ Python import（同进程）
dbtools（数据层，纯 Python 库）
  schema · 数据库连接 · SQL查询 · protobuf解码 · 数据变换
  不依赖任何 Web 框架、不处理 HTTP
```

**核心原则：** dbtools 不碰 HTTP，前端不碰数据库，中间 API Server 越薄越好。
API Server → dbtools 通过 Python import 同进程调用，不做进程间通信或 CLI 子进程。

### 技术栈选型

| 层 | 推荐 | 理由 |
| ------ | ------ | ------ |
| API Server | FastAPI | Python 异步、自动 OpenAPI、WebSocket 原生支持 |
| Web 前端 | HTMX + Alpine.js 或 React/Vue + Tailwind | 前者轻量适合数据展示密集型，后者复杂交互更强 |

---

## dbtools/schema

纯声明式、零依赖
不包含 ORM、不生成 SQL，只定义 QQNT 的数据形状。

类型层次（定义见 `base.py`）：
`Database` → `Table` → `Column`。
`Column` 可内嵌 `ProtoStruct` → `ProtoField`（BLOB 的 protobuf 结构），
以及 `EnumType` / `FlagsType`（INTEGER 列的语义映射）。

**模块结构：**

```plaintext
schema/
├── __init__.py       # 公开 API 导出
├── base.py           # 核心 dataclasses
└── profile_info/     # profile_info.db 的表定义
                      #   按实体拆分为独立文件，__init__.py 组装
```

**命名规则（核心约定）：** 目录、变量名从真实名称机械推导。

| 元素 | 规则 | 示例 |
| --- | --- | --- |
| 目录 | filename 去掉 `.db` | `profile_info.db` → `profile_info/` |
| Database 变量 | `replace(".", "_").upper()` | `PROFILE_INFO_DB` |
| Table 变量 | `name.upper()` | `BUDDY_LIST` |

**Example：新增数据库**
假设要添加 `group_info.db`，包含 `group_list` 表：

1. 创建 `schema/_group_info/` 子包，按实体拆分为独立文件
1. 在 `group.py` 中定义：

    ```python
    from ..base import Column, Table
    GROUP_LIST = Table(name="group_list", columns=[...])
    ```

1. 在 `_group_info/__init__.py` 组装：

    ```python
    from ..base import Database
    from .group import GROUP_LIST
    GROUP_INFO_DB = Database(filename="group_info.db", tables=[GROUP_LIST])
    ```

**关键约定：**

* `Column.id` 是 QQNT 的数字列名（如 `"1000"`），非语义列名
* `field_type` 使用 SQL 类型：`TEXT`、`INTEGER`、`BLOB`；
  `INTEGER?` 表示可为 NULL
* BLOB 列可附带 `proto: ProtoStruct` 描述内部 protobuf 结构
* 配置/系统类表（key-value 模式）统一归入 `config.py`，
  不与实体数据表混放

---

## dbtools/discover

从 SQLite 文件读取表和列的原始元数据，不含业务语义。
与声明层互补：schema 是预设知识，discover 是实际观察。

**类型语义：** `DBTable` 只是 `str`（表名），
`DBColumn` 只是 `{name, type}`（来自 `PRAGMA table_info`）。
`DB` 前缀标识"数据库自报"——这些类型描述 SQLite 文件里有什么，
不描述这些表/列的业务含义。

**公开函数（`sqlite.py`）：**

* `get_tables_by_files(*paths)` — 跨文件取用户表名并集，
  过滤 `sqlite_*` 和 `_fts*` 内部表
* `get_columns_by_files(*paths, table)` — 跨文件取指定表的列并集，
  按列名去重；文件不存在该表时静默跳过

---

## dbtools/types

查询和 protobuf 解码后的业务结果类型。
由 `info.py` / `groups.py` 等查询函数产出，被 CLI 命令直接使用。

**类型语义：** 这些类型描述"用户关心的实体"——
不感知数据来自哪张表、哪个列、是否经过 protobuf 解码。
同一类型可能由多表多列组合而成。

* `AccountInfo` — 用户账号信息（来自 `profile_info_v6` 表的多列）
* `FriendGroup` — 好友分组（来自 `category_list_v2` 的 BLOB 解码）
