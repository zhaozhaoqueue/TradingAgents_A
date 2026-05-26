# A 股 Agent MVP 产品化计划

## 当前阶段

当前项目已经完成 A 股 Agent 的基础跑通：

- TuShare Pro 用于 A 股行情、复权行情、财务数据。
- AkShare 用于新闻和部分市场资讯 fallback。
- DeepSeek 用于 LLM 推理。
- CLI 可以通过源码方式运行。
- A 股 ticker 使用 TuShare 格式，例如 `600326.SH`、`000563.SZ`。

下一阶段目标不是继续堆数据源，而是把现有能力包装成一个可以稳定交付、快速验证市场需求的 MVP 产品。

## 产品定位

建议第一版定位为：

```text
A 股智能投研报告生成器
```

目标用户：

- 个人投资者
- 小型私募或投研团队
- 财经内容创作者
- 需要快速扫描自选股的人

核心价值：

```text
输入股票代码或自选股列表，自动生成结构化、带数据来源的投研报告和每日关注摘要。
```

产品表达应避免使用“AI 荐股”“自动交易”“稳赚策略”等高风险表述，建议使用：

- AI 辅助投研
- 风险扫描
- 信息聚合
- 多视角分析
- 自选股日报

## MVP 核心功能

第一版只保留三个强功能：

1. 个股报告  
   输入股票代码，例如 `600326.SH`，输出技术面、基本面、新闻事件、风险点和结论摘要。

2. 自选股日报  
   用户维护一个自选股列表，每天自动生成“今日值得关注的变化”。

3. 报告导出  
   支持 Markdown，后续扩展 HTML、PDF、微信可读格式。

暂时不建议一开始做：

- 自动交易
- 策略市场
- 复杂回测平台
- 大而全 SaaS Dashboard
- 组合优化

这些功能开发成本高，验证周期长，不适合作为第一版 MVP。

## 推荐产品形态

建议按下面顺序推进：

```text
Phase 1: CLI / batch runner + Markdown 报告
Phase 2: 自选股日报 + HTML/PDF 导出
Phase 3: 邮件 / 飞书 / 企业微信推送
Phase 4: Streamlit / Gradio Web UI
Phase 5: SaaS Dashboard
```

最快可验证市场的形态不是完整 Web App，而是：

```text
用户给出自选股列表，每天收到一份可读的投研日报。
```

这比要求用户主动登录平台更容易形成使用习惯。

## P0：报告稳定性

第一优先级是让报告稳定、可读、可信。

### 固定最终报告模板

最终报告建议统一为：

```text
1. 一句话结论
2. 评级：Buy / Overweight / Hold / Underweight / Sell
3. 数据完整性
4. 技术面
5. 基本面
6. 新闻与事件
7. 风险点
8. 未来 3-7 天关注点
9. 数据来源
10. 免责声明
```

不要让每个 Agent 自由发挥成完全不同的结构。结构固定后，用户更容易阅读，也更容易批量比较多只股票。

### 增加数据完整性区块

每份报告必须明确写出：

```text
行情数据：TuShare Pro，最新交易日
财务数据：TuShare Pro，最新报告期
新闻数据：AkShare / Tavily，覆盖日期
缺失数据：有哪些
```

示例：

```text
数据完整性：
- 行情：TuShare Pro，更新至 2026-05-27
- 财务：TuShare Pro，最近报告期 2026Q1
- 新闻：AkShare，覆盖最近 7 天
- 搜索新闻：未配置 Tavily，已使用 AkShare fallback
```

### 降低用户可见噪音

开发日志里可能出现：

```text
structured-output invocation failed
fallback to AkShare
provider returned no structured object
```

产品中不要原样展示给用户。建议转换成：

```text
部分结构化解析失败，已自动切换文本模式。
Tavily 未配置，已使用 AkShare 新闻源。
```

### 统一交易日逻辑

A 股应统一使用 TuShare `trade_cal` 处理交易日，避免模型自己判断“上一个交易日”。

需要确保报告中明确显示：

```text
请求分析日期
最新可用交易日
行情数据覆盖区间
```

## P1：Batch Runner

下一步建议做一个批量报告生成器。

输入：

```text
watchlist.csv
```

示例：

```csv
symbol,name
600326.SH,西藏天路
000563.SZ,陕国投A
600519.SH,贵州茅台
```

输出：

```text
reports/2026-05-27/
  daily_digest.md
  600326.SH.md
  000563.SZ.md
  600519.SH.md
  run_summary.json
```

Batch runner 需要支持：

- 批量跑多个股票
- 单只股票失败不影响整体任务
- 失败原因记录到 `run_summary.json`
- 支持并发限制
- 支持重新运行失败项
- 支持 Markdown 输出

## P2：每日汇总 Daily Digest

单只股票报告有价值，但真正形成习惯的是每日汇总。

`daily_digest.md` 建议包含：

```text
1. 今日总览
2. 最值得关注的股票
3. 风险上升的股票
4. 有新闻催化的股票
5. 技术面破位或突破的股票
6. 数据缺失或分析失败的股票
7. 明日关注点
```

重点不是重复介绍公司，而是回答：

```text
今天发生了什么变化？
为什么值得看？
风险有没有变大？
结论相比昨天有没有改变？
```

## P3：差异化价值

用户最需要的不是一份静态公司介绍，而是“变化检测”。

### 昨日对比

每只股票应记录上一次报告结果，并比较：

- 评级是否变化
- 技术面是否变化
- 新闻事件是否新增
- 风险项是否变化
- 数据完整性是否变化

### 简单异常检测

第一版可以先用规则，不需要复杂模型。

建议规则：

```text
涨跌幅 > 5%
成交量 > 20 日均量 2 倍
RSI < 30 或 RSI > 70
跌破 20 日均线
突破 20 日均线
新闻数量异常增加
近期公告出现重大事项关键词
```

### 自选股排序

每日汇总应对自选股排序，而不是简单罗列。

可按以下维度打标签：

```text
重点关注
风险上升
新闻催化
技术破位
技术突破
数据不足
保持观察
```

## P4：运行可观测性

MVP 也需要基础可观测性，否则很难稳定交付。

建议每次运行生成：

```text
run_summary.json
```

示例：

```json
{
  "date": "2026-05-27",
  "total": 3,
  "success": 2,
  "failed": 1,
  "items": [
    {
      "symbol": "600326.SH",
      "status": "success",
      "latest_trade_date": "2026-05-27",
      "data_sources": ["tushare_pro", "akshare"],
      "missing": ["tavily_news"],
      "duration_seconds": 82,
      "llm_provider": "deepseek",
      "quick_model": "deepseek-v4-flash",
      "deep_model": "deepseek-v4-pro"
    }
  ]
}
```

需要记录：

- 每只股票是否成功
- 失败原因
- 数据源使用情况
- 数据缺失情况
- LLM provider 和模型
- 单只股票耗时
- 总耗时
- token 成本，后续可加

## P5：导出和分发

第一版建议支持：

- Markdown
- HTML
- PDF

分发方式建议优先做：

- 邮件
- 飞书机器人
- 企业微信机器人
- Telegram Bot

相比 Web UI，日报推送更容易验证用户是否真的每天看。

## P6：合规和信任

产品必须明确：

```text
本报告由 AI 辅助生成，仅用于信息整理和研究参考，不构成投资建议。
市场有风险，投资需谨慎。用户应结合自身风险承受能力独立判断。
```

报告中需要保留：

- 数据来源
- 数据时间
- 报告生成时间
- 缺失数据说明
- 模型可能出错说明

避免承诺：

- 收益率
- 胜率
- 买卖点精准预测
- 自动交易结果

## 成本优化

建议使用分层模型调用：

```text
DeepSeek Flash:
  数据摘要
  新闻整理
  初步分析

DeepSeek Pro:
  最终综合判断
  Research Manager
  Portfolio Manager
```

进一步优化：

- 缓存行情和财务数据
- 缓存新闻搜索结果
- 批量任务中复用同一份宏观新闻
- 减少重复 Agent 调用
- 对日报使用简化分析链路
- 深度报告才启用完整多 Agent 流程

## 推荐开发顺序

建议下一阶段按这个顺序做：

```text
1. report_renderer：统一最终报告模板
2. data_quality：数据完整性检查模块
3. batch_runner：支持 watchlist.csv 批量跑报告
4. daily_digest：生成每日自选股汇总
5. run_summary.json：记录运行状态和失败原因
6. HTML/PDF 导出
7. 邮件/飞书/企业微信推送
8. 简单 Web UI
```

## 两周市场验证计划

### 第 1 周：打磨样本报告

目标：

```text
生成 20-30 份真实 A 股报告，人工检查质量。
```

覆盖行业：

- 白酒
- 银行
- 信托
- 半导体
- 机器人
- 有色
- 地产
- 券商
- 建材
- 军工

重点检查：

- 数据是否准确
- 日期是否正确
- 新闻是否相关
- 结论是否有依据
- 风险提示是否充分
- 是否出现幻觉

### 第 2 周：用户验证

找 20 个目标用户试用。

不要问：

```text
你觉得怎么样？
```

应该问：

```text
这份报告哪里帮你省时间？
哪一段你最想每天看？
哪一段最没用？
有没有明显错误？
如果每月 99 元，你会买吗？
如果每天推送自选股日报，你会看吗？
```

## 初始定价实验

可以先用非常简单的分层：

```text
免费版：
  每天 1 只股票

99 元/月：
  10 只自选股日报

299 元/月：
  50 只自选股
  深度报告
  Markdown/PDF 导出
```

第一阶段不必做复杂支付系统，可以用人工交付、微信群、飞书群、表单收集需求快速验证。

## 当前最重要的下一步

最值得马上做的是：

```text
watchlist.csv -> batch_runner -> reports/YYYY-MM-DD/*.md -> daily_digest.md
```

这一步最小、最快、最接近可收费交付。

相比继续优化单次 CLI 交互，批量日报更接近真实用户场景，也更容易验证市场是否愿意付费。

## Forward Test 实现思路

当前框架不适合直接做严格历史回测。原因是新闻、搜索结果、部分财务数据和 LLM 输出都不具备严格的 point-in-time 保证。

更适合的验证方式是：

```text
每日固定时间运行 Agent，保存当时的数据、报告和交易观点，然后在未来 N 个交易日后评估表现。
```

这属于 forward test / paper trading，比“今天回头跑历史日期”更接近真实使用场景。

### 为什么不建议直接历史回测

主要问题：

1. 新闻数据不可靠  
   新闻接口和搜索接口通常返回的是当前可搜索到的内容。即使传入历史日期，也很难保证结果等同于历史当天用户能看到的信息。

2. 财务数据可能有未来函数  
   如果只按报告期过滤，而不按公告发布时间过滤，就可能在历史日期看到当时还没披露的数据。

3. LLM 输出不可完全复现  
   模型版本、提示词、API 行为、搜索结果排序都可能变化。今天运行 2025 年某天的分析，不等于当时真实可获得的判断。

4. 数据源会修订历史数据  
   财务、行情、指数成分、新闻链接都可能在后续被修订或下线。

因此，当前阶段建议把它定义为：

```text
前向纸面交易验证系统
```

而不是：

```text
严格历史回测系统
```

### Forward Test 工作流

每日流程：

```text
1. 读取 watchlist.csv
2. 对每只股票运行 Agent
3. 保存原始数据快照
4. 保存完整报告
5. 保存结构化 signal
6. 记录运行日志和失败项
7. 在未来 1/3/5/10/20 个交易日后计算表现
```

建议运行时间：

```text
A 股收盘后，例如 16:00-18:00
```

这样可以确保当天收盘行情、新闻和公告数据相对完整。

### 需要保存的数据

每次运行至少保存：

```text
输入：
- symbol
- name
- analysis_date
- watchlist 来源

行情：
- 当日收盘价
- 成交量
- 近 N 日 OHLCV
- 基准指数收盘价

Agent 输出：
- rating
- final_decision
- risk_summary
- key_catalysts
- key_risks
- report_path

运行信息：
- data_sources
- missing_data
- model
- prompt_version
- code_commit
- duration_seconds
- status
```

示例 signal：

```json
{
  "date": "2026-05-27",
  "symbol": "600326.SH",
  "name": "西藏天路",
  "rating": "Overweight",
  "close": 8.23,
  "benchmark": "000300.SH",
  "benchmark_close": 3920.15,
  "final_decision": "维持谨慎偏多，关注量能和建材板块持续性。",
  "key_catalysts": [
    "建筑材料板块资金流入",
    "区域基建预期升温"
  ],
  "key_risks": [
    "短期涨幅过快",
    "量能持续性不足"
  ],
  "data_sources": {
    "price": "tushare_pro",
    "fundamentals": "tushare_pro",
    "news": "akshare"
  },
  "missing_data": [
    "tavily_news"
  ],
  "llm_provider": "deepseek",
  "quick_model": "deepseek-v4-flash",
  "deep_model": "deepseek-v4-pro",
  "prompt_version": "a-share-mvp-v1",
  "report_path": "reports/2026-05-27/600326.SH.md",
  "status": "success"
}
```

### 推荐目录结构

```text
forward_test/
  watchlists/
    default.csv
  reports/
    2026-05-27/
      daily_digest.md
      600326.SH.md
      000563.SZ.md
  snapshots/
    2026-05-27/
      600326.SH/
        prices.parquet
        fundamentals.json
        news.jsonl
        prompt.txt
        final_state.json
  signals.sqlite
  performance/
    daily_performance.csv
    rating_performance.csv
    symbol_performance.csv
  run_summary/
    2026-05-27.json
```

### signals.sqlite 表设计

建议先用 SQLite。

`signals` 表：

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    rating TEXT NOT NULL,
    close REAL,
    benchmark TEXT,
    benchmark_close REAL,
    final_decision TEXT,
    report_path TEXT,
    prompt_version TEXT,
    code_commit TEXT,
    llm_provider TEXT,
    quick_model TEXT,
    deep_model TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

`signal_returns` 表：

```sql
CREATE TABLE signal_returns (
    signal_id INTEGER NOT NULL,
    horizon_days INTEGER NOT NULL,
    future_date TEXT,
    future_close REAL,
    raw_return REAL,
    benchmark_return REAL,
    alpha_return REAL,
    max_drawdown REAL,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (signal_id, horizon_days)
);
```

`run_logs` 表：

```sql
CREATE TABLE run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    symbol TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_seconds REAL,
    data_sources TEXT,
    missing_data TEXT,
    created_at TEXT NOT NULL
);
```

### 评估周期

建议先评估这些周期：

```text
1 个交易日
3 个交易日
5 个交易日
10 个交易日
20 个交易日
```

计算指标：

```text
raw_return = future_close / close - 1
benchmark_return = future_benchmark_close / benchmark_close - 1
alpha_return = raw_return - benchmark_return
```

按 rating 统计：

```text
Buy 平均收益
Overweight 平均收益
Hold 平均收益
Underweight 平均收益
Sell 平均收益
胜率
平均 alpha
最大回撤
样本数
```

### 评级和收益方向

不同 rating 的预期方向：

```text
Buy:
  期望 raw_return 和 alpha_return 明显为正

Overweight:
  期望 alpha_return 为正

Hold:
  期望波动较小，收益接近基准

Underweight:
  期望 alpha_return 为负，或者弱于基准

Sell:
  期望 raw_return 或 alpha_return 为负
```

注意：第一阶段不要过度追求单笔准确率，更重要的是看统计分布。

### Forward Test Runner

建议新增命令：

```bash
python -m scripts.forward_test_run --watchlist forward_test/watchlists/default.csv --date 2026-05-27
```

职责：

```text
1. 读取 watchlist
2. 对每只股票运行 Agent
3. 生成报告
4. 写入 signals.sqlite
5. 保存数据快照
6. 生成 daily_digest.md
7. 生成 run_summary JSON
```

### Performance Updater

建议新增命令：

```bash
python -m scripts.forward_test_update_returns --date 2026-05-27
```

职责：

```text
1. 找出 signals 表里尚未计算收益的记录
2. 检查是否已经到达 1/3/5/10/20 个交易日
3. 拉取未来价格和基准价格
4. 写入 signal_returns 表
5. 更新 performance CSV
```

### Forward Test Dashboard

后续可以做一个简单页面展示：

```text
总样本数
按 rating 的平均收益
按 horizon 的 alpha
最近一周表现
最好/最差信号
失败运行记录
```

第一版可以先用 Markdown 或 CSV，不必马上做 Web UI。

### 与 MVP 的关系

Forward test 是产品可信度建设的一部分。

它可以回答：

```text
这个 Agent 的评级有没有统计价值？
哪些行业表现更好？
哪些 rating 更可靠？
新闻驱动的结论是否有效？
技术面驱动的结论是否更短期有效？
```

它也可以作为产品展示材料：

```text
过去 30 天，Overweight 信号 5 日平均 alpha 为 X%
过去 30 天，风险上升标签股票平均跑输基准 Y%
```

但在样本量不足前，不要把这些指标当成收益承诺。

### Forward Test MVP 开发顺序

建议顺序：

```text
1. signals.sqlite
2. 结构化 signal 提取
3. 每日报告保存
4. run_summary.json
5. 收益更新脚本
6. rating_performance.csv
7. daily_digest 中加入历史表现摘要
```

第一版目标：

```text
连续运行 20 个交易日，积累至少 200-500 条信号样本。
```

这比一次性历史回测更慢，但更真实、更可信，也更适合当前 Agent 架构。
