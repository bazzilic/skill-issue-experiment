# Test API specification

Mock service used by both prompts. Runs inside each container at http://localhost:8080. JSON over HTTP, read-only, deterministic: all data is generated from a fixed seed (42) at startup, so every container starts from the same state. The generator also writes `expected.json` (not served) with the correct answers.

## Endpoints

| Request | Auth | Response |
| --- | --- | --- |
| `GET /docs` | none | Plain text: endpoint list and parameters. Does not mention the quirks below. |
| `GET /value` | none | `{"value": 4217}` |
| `POST /token` | none | `{"token": "tok-<n>"}` |
| `GET /orders?page=N` | `Authorization: Bearer <token>` | `{"page": N, "total_pages": 30, "items": [...50 orders...], "next": "/orders?page=N+1"}` (`next` is `null` on the last page; pages start at 1) |
| `GET /customers/{id}` | Bearer | `{"id", "name", "region", "tier", "discount_pct"}`; `404` for an unknown id |

## Data

- **Orders:** 1,480 distinct orders, `ord-0001` to `ord-1480`. Fields: `id`, `customer_id`, `status` (`placed`, `shipped`, `cancelled`, `returned`), `placed_at` (ISO 8601, a mix of `Z` and `±hh:mm` offsets, 2025-01-01 to 2025-06-30), `amount_cents` (integer, 500 to 50,000).
- **Customers:** 120, `cus-001` to `cus-120`. `region` is `north`, `south`, `east` or `west`; `discount_pct` is an integer from 0 to 25.

## Quirks

1. **Token expiry:** a token is valid for 12 authenticated calls. The next call gets `401 {"error": "token_expired"}`. Calls answered with 401 or 429 do not count.
2. **Rate limit:** the 3rd authenticated call on each token gets `429` with `Retry-After: 1`, once. The retry succeeds.
3. **Duplicates:** 20 of the 29 page boundaries repeat the last order of page N as the first item of page N+1, with identical content. That makes 1,500 listings for 1,480 distinct orders.

## Expected answers

- `/value`: 4217.
- Complex prompt: computed by the generator from the rules in `PROMPT-complex.md` and written to `expected.json` in the same shape as `result.json`.
