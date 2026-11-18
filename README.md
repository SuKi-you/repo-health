# oss-health

开源仓库健康度调查。输入一个 GitHub 仓库，判断它还能不能被长期依赖。

## 它能做什么

- **单库查询**：给一个链接，输出「健康 / 不健康」和判定理由
- **批量查询**：并发评估一批仓库，输出汇总表
- **网页界面**：黑绿主题，输入链接后展示结论、开发活动图和下载曲线
- **按周缓存**：一周内重复查询直接返回结果，不再调用模型

## 判定方式

从 GitHub 和 PyPI 抓取 12 项数据——发版节奏、提交活跃度、issue 响应速度、未关闭积压、下载趋势、贡献者集中度、是否归档——按固定规则输出结论。

针对知名项目，用 5 条红旗做反证检验；对不熟悉的项目，按维护、响应、存活、使用四个维度综合判断。

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .

setx GITHUB_TOKEN "ghp_xxx"    # 只读，用于抓取 GitHub 数据
setx LLM_API_KEY "sk-xxx"      # 用于生成判定
```

重开终端后：

```powershell
python agent.py https://github.com/pandas-dev/pandas
```

带上图表：

```powershell
python agent.py pandas-dev/pandas --chart card.png
```

批量：

```powershell
python batch.py repos.txt
```

网页：

```powershell
python web\server.py
```

打开 http://127.0.0.1:7860

## 项目结构

| 文件 | 作用 |
|---|---|
| `analyze.py` | 抓取单个仓库的数据并计算 12 项指标 |
| `agent.py` | 工具调用循环，驱动模型完成判定 |
| `cache.py` | 按 ISO 周缓存的判定结果 |
| `chart.py` | 生成证据卡（开发活动 + 下载曲线） |
| `batch.py` | 多仓库并发评估 |
| `web/` | Flask 服务与前端页面 |
| `PROMPT.md` | 判定规则与输出格式 |
| `METRICS.md` | 每项指标的设计依据与判断逻辑 |

## 技术栈

Python 3.10+ · requests · Flask · matplotlib
