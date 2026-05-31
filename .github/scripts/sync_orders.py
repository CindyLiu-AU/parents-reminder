#!/usr/bin/env python3
"""Sync Coles and Woolworths orders from Yahoo email into spending.json.

For each order number, the LATEST confirmation email wins — this handles
order modifications which send a new email with the same order number.
"""

import imaplib, email, email.header, email.utils, re, json, os, sys
from datetime import datetime, timezone, timedelta
from math import ceil
from urllib.request import urlopen
from urllib.parse import quote
from html.parser import HTMLParser

IMAP_HOST     = "imap.mail.yahoo.com"
EMAIL_ADDR    = "cindy_melbourne@yahoo.com"
APP_PASSWORD  = os.environ.get("YAHOO_APP_PASSWORD", "")
REPO_ROOT     = os.path.join(os.path.dirname(__file__), "..", "..")
SPENDING_JSON = os.path.join(REPO_ROOT, "spending.json")

FOR_PARENTS_RULES = [
    r"30\s*pack\s*egg|egg.*30\s*pack",
    r"full\s*cream\s*milk.*3\s*l\b|3\s*l\b.*full\s*cream\s*milk",
    r"cocobella|coconut\s*yoghurt.*vanilla|vanilla.*coconut\s*yoghurt",
    r"\bplain\s*flour\b",
    r"\bloaf\b|\bbread\b",
    r"\bmince\b",
]


# ── HTML text extractor ───────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip = False
        if tag in ("td", "tr", "div", "p", "br", "li"):
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def text(self):
        raw = "".join(self.chunks)
        return re.sub(r"\n{3,}", "\n\n", raw)


def html_to_text(html):
    p = TextExtractor()
    p.feed(html)
    return p.text()


# ── Email helpers ─────────────────────────────────────────────────────────────

def decode_hdr(v):
    if not v:
        return ""
    parts = email.header.decode_header(v)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)


def get_html_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                cs = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(cs, errors="replace")
    cs = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(cs, errors="replace") if payload else ""


def msg_date(msg):
    """Return an aware datetime for an email message (UTC fallback)."""
    try:
        d = email.utils.parsedate_to_datetime(decode_hdr(msg.get("Date", "")))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


# ── Store detection ───────────────────────────────────────────────────────────

def detect_store(subject, from_addr):
    """Return ('coles'|'woolworths', order_num) or (None, None)."""
    from_l = from_addr.lower()

    # Woolworths — detected by sender; subject "Delivery order #XXXXXX - Confirmation"
    if "woolworths" in from_l:
        for pat in [
            r"[Dd]elivery order\s*#(\d+)",
            r"[Ww]oolworths.*order\s*#?(\d+)",
            r"order\s*#?(\d+).*[Cc]onfirm",
            r"#(\d{7,})",
            r"\b(\d{7,})\b",
        ]:
            m = re.search(pat, subject)
            if m:
                return "woolworths", m.group(1)

    # Coles — "Your order XXXXXXXXX has been confirmed"
    m = re.search(r"[Yy]our order (\d+) has been confirmed", subject)
    if m:
        return "coles", m.group(1)

    return None, None


# ── Coles item parser ─────────────────────────────────────────────────────────

PRICE_RE      = re.compile(r"^\$(\d+\.\d{2})$")
UNIT_PRICE_RE = re.compile(r"^\$[\d.]+\s*/")
SAVINGS_RE    = re.compile(r"\$[\d.]+ saved")
CATEGORY_RE   = re.compile(r"^.+\(\d+\)$")
SKIP_LINES    = {"Quantity", "Price", "Track order", "Track Order"}
COLES_STOP    = ["Free Delivery", "Estimated total", "You've saved", "This is our best"]


def parse_coles_items(text):
    lines    = [l.strip() for l in text.split("\n") if l.strip()]
    in_items = False
    pending  = []
    items    = []

    for line in lines:
        if any(s in line for s in COLES_STOP):
            break
        if "Order summary" in line or "Order Summary" in line:
            in_items = True
            continue
        if not in_items:
            continue
        if line in SKIP_LINES or CATEGORY_RE.match(line):
            pending = []
            continue
        if UNIT_PRICE_RE.match(line) or SAVINGS_RE.search(line):
            continue

        m = PRICE_RE.match(line)
        if m:
            amount = float(m.group(1))
            if pending and amount > 0:
                name = f"{pending[-2]} {pending[-1]}" if len(pending) >= 2 else pending[-1]
                items.append({"name_en": name.strip(), "amount": amount})
            pending = []
        else:
            pending.append(line)
            if len(pending) > 3:
                pending = pending[-3:]

    return items


# ── Woolworths item parser ────────────────────────────────────────────────────
#
# Table columns per item: name | unit_price | qty | line_total  (no $ sign)
# Example after HTML→text:
#   Sunrice Hinata Short Grain Rice
#   15.00     ← unit price  (skip, num_count=1)
#   5.00      ← qty         (skip, num_count=2)
#   75.00     ← line total  (use, num_count=3)

WW_NUMBER_RE  = re.compile(r"^(\d+(?:\.\d+)?)$")
WW_SKIP_LINES = {
    "Item description", "Unit price", "Qty", "Price",
    "Woolworths items", "Woolworths Everyday Market items", "Everyday Market items",
}
WW_STOP_RE    = re.compile(
    r"^(?:Subtotal|Delivery fee|Paper bags?|Service fees?|Total payable|Paid with|GST)",
    re.I,
)


def parse_woolworths_items(text):
    lines        = [l.strip() for l in text.split("\n") if l.strip()]
    in_items     = False
    current_name = None
    num_count    = 0
    items        = []

    for line in lines:
        if WW_STOP_RE.match(line):
            break

        if not in_items:
            if re.search(r"Your Items|Item description", line, re.I):
                in_items = True
            continue

        if line in WW_SKIP_LINES:
            continue

        m = WW_NUMBER_RE.match(line)
        if m:
            if current_name is None:
                continue
            num_count += 1
            if num_count == 3:
                amount = float(m.group(1))
                if amount > 0:
                    items.append({"name_en": current_name, "amount": amount})
                current_name = None
                num_count    = 0
        else:
            current_name = line
            num_count    = 0

    return items


# ── Shared helpers ────────────────────────────────────────────────────────────

def parse_delivery_date(text):
    m = re.search(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[,‚\s]+"
        r"(\d{1,2})\s+(\w+)\s+(\d{4})",
        text
    )
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
    except ValueError:
        return None


def week_info(d):
    week_num   = ceil(d.day / 7)
    week_str   = f"{d.year}年{d.month}月第{week_num}周"
    monday     = d - timedelta(days=d.weekday())
    week_start = monday.strftime("%Y-%m-%d")
    return week_str, week_start


def translate_en_to_zh(text):
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:200])}"
        )
        with urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
            return data[0][0][0] if data and data[0] and data[0][0] else text
    except Exception:
        return text


def is_for_parents(name_en):
    nl = name_en.lower()
    return any(re.search(p, nl) for p in FOR_PARENTS_RULES)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not APP_PASSWORD:
        print("ERROR: YAHOO_APP_PASSWORD secret not set.")
        sys.exit(1)

    with open(SPENDING_JSON, encoding="utf-8") as f:
        spending = json.load(f)

    # Index existing entries by order number for fast lookup
    existing_by_order = {
        str(e.get("orderNumber", "")): i
        for i, e in enumerate(spending)
        if e.get("orderNumber")
    }

    print("Connecting to Yahoo IMAP…")
    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    imap.login(EMAIL_ADDR, APP_PASSWORD)
    imap.select("Inbox")

    # Broad search — detect_store() filters to real orders
    uid_set = set()
    for criterion in [
        'SUBJECT "has been confirmed"',   # Coles
        'FROM "woolworths.com.au"',        # Woolworths (any subject)
        'SUBJECT "Delivery order"',        # Woolworths fallback
    ]:
        _, ids = imap.search(None, criterion)
        uid_set.update(ids[0].split())

    print(f"Found {len(uid_set)} candidate emails.")

    # Pass 1 — identify latest email per order number
    # order_emails: order_num -> (datetime, msg, store)
    order_emails = {}

    for uid in uid_set:
        _, raw   = imap.fetch(uid, "(RFC822)")
        msg       = email.message_from_bytes(raw[0][1])
        subject   = decode_hdr(msg.get("Subject", ""))
        from_addr = decode_hdr(msg.get("From", ""))

        store, order_num = detect_store(subject, from_addr)
        if not store or not order_num:
            continue

        date = msg_date(msg)
        if order_num not in order_emails or date > order_emails[order_num][0]:
            order_emails[order_num] = (date, msg, store)

    imap.logout()
    print(f"Identified {len(order_emails)} unique order(s).")

    # Pass 2 — parse latest email for each order; update or add
    new_entries  = []
    changed      = False

    for order_num, (date, msg, store) in order_emails.items():
        html = get_html_body(msg)
        text = html_to_text(html)

        delivery_date = parse_delivery_date(text)
        if not delivery_date:
            print(f"  ⚠ #{order_num} [{store}]: could not parse delivery date, skipping.")
            continue

        raw_items = parse_coles_items(text) if store == "coles" else parse_woolworths_items(text)
        if not raw_items:
            print(f"  ⚠ #{order_num} [{store}]: no items parsed, skipping.")
            continue

        print(f"  #{order_num} [{store}]: {len(raw_items)} items, translating…")
        items = []
        for item in raw_items:
            cn_name = translate_en_to_zh(item["name_en"])
            entry   = {"name": cn_name, "amount": item["amount"]}
            if is_for_parents(item["name_en"]):
                entry["forParents"] = True
            items.append(entry)

        week_str, week_start = week_info(delivery_date)
        new_data = {
            "store":        store,
            "week":         week_str,
            "weekStart":    week_start,
            "orderNumber":  order_num,
            "deliveryDate": delivery_date.strftime("%Y-%m-%d"),
            "transferred":  False,
            "items":        items,
        }

        if order_num in existing_by_order:
            idx = existing_by_order[order_num]
            old = spending[idx]
            # Preserve transferred status; replace everything else
            new_data["transferred"] = old.get("transferred", False)
            if new_data != old:
                spending[idx] = new_data
                changed = True
                print(f"    ↺ Updated (latest email supersedes previous version)")
            else:
                print(f"    — No change")
        else:
            new_entries.append(new_data)
            changed = True
            print(f"    ✓ New entry — {week_str}")

    if not changed:
        print("No changes to spending.json.")
        return

    # Prepend new entries newest-first, then existing
    new_entries.sort(key=lambda x: x["deliveryDate"], reverse=True)
    spending = new_entries + spending

    with open(SPENDING_JSON, "w", encoding="utf-8") as f:
        json.dump(spending, f, ensure_ascii=False, indent=2)

    print(f"\nDone — {len(new_entries)} new, {sum(1 for o in order_emails if o in existing_by_order)} checked for updates.")


if __name__ == "__main__":
    main()
