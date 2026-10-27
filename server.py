#!/usr/bin/env python3
"""Mock order service for the Skill Issue experiment. See SPECIFICATION.md.

Usage: python3 server.py [--host 127.0.0.1] [--port 8080] [--expected expected.json]
"""

import argparse
import json
import os
import random
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SEED = 42
VALUE = 4217
N_ORDERS = 1480
N_CUSTOMERS = 120
PAGE_SIZE = 50
TOTAL_PAGES = 30
N_DUPLICATE_BOUNDARIES = 20
TOKEN_CALLS = 12  # authenticated calls a token is valid for
CALLS_BEFORE_RATE_LIMIT = 2  # the call after these gets a one-off 429

STATUSES = ["placed", "shipped", "cancelled", "returned"]
STATUS_WEIGHTS = [20, 50, 15, 15]
REGIONS = ["north", "south", "east", "west"]
TIERS = ["bronze", "silver", "gold", "platinum"]
OFFSET_MINUTES = [0, 0, 0, 120, -300, 330, -120, 540]
NAME_WORDS = (
    ["Northern", "Golden", "Silver", "Rapid", "Quiet", "Bright", "Iron", "Maple", "Cedar", "Blue", "Amber", "Summit"],
    ["Trading", "Logistics", "Supplies", "Foods", "Textiles", "Hardware", "Optics", "Works", "Goods", "Systems"],
)

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
SPAN_SECONDS = 181 * 86400  # 2025-01-01 to 2025-06-30 inclusive
RANGE_START = datetime(2025, 3, 1, tzinfo=timezone.utc)
RANGE_END = datetime(2025, 6, 1, tzinfo=timezone.utc)  # exclusive: through 31 May inclusive

DOCS = """\
Order service API

All responses are JSON unless noted. Requests are made to the address this service is running on.

GET /docs
    This page (plain text).

GET /value
    Returns {"value": <integer>}. No authentication.

POST /token
    Returns {"token": "<token>"}. No authentication. Send the token on authenticated
    requests in the header "Authorization: Bearer <token>".

GET /orders?page=N
    Authenticated. Lists orders, 50 per page; N starts at 1.
    Returns {"page", "total_pages", "items", "next"}. "next" is the path of the following
    page, or null on the last page.
    Each order has: id, customer_id, status, placed_at, amount_cents.
    status is one of: placed, shipped, cancelled, returned.
    placed_at is an ISO 8601 timestamp. amount_cents is an integer number of cents.

GET /customers/{id}
    Authenticated. Returns {"id", "name", "region", "tier", "discount_pct"}; 404 if the id is unknown.
    region is one of: north, south, east, west. discount_pct is a whole-number percentage.
"""


def format_time(moment):
    return moment.isoformat().replace("+00:00", "Z")


def discounted_cents(amount_cents, discount_pct):
    quotient, remainder = divmod(amount_cents * (100 - discount_pct), 100)
    return quotient + (1 if remainder >= 50 else 0)  # round half up


def build_data():
    rng = random.Random(SEED)

    customers = {}
    for i in range(1, N_CUSTOMERS + 1):
        customer_id = f"cus-{i:03d}"
        customers[customer_id] = {
            "id": customer_id,
            "name": f"{rng.choice(NAME_WORDS[0])} {rng.choice(NAME_WORDS[1])}",
            "region": rng.choice(REGIONS),
            "tier": rng.choice(TIERS),
            "discount_pct": rng.randint(0, 25),
        }

    orders = []
    for i in range(1, N_ORDERS + 1):
        placed_utc = START + timedelta(seconds=rng.randrange(SPAN_SECONDS))
        zone = timezone(timedelta(minutes=rng.choice(OFFSET_MINUTES)))
        orders.append({
            "id": f"ord-{i:04d}",
            "customer_id": f"cus-{rng.randint(1, N_CUSTOMERS):03d}",
            "status": rng.choices(STATUSES, STATUS_WEIGHTS)[0],
            "placed_at": format_time(placed_utc.astimezone(zone)),
            "amount_cents": rng.randint(500, 50000),
        })

    # Repeat the last order of page N as the first item of page N+1 at 20 of the 29 boundaries.
    duplicate_boundaries = set(rng.sample(range(1, TOTAL_PAGES), N_DUPLICATE_BOUNDARIES))
    pages, next_order = [], 0
    for page in range(1, TOTAL_PAGES + 1):
        items = []
        if (page - 1) in duplicate_boundaries:
            items.append(dict(pages[-1][-1]))
        while len(items) < PAGE_SIZE:
            items.append(orders[next_order])
            next_order += 1
        pages.append(items)
    assert next_order == N_ORDERS

    return customers, pages, expected_answers(customers, orders)


def expected_answers(customers, orders):
    by_region = {region: 0 for region in REGIONS}
    order_count = 0
    for order in orders:
        placed = datetime.fromisoformat(order["placed_at"].replace("Z", "+00:00"))
        if order["status"] == "shipped" and RANGE_START <= placed < RANGE_END:
            customer = customers[order["customer_id"]]
            by_region[customer["region"]] += discounted_cents(order["amount_cents"], customer["discount_pct"])
            order_count += 1
    return {
        "value": VALUE,
        "complex": {
            "total_cents": sum(by_region.values()),
            "order_count": order_count,
            "duplicates_skipped": N_DUPLICATE_BOUNDARIES,
            "by_region": by_region,
        },
    }


CUSTOMERS, PAGES, EXPECTED = build_data()
TOKENS = {}  # token -> {"calls": counted authenticated calls, "limited": 429 already served}
TOKEN_LOCK = threading.Lock()
TOKEN_COUNTER = 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OrderService/1.0"

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def send_body(self, status, body, content_type, headers=None):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, payload, headers=None):
        self.send_body(status, json.dumps(payload), "application/json", headers)

    def authenticate(self):
        """Return True if the call may proceed; otherwise the error response has been sent."""
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            self.send_json(401, {"error": "missing_token"})
            return False
        with TOKEN_LOCK:
            record = TOKENS.get(token.strip())
            if record is None:
                outcome = "invalid_token"
            elif record["calls"] >= TOKEN_CALLS:
                outcome = "token_expired"
            elif record["calls"] == CALLS_BEFORE_RATE_LIMIT and not record["limited"]:
                record["limited"] = True
                outcome = "rate_limited"
            else:
                record["calls"] += 1
                outcome = None
        if outcome == "rate_limited":
            self.send_json(429, {"error": "rate_limited", "retry_after": 1}, {"Retry-After": "1"})
        elif outcome:
            self.send_json(401, {"error": outcome})
        return outcome is None

    def route(self, method):
        global TOKEN_COUNTER
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)  # request bodies are ignored
        url = urlparse(self.path)
        path = url.path
        customer = re.fullmatch(r"/customers/([^/]+)", path)

        known = {"/docs": "GET", "/value": "GET", "/token": "POST", "/orders": "GET"}
        if path in known or customer:
            if method != (known.get(path) or "GET"):
                return self.send_json(405, {"error": "method_not_allowed"})
        else:
            return self.send_json(404, {"error": "not_found"})

        if path == "/docs":
            return self.send_body(200, DOCS, "text/plain; charset=utf-8")
        if path == "/value":
            return self.send_json(200, {"value": VALUE})
        if path == "/token":
            with TOKEN_LOCK:
                TOKEN_COUNTER += 1
                token = f"tok-{TOKEN_COUNTER}"
                TOKENS[token] = {"calls": 0, "limited": False}
            return self.send_json(200, {"token": token})

        if not self.authenticate():
            return
        if customer:
            record = CUSTOMERS.get(customer.group(1))
            if record is None:
                return self.send_json(404, {"error": "not_found"})
            return self.send_json(200, record)

        raw_page = parse_qs(url.query).get("page", ["1"])[0]
        if not raw_page.isdigit() or int(raw_page) < 1:
            return self.send_json(400, {"error": "invalid_page"})
        page = int(raw_page)
        if page > TOTAL_PAGES:
            return self.send_json(404, {"error": "page_not_found"})
        self.send_json(200, {
            "page": page,
            "total_pages": TOTAL_PAGES,
            "items": PAGES[page - 1],
            "next": f"/orders?page={page + 1}" if page < TOTAL_PAGES else None,
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--expected", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected.json"),
                        help="where to write the expected answers (never served)")
    args = parser.parse_args()

    with open(args.expected, "w") as f:
        json.dump(EXPECTED, f, indent=2)
        f.write("\n")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
