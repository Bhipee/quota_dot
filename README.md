# quota-dot

把 Codex 额度、中转站余额（Nexus、公司 LiteLLM）和 cc-switch 每日用量画成 296×152 的黑白图，通过 Dot. 图片 API 推到 Quote/0。

功能都是插件：**数据源**（`quotadot/sources/`）负责取数，**页面**（`quotadot/pages/`）负责画一屏。用 `PAGES` 选择要推哪些页面，每个页面推到设备列表里自己的那个「图片 API」项。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env               # 填 DOT_*、要用的数据源；用不到的整组删掉
python -m quotadot list            # 看有哪些数据源和页面、在这台机器上能不能用
python -m quotadot render          # 只出图到 out/，不推送
python -m quotadot push            # 出图并推送一次
python -m quotadot run             # 常驻，每个页面按自己的间隔推送
```

`.env` 会自动加载（`--env-file` 可换路径），已经存在的环境变量优先，不会被覆盖。

## 页面

| 页面 | 内容 | 需要的数据源 | 默认间隔 |
| --- | --- | --- | --- |
| `quota` | 左栏 Codex 剩余额度，右栏中转站余额（一个显示大字，多个显示列表） | `codex`（`relays` 可选） | 900 秒 |
| `heatmap` | GitHub 式每日用量格子图，24 周，4 档点阵深浅 | `ccswitch` | 3600 秒 |
| `overview` | 顶部同 heatmap 的 TOKENS 标题和 today / 7d / 区间合计；左边每个额度一行（Codex、各中转站），右边最近几周的格子图（`PAGE_OVERVIEW_WEEKS`，默认 10，4–13） | `ccswitch`（`codex`、`relays` 可选） | 900 秒 |

每个页面的设置都用 `PAGE_<名字>_<项>`：

- `TASK_KEY`：推到哪个「图片 API」项。**多个页面必须各配一个**，否则会互相覆盖。key 从 `GET /api/authV2/open/device/{id}/loop/list` 返回里 `IMAGE_API` 那几项取。
- `INTERVAL`：推送间隔（秒，最少 60）。
- `ALIAS`：在 Dot. App 列表里显示的名字。
- `TASK_TYPE`：`loop` 或 `fixed`，默认取 `DOT_TASK_TYPE`。
- 页面自己的选项，比如 `PAGE_HEATMAP_METRIC=tokens|fresh|cost`、`PAGE_HEATMAP_WEEKS`。

不设 `PAGES` 时，自动启用「数据源在这台机器上可用」的页面。比如服务器上没有 cc-switch 数据库，`heatmap` 会自动跳过。如果在 `PAGES` 里明确写了某个页面但数据源不可用，它照样推送，图上显示原因。

## 数据源

| 数据源 | 取数方式 | 配置 |
| --- | --- | --- |
| `codex` | `GET chatgpt.com/backend-api/wham/usage`，token 取自 `~/.codex/auth.json`，快过期或 401 时用 `refresh_token` 自动续期并写回 | `CODEX_AUTH_PATH` |
| `relays` | 每个中转站一个 `type`：<br>`nexus`：`GET {base}/v1/usage`，读 `quota.limit/used/remaining`，需带浏览器 UA<br>`litellm`（公司 API）：`GET {base}/team/info?team_id=`，取 `team_memberships` 里你的 `spend` 和 `max_budget`；没有 `spend` 时改为累加 `keys` 里属于你的 key | `NEXUS_*`、`COMPANY_*`，或 `RELAYS` JSON（覆盖前两组，`.env` 里用单引号包住） |
| `ccswitch` | 只读 `~/.cc-switch/cc-switch.db`：近一个月取明细表 `proxy_request_logs`，更早的取 `usage_daily_rollups`。Codex 等的输入 token 本身含缓存，按 cc-switch 的规则扣掉，避免重复 | `CCSWITCH_DB` |

## 加一个新功能

**新页面**：在 `quotadot/pages/` 放一个文件，重启就生效，不用改别处。

```python
from ..draw import canvas, font, footer, to_1bit
from ..registry import Page, page

@page
class HelloPage(Page):
    name = "hello"                  # PAGES=...,hello；设置走 PAGE_HELLO_*
    requires = ("codex",)           # 缺这些数据源时自动跳过
    default_interval = 1800

    def render(self, data, now):
        img, d = canvas()
        d.text((8, 8), f"plan: {data['codex'].plan}", font=font(13, True), fill=0)
        footer(d, now)
        return to_1bit(img)
```

**新数据源**：在 `quotadot/sources/` 放一个文件，继承 `Source`，用 `@source` 注册，实现 `fetch()`。如果数据源在某些机器上用不了，实现 `unavailable()` 返回原因。远端请求失败时把错误放进返回结果，别直接抛异常，这样图上能显示出错原因。

**新中转站类型**：在 `sources/relays.py` 里写一个函数，用 `@relay_type("名字", 必填字段...)` 注册，返回 `RelayReading`。

画图工具都在 `quotadot/draw.py`：字体、进度条、文字截断和换行、底栏、错误块、数字格式化。几个页面共用的组件（TOKENS 标题栏、格子图、紧凑的额度行）在 `quotadot/widgets.py`，组合新页面时可以直接用。屏幕只有黑白两色，深浅用点阵模拟，可参考 `pages/heatmap.py`。

## 部署

格子图要读 cc-switch 的数据库，所以必须在装了 cc-switch 的那台 Mac 上跑。只有 `quota` 页面的话放服务器上就行。

**macOS（launchd）**：`deploy/tech.mindreset.quota-dot.plist` 里路径已经填好了。

```bash
cp deploy/tech.mindreset.quota-dot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/tech.mindreset.quota-dot.plist
tail -f /tmp/quota-dot.log
```

Mac 休眠时不会推送，唤醒后会继续。

**Docker（服务器）**

```bash
mkdir -p data/codex && cp ~/.codex/auth.json data/codex/ && chown -R 1000:1000 data
docker compose up -d --build && docker compose logs -f
```

**systemd**：见 `deploy/quota-dot.service`。也可以不常驻，用 cron 定时跑 `python -m quotadot push`。

## 推送前的准备

1. Dot. App →「内容工坊」，按页面数量在循环列表里添加「图片 API」项。
2. Dot. App →「更多」→「API Key」创建密钥，填到 `DOT_API_KEY`；设备序列号填到 `DOT_DEVICE_ID`。
3. 用上面的 `loop/list` 查询拿到每个「图片 API」项的 `key`，分别填到 `PAGE_QUOTA_TASK_KEY` 和 `PAGE_HEATMAP_TASK_KEY`。

## 注意

- 刷新 Codex token 会换掉 refresh_token。如果本机 Codex CLI 和服务器共用同一个 auth.json，一方刷新后另一方会掉线，服务器最好单独登录一份。
- 固定列表（`fixed`）里的内容要等 App 里设好的时间点才刷新，`refreshNow` 对它不起作用。
- 墨水屏每次刷新都耗电，间隔别设得太短。
