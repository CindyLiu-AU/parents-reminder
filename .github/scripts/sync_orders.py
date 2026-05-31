#!/usr/bin/env python3
"""Sync new Coles and Woolworths orders from Yahoo email into spending.json."""

import imaplib, email, email.header, re, json, os, sys
from datetime import datetime, timedelta
from math import ceil
from urllib.request import urlopen
from urllib.parse import quote
from html.parser import HTMLParser

IMAP_HOST     = "imap.mail.yahoo.com"
EMAIL_ADDR    = "cindy_melbourne@yahoo.com"
APP_PASSWORD  = os.environ.get("YAHOO_APP_PASSWORD", "")
REPO_ROOT     = os.path.join(os.path.dirname(__file__), "..", "..")
SPENDING_JSON = os.path.join(REPO_ROOT, "spending.json")

# forParents detection — English product name patterns (shared across both stores)
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


# ── Store detection ───────────────────────────────────────────────────────────

def detect_store(subject, from_addr):
    """Return ('coles', order_num) or ('woolworths', order_num) or (None, None)."""
    subj_l = subject.lower()
    from_l = from_addr.lower()

    # Coles
    m = re.search(r"your order (\d+) has been confirmed", subject, re.I)
    if m and "coles" in (subj_l + from_l):
        return "coles", m.group(1)
    # Coles without "coles" in subject — check from address
    if m and "coles" in from_l:
        return "coles", m.group(1)

    # Woolworths — several known subject patterns
    ww_patterns = [
        r"woolworths\s+online\s+order\s+#?(\d+)",
        r"woolworths\s+order\s+#?(\d+)",
        r"your\s+woolworths.*order\s+#?(\d+)",
        r"order\s+#?(\d+).*woolworths",
        r"your order (\d+).*confirmed",  # generic, paired with ww from-addr
    ]
    if "woolworths" in subj_l or "woolworths" in from_l:
        for pat in ww_patterns:
            m = re.search(pat, subject, re.I)
            if m:
                return "woolworths", m.group(1)
        # Try any long number in subject as fallback
        m = re.search(r"\b(\d{7,})\b", subject)
        if m:
            return "woolworths", m.group(1)

    # Coles fallback — no "coles" in subject but coles in from
    m = re.search(r"your order (\d+) has been confirmed", subject, re.I)
    if m and "coles" not in from_l and "woolworths" not in from_l:
        # Ambiguous — assume Coles (original behaviour)
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
    lines = [l.strip() for l in text.split("\n") if l.strip()]
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

WW_START   = re.compile(r"items in your order|your items|order (?:details|summary)|what you ordered", re.I)
WW_STOP    = re.compile(r"delivery fee|service fee|bag fee|total savings|you(?:'ve)? saved|order total|subtotal|estimated total", re.I)
WW_QTY_RE  = re.compile(r"^\d+\s*[×x]\s*\$|^qty\s*[:\-]?\s*\d", re.I)


def parse_woolworths_items(text):
    lines    = [l.strip() for l in text.split("\n") if l.strip()]
    in_items = False
    pending  = []
    items    = []

    for line in lines:
        if WW_STOP.search(line):
            break
        if WW_START.search(line):
            in_items = True
            continue
        if not in_items:
            continue
        # Skip quantity/unit-price lines
        if WW_QTY_RE.match(line) or UNIT_PRICE_RE.match(line):
            continue
        if SAVINGS_RE.search(line):
            continue
        if line in SKIP_LINES:
            pending = []
            continue

        m = PRICE_RE.match(line)
        if m:
            amount = float(m.group(1))
            if pending and amount > 0:
                # Woolworths tends to have clean single-line product names
                name = pending[-1]
                items.append({"name_en": name.strip(), "amount": amount})
            pending = []
        else:
            pending.append(line)
            if len(pending) > 3:
                pending = pending[-3:]

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
    known_orders = {str(e.get("orderNumber", "")) for e in spending}

    print("Connecting to Yahoo IMAP…")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    mail.login(EMAIL_ADDR, APP_PASSWORD)
    mail.select("Inbox")

    # Collect unique message UIDs from multiple searches
    uid_set = set()
    for criterion in [
        'SUBJECT "has been confirmed"',
        'FROM "woolworths.com.au"',
        'SUBJECT "Woolworths" SUBJECT "order"',
    ]:
        _, ids = mail.search(None, criterion)
        uid_set.update(ids[0].split())

    print(f"Found {len(uid_set)} candidate emails to check.")

    new_entries = []

    for uid in uid_set:
        _, data = mail.fetch(uid, "(RFC822)")
        msg       = email.message_from_bytes(data[0][1])
        subject   = decode_hdr(msg.get("Subject", ""))
        from_addr = decode_hdr(msg.get("From", ""))

        store, order_num = detect_store(subject, from_addr)
        if not store or not order_num:
            continue
        if order_num in known_orders:
            continue

        print(f"  New {store} order: #{order_num}")
        html = get_html_body(msg)
        text = html_to_text(html)

        delivery_date = parse_delivery_date(text)
        if not delivery_date:
            print(f"    ⚠ Could not parse delivery date, skipping.")
            continue

        raw_items = parse_coles_items(text) if store == "coles" else parse_woolworths_items(text)
        if not raw_items:
            print(f"    ⚠ No items parsed, skipping.")
            continue

        print(f"    Parsed {len(raw_items)} items, translating…")
        items = []
        for item in raw_items:
            cn_name = translate_en_to_zh(item["name_en"])
            entry   = {"name": cn_name, "amount": item["amount"]}
            if is_for_parents(item["name_en"]):
                entry["forParents"] = True
            items.append(entry)

        week_str, week_start = week_info(delivery_date)
        new_entries.append({
            "store":        store,
            "week":         week_str,
            "weekStart":    week_start,
            "orderNumber":  order_num,
            "deliveryDate": delivery_date.strftime("%Y-%m-%d"),
            "transferred":  False,
            "items":        items,
        })
        print(f"    ✓ [{store}] {week_str} — {len(items)} items")

    mail.logout()

    if not new_entries:
        print("No new orders found.")
        return

    new_entries.sort(key=lambda x: x["deliveryDate"], reverse=True)
    spending = new_entries + spending

    with open(SPENDING_JSON, "w", encoding="utf-8") as f:
        json.dump(spending, f, ensure_ascii=False, indent=2)

    print(f"\nDone — added {len(new_entries)} new order(s) to spending.json.")


if __name__ == "__main__":
    main()
