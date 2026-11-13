"""Render README screenshots from synthetic data (no real usage numbers).

  python3 scripts/make_screenshots.py      # writes docs/screenshots/*.png at 2x
"""
import random, sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from quotadot import registry
from quotadot.sources.ccswitch import DayUsage, UsageHistory
from quotadot.sources.codex import CodexReading, Window
from quotadot.sources.relays import RelayReading

out = ROOT / "docs" / "screenshots"
out.mkdir(parents=True, exist_ok=True)
registry.discover()
now = datetime(2026, 11, 13, 16, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
rng = random.Random(7)

history = UsageHistory()
for i in range(26 * 7):
    day = now.date() - timedelta(days=i)
    ramp = 0.35 + 0.65 * (1 - i / 182)                      # busier lately
    weekend = 0.25 if day.weekday() >= 5 else 1.0
    if rng.random() < (0.12 if weekend == 1 else 0.45):
        continue                                           # some days off
    tokens = 40e6 * ramp * weekend * rng.uniform(0.2, 1.6)
    history.days[day] = DayUsage(tokens=tokens, fresh=tokens * 0.05, cost=tokens / 1e6 * 0.9)
history.days[now.date()] = DayUsage(tokens=18.4e6, fresh=0.9e6, cost=16.5)

codex = CodexReading(plan="Pro 5x", windows=[Window("7d", 38, now + timedelta(days=4, hours=6))])
relays = [RelayReading("Nexus", remaining=842.50, limit=1500, used=657.50),
          RelayReading("Company", remaining=61.20, limit=100, used=38.80)]
data = {"codex": codex, "relays": relays, "ccswitch": history}

for name, rel in (("overview", relays), ("heatmap", relays), ("quota", relays[:1])):
    page = registry.PAGES[name]()
    img = page.render({**data, "relays": rel}, now)
    img.convert("L").resize((img.width * 2, img.height * 2), 0).save(out / f"{name}.png")
print("ok", sorted(p.name for p in out.iterdir()))
