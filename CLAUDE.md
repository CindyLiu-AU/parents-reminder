# parents-reminder — Project Context

## Goal
Always-on display for Cindy's parents (Xuecheng Liu & Chao Chen) showing reminders, notices, and schedules in Chinese. They are not tech-savvy and should never need to touch the device.

## Hardware
- Opel Mobile 10.1" tablet ($159, Officeworks) — purchased
- On a stand, plugged in permanently, screen always on
- Kiosk/fullscreen browser mode

## Hosting
- **GitHub Pages** (free) — Cindy edits from anywhere, parents see updates instantly
- **Live URL:** https://cindyliu-au.github.io/parents-reminder
- **Local repo:** ~/Documents/parents-reminder

## Pages
| File | URL | Purpose |
|------|-----|---------|
| `index.html` | / | Main always-on display (clock, weather, notice card) |
| `reminders.html` | /reminders.html | Upcoming notices list |
| `spending.html` | /spending.html | Weekly Coles shopping summary for parents |

## Data Files
| File | Purpose |
|------|---------|
| `history.json` | Single source of truth for all notices (used by both index + reminders pages) |
| `notices.json` | Legacy — no longer used by index.html, kept for reference |
| `words.json` | English word list for afternoon word rotation |
| `spending.json` | Weekly Coles shopping items + totals |

## Aliases
- `^reminder` — work within this project context
- `^wordlist` — add a new English word to words.json for afternoon rotation
- `going to work` — add the TTS work day notice template to history.json; ask for date and time if not provided
- `push bins out` — add the bin night notice template to history.json; ask for date if not provided (skip if it's a Wednesday — already auto-hardcoded)

## Notice Types (in history.json)
Each notice needs `fulldate` ("2026年X月X日（星期X）") and `time` for sorting and badge display.

| type | Required fields | Notes |
|------|----------------|-------|
| `coles` | date, fulldate, time | Delivery notice |
| `visit` | who, date, fulldate, time | Someone visiting |
| `trip` | destination, date, fulldate, time, note | Family trip |
| `power` | date, fulldate, time, note | Free power hour |
| `custom` | icon, label, message, fulldate, time | Any other notice |

## Notice Templates

### "Going to work" — 爸妈来帮 Cindy 做 TTS 工作
Use when parents are coming to Cindy's house to help with Tasman Trophy Service jobs (Cindy pays them). Fill in `fulldate`, `time` (when they should arrive), and optionally the job description in the message.
```json
{
  "type": "custom",
  "icon": "🏆",
  "label": "X月X日 去 Cindy 家上班",
  "message": "记得X点到 Cindy 家，帮忙做 TTS 工作 💪",
  "fulldate": "2026年X月X日（星期X）",
  "time": "09:00",
  "pin_from": "08:00",
  "pin_until": "18:00"
}
```

### "Push rubbish bin out" — 垃圾桶
Use for non-Wednesday bin nights (Wednesday is auto-hardcoded in JS). Same pin window as the auto one.
```json
{
  "type": "custom",
  "icon": "🗑️",
  "label": "垃圾桶提醒",
  "message": "今晚请把垃圾桶推到路边",
  "fulldate": "2026年X月X日（星期X）",
  "time": "20:00",
  "pin_from": "20:00",
  "pin_until": "07:30"
}
```

### Pin fields (optional — locks display to this notice during window)
```json
"pin_from": "15:00",
"pin_until": "19:00"
```
Supports overnight ranges (e.g. pin_from "18:00", pin_until "08:30").

## Main Page Logic (index.html)
- **Priority 1:** Bin reminder (auto, every Wed 8pm – Thu 7:30am, no JSON needed)
- **Priority 2:** Pinned notice (notice with active pin_from/pin_until window)
- **Priority 3:** First upcoming notice from history.json (sorted by datetime ASC, past notices filtered out)
- **Afternoon (12–6pm), no notices:** Rotate English word cards every 30 min
- **Night (10pm–6am):** Goodnight message
- Refreshes every 60 seconds; manual 刷新 button bottom-left

## Day Badge
Each notice card shows a coloured pill next to the title:
- 🟢 今天 (green)
- 🟠 明天 (orange)
- 🟣 后天 / X天后 (purple)

## Recurring Logic (hardcoded in JS, no JSON needed)
- **Bin night:** Every Wednesday 8pm → Thursday 7:30am — 🗑️ "把垃圾桶推到路边"

## Spending Page (spending.html)
- Reads from `spending.json`
- All item names displayed in **Chinese** (parents read this page)
- Full order section is **collapsed by default**; tap 展开 ▼ to reveal
- Parent items (爸妈的部分) shown in gold box with transfer amount in green — always visible
- Cindy populates from Coles confirmation emails (cindy_melbourne@yahoo.com via IMAP) — Yahoo email MCP server set up at ~/claude_email_mcp/yahoo_email_server.py

### spending.json structure
```json
[
  {
    "week": "2026年4月第4周",
    "weekStart": "2026-04-20",
    "orderNumber": "256169013",
    "deliveryDate": "2026-04-12",
    "items": [
      { "name": "商品中文名", "amount": 9.30 },
      { "name": "商品中文名", "amount": 31.10, "forParents": true }
    ]
  }
]
```
- `forParents: true` marks items the parents will transfer money back for
- Items without `forParents` are Cindy's own

### Parent items rules (apply to every order)
These items are **always** `forParents: true` whenever they appear:
- 笼养鸡蛋 30个装 (30-pack eggs)
- 全脂牛奶 3L (3L milk)
- 椰子酸奶 香草味 (Cocobella Coconut Yoghurt Vanilla)
- 普通白面粉 (Coles White Plain Flour)
- 任何面包 / Loaf (any bread/loaf product)
- 任何肉末 (any mince — lamb, beef, etc.)

## Navigation Buttons (main page, bottom-right)
- 🎁 → spending.html (top)
- 📋 → reminders.html (bottom)

## Current Status
- Tablet purchased, GitHub Pages live
- All core features working: notices, word cards, day badges, bin reminder, spending page
- `^wordlist` alias working — tell Claude a word to add it to words.json
- Yahoo email MCP connected — Claude can read Coles order emails directly from cindy_melbourne@yahoo.com and populate spending.json

## Remaining To-Do
1. Configure tablet: kiosk mode, always-on screen, auto-start browser to live URL
