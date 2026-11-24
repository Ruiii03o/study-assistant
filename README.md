# 过了么 · 大学生课程复习助手

围绕个人课程资料和样卷，完成资料整理、复习大纲、练习与仿真考试、错题巩固和学习反馈。

本项目使用原生 HTML/CSS/JavaScript、Python FastAPI 和 SQLite；AI 能力通过配置的外部接口提供，没有训练自有模型。开发过程中使用了 AI 辅助编程与插画生成。

## 1. 主要功能

- 账户注册、登录、课程管理与账户数据隔离；管理员可管理普通账户启用状态。
- 上传 PDF、DOCX、PPTX、JPG、PNG；文字提取、人工校对、章节范围设置。
- PDF 原页转图与 AI 图文/数学识别，校对后保存；数学公式使用 KaTeX 展示。
- 按范围分批整理大纲、继续处理、批注、命名存档、重命名、导出和删除。
- 章节练习：单选、多选、判断、填空、简答；草稿保存、提交和评分。
- 样卷结构确认与分批仿真组卷；有课件时限制范围，无课件时使用样卷知识线索。
- 限时考试、原题重做、错题变式、知识点梳理及补充讲解。
- 根据真实作答生成学习报告、信心分析和下一步学习建议。
- 学习资源搜索与收藏（需要相应搜索服务权限）。

## 2. 环境要求

- Python 3.11 或以上；本项目主要在 Windows / Python 3.13 环境开发验证。
- 现代浏览器。Node.js 仅用于运行前端自动化测试，启动网站不需要 Node.js。
- 调用 AI 时需要网络、可用接口地址、模型名称和自己的 API 密钥。
- 图文识别需要模型和接口支持图像输入，纯文本模型不能替代。

## 3. Windows 快速开始

在项目根目录打开 PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

若安装的是其他受支持的 Python 版本，将 `py -3.13` 换成相应版本。
打开 http://127.0.0.1:8000/ ，首次使用先注册账户。启动时会自动创建 `data/app.db` 及所需表，不需要导入开发者的数据库。

PyCharm：将项目解释器设置为 `.venv/Scripts/python.exe`，再运行 `run.py`。
停止服务：在运行窗口按 Ctrl+C。

macOS/Linux 可使用：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

这些命令提供跨平台启动方式；当前发布检查以 Windows 为准。

## 4. 配置 AI

复制样例配置，不要将真实配置暴露：

```powershell
Copy-Item ai-config.example.json ai-config.json
```

编辑 `ai-config.json`：

```json
{
  "url": "https://YOUR_PROVIDER_HOST/v1/chat/completions",
  "model": "YOUR_MODEL_NAME",
  "api_key": "YOUR_API_KEY"
}
```

将占位内容替换为服务商提供的真实值。接口需兼容本项目使用的 Chat Completions 请求和响应格式；地址必须为 HTTPS。不同服务的模型、图像输入和 JSON 输出能力可能不同。

也可以通过环境变量配置：

| 环境变量 | 用途 |
| --- | --- |
| `STUDY_AI_URL` | AI 接口地址 |
| `STUDY_AI_MODEL` | 模型名称 |
| `STUDY_AI_KEY` | API 密钥 |
| `STUDY_SEARCH_KEY` | 资源搜索所需的 DeepSeek 官方服务密钥 |
| `STUDY_DB` | 自定义 SQLite 数据库路径，默认 `data/app.db` |
| `STUDY_SECURE_COOKIE` | HTTPS 部署时设为 `1`，要求 Cookie 通过安全连接传输 |

兼容的 `deepseek_api_base`、`deepseek_model`、`deepseek_api_key` 环境变量优先于对应的 `STUDY_AI_*`，环境变量优先于配置文件。配置状态显示已填写，不等于已验证服务可用。

无 AI 配置时仍可使用账户、课程、资料本地提取及已有数据浏览等功能。AI 生成、图文识别和部分讲解需要配置。所选资料或页面图片会发送到配置的 AI 服务，调用可能产生费用。

## 5. 推荐体验流程

1. 注册并登录，创建课程。
2. 上传资料，提取文字；公式或扫描页可进入原页图文识别并校对。
3. 设置并保存章节范围。
4. 在“复习”中选择范围，生成大纲；完成后命名存档。
5. 在“练习与考试”中生成章节练习，或上传样卷并确认结构后组卷。
6. 保存作答、提交，按需完成主观题评价。
7. 查看本次错题、知识点和变式练习，在报告中查看下一步建议。

普通练习与考试的评分、变式的正误统计采用各自的界面口径；未评分题目不会直接当作已答错。考试时间由后台判断，切换页面不会暂停。

## 6. 资料格式与限制

| 格式 | 处理方法 |
| --- | --- |
| PDF | pypdf 提取文字；复杂公式/扫描页可转图片后识别 |
| DOCX | ZIP/XML 提取段落文字 |
| PPTX | ZIP/XML 与幻灯片位置重组 |
| JPG/PNG | 图文识别或人工录入校对流程 |
| DOC/PPT | 需先另存为 DOCX/PPTX |

普通资料上传限制：单文件 30 MB、账户资料合计 500 MB；基础 PDF 提取最多 300 页。原页图片接口有独立的大小与尺寸限制。提取不等于完整复刻版式，复杂图表、公式仍需校对。

## 7. 数据与安全

- `data/app.db`：账户、课程、资料文字、任务、试题、作答、批注等。
- `data/uploads/`：上传的原始资料。部分页面图片另存在数据库 BLOB 中。
- 密码使用加盐 scrypt；登录使用 HttpOnly / SameSite Cookie；业务接口检查资源所有者。
- 大纲与试题保留生成时的来源快照；修改资料不会直接重写历史依据。
- API 密钥仅供后端使用；源码交付包不含真实配置、用户资料或数据库。

默认只监听本机 `127.0.0.1`。当前项目面向本地课程设计演示；公开部署需要另外配置 HTTPS、访问与请求限制、运行监控和备份，不应直接将开发环境当作生产服务。

## 8. 管理员、备份与恢复

先在网页注册管理员候选账户，再停止服务，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m backend.maintenance grant-admin --username YOUR_USERNAME
```

重新启动并登录。没有固定的默认管理员密码。

停止服务后备份（备份文件名不能已存在）：

```powershell
.\.venv\Scripts\python.exe -m backend.maintenance backup --output backups/study-backup.zip
```

恢复到一个尚不存在的新目录：

```powershell
.\.venv\Scripts\python.exe -m backend.maintenance restore --archive backups/study-backup.zip --destination restored-data
$env:STUDY_DB = "restored-data/app.db"
.\.venv\Scripts\python.exe run.py
```

备份包含所有账户的学习数据和已登记原始资料，不包含 AI 密钥；恢复会清除登录会话。不要把备份上传公开仓库。

## 9. 项目结构

| 路径 | 作用 |
| --- | --- |
| `run.py` | 启动 Uvicorn 服务 |
| `backend/` | FastAPI 接口、解析、AI、评分与存储逻辑 |
| `frontend/` | HTML、CSS、JavaScript 和本地资源 |
| `frontend/vendor/katex/` | 公式渲染库与许可 |
| `tests/` | Python 与 JavaScript 自动化测试 |
| `docs/` | 配置、历史开发记录、交付检查记录 |
| `requirements.txt` | Python 依赖版本范围 |
| `ai-config.example.json` | 无密钥的 AI 配置模板 |
| `PRODUCT.md` | 当前功能范围与限制 |
| `DESIGN.md` | 当前界面与架构设计 |
| `THIRD_PARTY_NOTICES.md` | 第三方组件与素材说明 |

`docs/stage*.md` 和 `docs/progress.md` 是历史记录，不代表当前界面。以本 README、当前代码与对应发布检查记录为准。

为复现本次验证环境，另提供 `requirements-lock.txt`（Windows / Python 3.13 已安装依赖的固定版本）。同平台可用 `python -m pip install -r requirements-lock.txt` 安装；其他平台先使用 `requirements.txt`。

## 10. 测试

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp=.tmp-test-run
node --test tests/*.cjs
```

`--basetemp` 指定专用测试临时目录，pytest 会管理该目录，不要指向资料目录。测试主要使用临时数据库和模拟服务响应，不需要真实 AI 密钥；通过测试不等于验证所有服务商的真实模型输出，也不替代浏览器人工体验。

## 11. 常见问题

- **端口 8000 被占用**：确认是否已有 run.py 正在运行，停止自己先前启动的实例后再启动。
- **页面仍是旧版**：Ctrl+F5 强制刷新；后端代码变化需重启 run.py。
- **无法调用 AI**：检查地址、密钥、模型权限、网络和余额。配置样例不是已验证的服务账户。
- **超时或格式错误**：查看页面具体原因；保留的合格题可继续补题，不要连续重复提交。
- **PDF 没有文字**：可能是扫描页，使用原页图文识别或人工校对。
- **图片识别失败**：确认接口与模型支持图像输入。
- **搜索失败**：独立搜索接口需要服务支持和权限，文本生成可用不代表搜索可用。

## 12. 交付与授权

提交源代码、必要素材、说明和测试；排除 `.venv`、缓存、`.tmp*`、数据库、上传资料、真实配置及备份。

第三方组件遵循各自许可。项目自身尚未指定开源许可证；公开代码不等于授予任意使用、修改或商业分发的许可。
