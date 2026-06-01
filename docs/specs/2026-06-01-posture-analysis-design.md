# 体态分析模块 MVP 设计文档

> 版本: v1.0
> 日期: 2026-06-01
> 状态: 设计完成，待实现

---

## 1. 项目概述

### 1.1 产品定位

面向健身人群的体态分析 App。核心差异化：**基于用户个体体态问题，提供针对性的自测引导和纠正方案**，而非大众化通用建议。

### 1.2 MVP 范围

本次仅实现**体态分析模块**。训练计划、饮食推荐后续开发。

### 1.3 目标用户

- 有健身习惯但存在体态问题的人群
- 久坐办公族（程序员、白领）
- 对自身体态有疑虑但不知从何入手的人

---

## 2. 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| App 端 | Flutter (Dart) | iOS + Android 双端 |
| 状态管理 | Riverpod | 类型安全、可测试 |
| 3D 渲染 | model_viewer_plus | GLB 模型交互展示 |
| 后端 | Python FastAPI | 单体模块化服务 |
| 数据库 | PostgreSQL | 用户数据 + 分析记录 |
| AI 视觉分析 | Qwen VL (阿里百炼) | 图片体态判定 |
| 图片存储 | 阿里云 OSS | App 直传，不经后端 |
| 3D 模型素材 | MakeHuman (CC0) | 无版权风险 |
| 自测示意图 | AI 生成（统一风格） | 深色背景+人体轮廓+彩色标注 |

---

## 3. 系统架构

```
┌─────────────────┐     HTTPS/REST      ┌──────────────────────┐
│   Flutter App    │ ◄──────────────────► │  FastAPI 服务          │
│  (iOS + Android) │                     │  (单体, 模块化)         │
└─────────────────┘                     └────────┬─────────────┘
                                                 │
                    ┌────────────────────────────┼──────────────┐
                    │                            │              │
                    ▼                            ▼              ▼
             ┌──────────┐              ┌──────────────┐  ┌──────────┐
             │PostgreSQL│              │ 阿里云 OSS    │  │ Qwen VL  │
             │ (主数据库) │              │ (图片存储)    │  │ (阿里百炼) │
             └──────────┘              └──────────────┘  └──────────┘
```

### 3.1 核心原则

- App 和 API 之间纯 REST 通信，所有业务逻辑在后端完成
- 图片上传走 OSS 直传（STS 临时凭证），不经过后端中转
- Qwen VL 调用只在后端发生，API Key 不暴露到客户端
- API 路由版本化 `/api/v1/`
- 内部按模块分目录，未来可拆微服务

---

## 4. 用户流程

```
注册/登录（手机号+短信验证码）
       ↓
填写基础信息（身高/体重/性别/年龄）
       ↓
首页：3D 人体导航入口
（MakeHuman 模型，深色背景，可旋转，4个高亮可点击区域）
       ↓
点击区域 → 进入该分类的体态问题列表
（如点击肩胸区 → 显示：圆肩、翼状肩胛、驼背…）
       ↓
选择一个问题 → 进入详情页
（定义 + 典型表现 + 成因 + "开始自测"按钮）
       ↓
自测引导（文字步骤 + AI生成静态示意图）
├── 简单自测：按步骤操作，用户自判（选择：阳性/阴性/不确定）
└── AI辅助自测（可选）：拍照上传 → Qwen VL 分析
       ↓
三档结果输出
├── ✅ 正常/轻微 → 预防建议
├── ⚠️ 中度 → 纠正方法展示（拉伸+强化+习惯改变）
└── 🚩 重度/红旗征 → 强制引导就医提示
       ↓
关联推荐（基于关联矩阵 weight 值）
"你可能还需要关注：骨盆前倾（强关联）"
       ↓
结果保存到个人档案（历史记录）
```

---

## 5. 页面结构

### 5.1 页面清单

| 页面 | 路由 | 说明 |
|------|------|------|
| 注册页 | `/register` | 手机号 + 验证码注册 |
| 登录页 | `/login` | 手机号 + 验证码登录 |
| 信息采集页 | `/onboarding` | 首次登录填写身高/体重/性别/年龄 |
| 首页/3D导航 | `/home` | MakeHuman 模型，4个可点击区域 |
| 问题列表 | `/issues/:category` | 某区域下的问题卡片列表 |
| 问题详情 | `/issues/:id` | 定义、典型表现、成因、自测入口 |
| 自测流程 | `/issues/:id/test` | 步骤式引导（文字+图片），底部选择按钮 |
| AI拍照分析 | `/issues/:id/photo` | 相机/相册选图 → 上传 → AI判定 |
| 结果页 | `/issues/:id/result` | 三档结果 + 纠正方法 + 关联推荐 |
| 历史记录 | `/history` | 时间线展示历次自测结果 |
| 个人中心 | `/profile` | 基本信息、修改资料 |

### 5.2 3D 导航交互

MakeHuman 模型按 4 个区域划分 hotspot：

| 区域 | 对应问题分类 | 涵盖问题数 |
|------|------------|:--:|
| 头颈区 | 头颈部 | 3 项 |
| 肩胸区 | 肩部 + 上交叉 + 驼背/平背 + 肋骨外翻 | 7 项 |
| 骨盆腰区 | 骨盆 + 下交叉 + 脊柱侧弯/摇摆背 | 7 项 |
| 下肢区 | 膝部 + 足踝 | 7 项 |

（共 26 项，其中分层综合征和短信颈归入 compound 分类，作为"综合评估"独立入口展示在首页，合计 2 项）

---

## 6. 后端模块结构

```
app/
├── main.py                 # FastAPI 入口
├── auth/                   # 认证模块
│   ├── router.py           # POST /api/v1/auth/send-code, /login, /register
│   ├── service.py          # 验证码生成/校验、JWT签发
│   ├── models.py           # User ORM模型
│   └── schemas.py          # Pydantic 请求/响应模型
├── user/                   # 用户信息模块
│   ├── router.py           # GET/PUT /api/v1/user/profile
│   ├── service.py          # CRUD
│   └── schemas.py
├── posture/                # 体态分析核心模块
│   ├── router.py           # GET /issues, GET /issues/:id, POST /assess
│   ├── service.py          # 评估业务逻辑
│   ├── models.py           # PostureAssessment ORM
│   ├── schemas.py
│   ├── ai_service.py       # Qwen VL 调用封装
│   └── knowledge.py        # 25个问题的结构化数据（JSON）
├── upload/                 # OSS 上传模块
│   ├── router.py           # POST /api/v1/upload/sts-token
│   └── service.py          # STS 临时凭证生成
├── db/                     # 数据库
│   ├── database.py         # 连接池配置
│   └── migrations/         # Alembic 迁移
└── core/                   # 公共基础
    ├── config.py           # 环境变量/配置
    ├── security.py         # JWT 工具函数
    ├── dependencies.py     # FastAPI 依赖注入
    └── exceptions.py       # 全局异常处理
```

---

## 7. API 设计

### 7.1 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/send-code` | 发送短信验证码 |
| POST | `/api/v1/auth/register` | 注册（手机号+验证码） |
| POST | `/api/v1/auth/login` | 登录（手机号+验证码） |
| POST | `/api/v1/auth/refresh` | 刷新 JWT Token |

认证方式：JWT Bearer Token（Access Token 2h + Refresh Token 7d）

短信服务商：阿里云短信服务（与 OSS 同一账号体系，统一管理）

### 7.2 用户

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/user/profile` | 获取个人信息 |
| PUT | `/api/v1/user/profile` | 更新个人信息（身高/体重等） |

### 7.3 体态分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/posture/issues` | 获取全部问题列表（支持 ?category= 筛选） |
| GET | `/api/v1/posture/issues/:id` | 获取单个问题详情（含自测步骤） |
| POST | `/api/v1/posture/assess` | 提交自测结果（自判） |
| POST | `/api/v1/posture/assess/photo` | 提交照片进行 AI 分析 |
| GET | `/api/v1/posture/history` | 获取用户历史评估记录 |
| GET | `/api/v1/posture/issues/:id/related` | 获取关联问题推荐 |

### 7.4 上传

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/upload/sts-token` | 获取 OSS 临时上传凭证 |

---

## 8. 数据模型

### 8.1 数据库表

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) UNIQUE NOT NULL,
    height DECIMAL(5,1),          -- 身高 cm
    weight DECIMAL(5,1),          -- 体重 kg
    age INTEGER,
    gender VARCHAR(10),           -- male/female
    membership_level VARCHAR(20) DEFAULT 'free',  -- 预留付费扩展
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 体态评估记录表
CREATE TABLE posture_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    issue_id VARCHAR(20) NOT NULL,        -- 如 "HN-01"
    method VARCHAR(20) NOT NULL,          -- self_test / ai_photo
    result VARCHAR(20) NOT NULL,          -- normal / moderate / severe
    self_test_answers JSONB,              -- 用户自测选择记录
    ai_response JSONB,                    -- Qwen VL 原始返回
    photo_keys JSONB,                     -- OSS 图片 key 数组
    created_at TIMESTAMP DEFAULT NOW()
);

-- 验证码临时存储（可用 Redis 替代）
CREATE TABLE verification_codes (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    code VARCHAR(6) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 8.2 体态问题数据结构（hardcoded JSON）

每个问题遵循 issue.md 中定义的 JSON Schema：

```json
{
  "id": "HN-01",
  "name_cn": "头部前倾",
  "name_en": "Forward Head Posture",
  "abbr": "FHP",
  "category": "head_neck",
  "aliases": ["乌龟颈", "探颈"],
  "definition": "耳垂落于肩峰垂线前方，颈椎下段屈曲、上段过伸",
  "severity_levels": ["轻度", "中度", "重度"],
  "causes": [...],
  "self_tests": [
    {
      "name": "靠墙站立测试",
      "steps": ["背靠墙站立", "后脑勺、上背、臀部贴墙", "观察后脑勺是否能自然贴墙"],
      "positive_sign": "后脑勺无法自然贴墙",
      "image_key": "assets/images/tests/hn01_wall_test.png",
      "tools_needed": "无"
    }
  ],
  "corrections": [...],
  "consequences": [...],
  "red_flags": ["伴手臂放射痛、麻木、握力下降"],
  "related_issues": [
    {"id": "HN-02", "weight": 0.9, "relation": "因果/共存"},
    {"id": "ST-04", "weight": 0.9, "relation": "共存(UCS)"}
  ]
}
```

分类编码（与 issue.md 章节对应）：
- `head_neck`: 头颈部（1.头部前倾, 2.颈曲变直, 3.斜颈, 25.短信颈）
- `shoulder_thorax`: 肩胸区（4.圆肩, 5.高低肩, 6.翼状肩胛, 7.上交叉综合征, 8.驼背, 9.平背, 10.肋骨外翻）
- `pelvis_spine`: 骨盆腰椎（11.脊柱侧弯, 12.摇摆背, 13.骨盆前倾, 14.骨盆后倾, 15.下交叉综合征, 16.骨盆侧倾, 17.骨盆旋转）
- `lower_limb`: 下肢（18.X型腿, 19.O型腿, 20.膝超伸, 21.扁平足, 22.高弓足, 23.足外翻, 24.足内翻）
- `compound`: 复合综合征（25.分层综合征, 26.短信颈）

总计 26 项。

ID 命名规则：`{类别缩写}-{两位序号}`
- 头颈：`HN-01`~`HN-03`
- 肩胸：`ST-04`~`ST-10`
- 骨盆腰椎：`PS-11`~`PS-17`
- 下肢：`LL-18`~`LL-24`
- 复合：`CP-25`~`CP-26`

---

## 9. AI 分析设计

### 9.1 Qwen VL 调用方案

使用模型：`qwen-vl-max`（视觉理解最强）或 `qwen-vl-plus`（平衡精度和成本）
初期建议用 `qwen-vl-max` 验证准确率，稳定后降级到 `qwen-vl-plus` 控制成本。

### 9.2 AI 判定等级映射

AI 输出 4 级：normal / mild / moderate / severe
App 展示 3 档：
- normal + mild → 正常/轻微（预防建议）
- moderate → 中度（纠正训练）
- severe → 重度（引导就医）

数据库 `result` 字段存 3 档简化值：normal / moderate / severe（mild 归入 normal）

### 9.3 Prompt 模板

```
你是一位专业的运动康复评估师，具备丰富的体态评估经验。

当前评估问题：{issue_name}（{issue_definition}）

用户信息：
- 性别：{gender}
- 年龄：{age}
- 身高：{height}cm
- 体重：{weight}kg

请分析用户上传的照片，完成以下任务：

1. 识别照片中与"{issue_name}"相关的体征
2. 给出判定等级：normal（正常）/ mild（轻度）/ moderate（中度）/ severe（重度）
3. 给出判定依据（具体哪些视觉特征支持你的判断）
4. 如果照片角度、清晰度不足以准确判断，明确说明并建议重拍

请以 JSON 格式输出：
{
  "level": "normal|mild|moderate|severe",
  "confidence": 0.0-1.0,
  "evidence": ["特征1", "特征2"],
  "suggestion": "建议文字",
  "need_retake": false,
  "retake_reason": ""
}

重要提示：
- 你的分析仅供参考，不构成医疗诊断
- 如发现可能的严重病理问题，请在 suggestion 中建议用户就医
- 保持客观、专业、谨慎的态度
```

### 9.4 成本估算

- 单次分析：2-3张照片（约3.5万Token输入）+ 输出（约500Token）
- qwen-vl-plus: 输入 0.8元/百万Token + 输出 4.8元/百万Token
- **单次成本约 3 分钱**

---

## 10. 图片上传流程

```
Flutter App                    FastAPI 后端              阿里云 OSS          Qwen VL (百炼)
    │                              │                      │                      │
    │ 1. POST /upload/sts-token    │                      │                      │
    │ ───────────────────────────► │                      │                      │
    │                              │ 2. 调用 STS 生成临时凭证 │                      │
    │ 3. 返回 {accessKeyId,        │                      │                      │
    │    accessKeySecret,          │                      │                      │
    │    securityToken, bucket,    │                      │                      │
    │    region, path_prefix}      │                      │                      │
    │ ◄─────────────────────────── │                      │                      │
    │                              │                      │                      │
    │ 4. 直传照片到 OSS（用临时凭证）│                      │                      │
    │ ────────────────────────────────────────────────────►│                      │
    │                              │                      │                      │
    │ 5. 上传成功，获得 object key  │                      │                      │
    │ ◄────────────────────────────────────────────────────│                      │
    │                              │                      │                      │
    │ 6. POST /posture/assess/photo│                      │                      │
    │    {issue_id, photo_keys:[]} │                      │                      │
    │ ───────────────────────────► │                      │                      │
    │                              │ 7. 用 key 生成签名URL  │                      │
    │                              │ ─────────────────────►│                      │
    │                              │ ◄── 返回图片内容 ──────│                      │
    │                              │                      │                      │
    │                              │ 8. 调用 Qwen VL 分析   │                      │
    │                              │ ─────────────────────────────────────────────►│
    │                              │ ◄──────────────── 返回分析结果 ────────────────│
    │                              │                      │                      │
    │ 9. 返回分析结果               │                      │                      │
    │ ◄─────────────────────────── │                      │                      │
```

STS 临时凭证有效期：15分钟，权限仅限上传指定路径前缀。

---

## 11. 自测示意图方案

### 11.1 生成方式

使用 AI 图像生成工具（Stable Diffusion / DALL-E）批量生成。

### 11.2 统一风格规范

- **背景**：深色（#1A1A2E 或类似）
- **人体**：简洁轮廓线条，浅色（白/灰）
- **标注**：
  - 红色：问题部位/错误姿势
  - 绿色：正确位置/目标方向
  - 箭头：动作方向/偏差方向
- **视角**：正面或侧面，根据自测需要
- **尺寸**：1080×1080px（适配手机屏）
- **格式**：PNG（透明背景可选）

### 11.3 图片数量估算

25个问题 × 平均2个自测方法 = 约50张示意图

### 11.4 存储

打包在 App 内 `assets/images/tests/` 目录，随 App 发布，不需网络加载。

---

## 12. 安全与合规

### 12.1 数据安全

- 用户照片通过 HTTPS 加密传输
- OSS 存储启用服务端加密（SSE-AES256）
- 照片保留策略：分析完成后保留30天，用户可手动删除
- JWT Token 存储在设备 Secure Storage（iOS Keychain / Android EncryptedSharedPreferences）

### 12.2 医疗合规

全局免责声明（App 内多处展示）：

> "本内容基于公开医学文献，仅供健康科普与自我管理参考，不能替代专业医疗诊断与治疗。如有持续疼痛、麻木、畸形或其他异常，请及时就医。"

### 12.3 自测三档输出规则

| 等级 | 触发条件 | App 行为 |
|------|---------|---------|
| 正常/轻微 | 自测阴性 或 AI 判定 normal/mild | 显示预防建议 |
| 中度 | 自测阳性 或 AI 判定 moderate | 展示纠正训练方案 |
| 重度/红旗 | AI 判定 severe 或 触发 red_flags | 弹窗强制引导就医，不提供自行纠正方案 |
| 不确定 | 用户自测选择"不确定" | 引导用户进行 AI 拍照分析，若用户拒绝则标记为"待确认"并建议改天重测 |

---

## 13. 关联推荐逻辑

基于 issue.md 第八章关联矩阵：

1. 用户完成某问题评估且结果为"中度"或"重度"
2. 查询该问题的 `related_issues`，筛选 weight >= 0.6（中/强关联）
3. 按 weight 降序排列，展示前 3 个关联问题
4. 优先提示根因（遵循根因优先级原则）：
   - 先排除结构性/病理性 → 引导就医
   - 自下而上链优先处理足踝根因
   - 矢状面以骨盆为枢纽
   - 最后处理远端代偿表现

---

## 14. 未来扩展预留

| 预留项 | 说明 |
|--------|------|
| `plan/` 模块目录 | 训练计划（后续开发） |
| `diet/` 模块目录 | 饮食推荐（后续开发） |
| `users.membership_level` | 付费等级字段 |
| API 版本化 `/api/v1/` | 未来破坏性变更走 v2 |
| 问题库切数据库 | 初期 JSON hardcode，后续加管理后台 |
| 微信小程序 | 独立代码库（Uni-app），共用后端 API |

---

## 15. 非功能性需求

| 项目 | 目标 |
|------|------|
| API 响应时间 | p95 < 500ms（不含 AI 分析） |
| AI 分析响应 | < 10s（含图片传输） |
| App 启动时间 | 冷启动 < 3s |
| 3D 模型加载 | < 2s |
| 并发支持 | 初期 100 QPS 足够 |
| 可用性 | 99.5%（单节点部署初期可接受） |

---

## 16. 部署方案（MVP 阶段）

| 组件 | 部署位置 |
|------|---------|
| FastAPI 服务 | 阿里云 ECS（1台，2核4G 够用） |
| PostgreSQL | 阿里云 RDS（基础版） |
| OSS | 阿里云 OSS（华东区） |
| 域名 + HTTPS | 阿里云 SSL 免费证书 + Nginx 反代 |

预计月成本（初期低流量）：约 200-400 元/月
