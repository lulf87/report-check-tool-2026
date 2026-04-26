# 报告核对工具

本项目用于上传 PDF 检验报告或 PTR 产品技术要求 PDF，抽取 PDF 文本后调用 Codex CLI 做核对。

## 功能

- 报告自身核对：检查报告内部字段、页码、结论、表格结果等一致性。
- PTR 与报告核对：按报告首页“检验项目”识别 PTR 第 2 章性能指标范围，核对报告“标准要求”是否完整摘录。
- PTR 对照结果会显示首页声明条款、报告实际条款、缺漏条款，以及最细条款的“PTR 内容 / 报告内容”对照。
- 两种核对结果均支持从结果页导出为 PDF。

## 目录

- `backend/`：FastAPI 后端，负责 PDF 解析、证据构建和 Codex 调用。
- `frontend/`：Vite + React 前端。
- `docs/`：需求和实现计划文档。

`素材/`、`tmp/`、`frontend/node_modules/`、`frontend/dist/` 等目录不会提交到 GitHub。

## 启动

后端：

```bash
cd backend
/Users/lulingfeng/miniforge3/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173/
```

## 验证

后端测试：

```bash
cd backend
/Users/lulingfeng/miniforge3/bin/python3 -m pytest -q
```

前端构建：

```bash
cd frontend
npm run build
```

## 注意

- 本仓库不提交原始 PDF 素材；需要核对时从前端页面重新上传 PDF。
- 需要本机已登录并可使用 Codex CLI，否则后端会返回 Codex 调用或解析相关诊断。
