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

## Notice Types (in history.json)
Each notice needs `fulldate` ("2026年X月X日（星期X）") and `time` for sorting and badge display.

| type | Required fields | Notes |
|------|----------------|-------|
| `coles` | date, fulldate, time | Delivery notice |
| `visit` | who, date, fulldate, time | Someone visiting |
| `trip` | destination, date, fulldate, time, note | Family trip |
| `power` | date, fulldate, time, note | Free power hour |
| `custom` | icon, label, message, fulldate, time | Any other notice |

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
- Shows weekly Coles shopping items + individual prices + total
- Cindy tells Claude what was bought → Claude updates spending.json
- **Future:** Auto-populate from weekly Coles confirmation emails (cindy_melbourne@yahoo.com via IMAP)

## Navigation Buttons (main page, bottom-right)
- 🎁 → spending.html (top)
- 📋 → reminders.html (bottom)

## Current Status
- Tablet purchased, GitHub Pages live
- All core features working: notices, word cards, day badges, bin reminder, spending page
- `^wordlist` alias working — tell Claude a word to add it to words.json

## Remaining To-Do
1. Configure tablet: kiosk mode, always-on screen, auto-start browser to live URL
2. Automate spending.json from Coles email (future)
