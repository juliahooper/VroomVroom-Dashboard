# API Design Decisions

This document records the approach for bulk vs granular uploads, versioning, security, and client/server complexity trade-offs.

---

## 1. Bulk vs granular uploads

**Current approach: granular (one snapshot per request).**

- **Endpoints:** POST /snapshots, POST /orm/snapshots, and POST /orm/upload_snapshot each accept a **single snapshot** (one device_id, one timestamp_utc, one list of metrics) and persist it in one transaction.
- **Rationale:**
  - **Simplicity:** One request = one transaction; success or failure is clear per snapshot.
  - **Traceability:** Each response (e.g. 201 with `id`) maps to one stored snapshot; no partial-success ambiguity.
  - **Client simplicity:** The collector agent and one-shot clients send one snapshot per interval or per run; no batching logic required.
  - **Error handling:** A failed upload affects one snapshot; retry is straightforward (same payload again).
- **Trade-off:** Under very high throughput, many small requests may add overhead (connection, HTTP, validation per call). A **bulk** endpoint (e.g. POST /v1/snapshots/bulk with an array of DTOs) could reduce round-trips and amortize validation, at the cost of partial-success semantics (e.g. “accepted” vs “rejected” per item) and a more complex client and server (batch transactions, per-item validation reporting).
- **Future:** If needed, add a separate bulk endpoint (e.g. POST /v1/snapshots/bulk) with a well-defined contract (e.g. 207 Multi-Status or a body listing created ids and validation errors). Keep granular uploads as the default for agents and simple clients.

---

## 2. Versioning strategy

**Current state: no URL version prefix.**

- Paths today: /snapshots, /devices, /orm/snapshots, /orm/upload_snapshot, /orm/devices. These are treated as the initial, stable surface for the PoC.
- **Recommended strategy when introducing breaking changes:**
  - **Prefix by major version:** e.g. /v1/snapshots, /v1/devices, /v1/upload_snapshot. All current routes would become /v1/... when the first “versioned” release is cut.
  - **Stability within v1:** Avoid breaking changes to request/response shape or semantics on the same path; extend with optional fields or new endpoints instead.
  - **New major version (e.g. v2):** When breaking changes are required, introduce /v2/... and keep /v1/... for a deprecation period. Document sunset and migration in release notes.
  - **Optional:** Version in header (e.g. Accept-Version: v1) instead of URL; URL versioning is chosen here for clarity and cacheability.
- **Practical next step:** When adding versioning, mount existing blueprints under a /v1 prefix (e.g. app.register_blueprint(orm_bp, url_prefix="/v1/orm")) and document “v1” in API docs. No functional change until then.

---

## 3. Security considerations

**Current: no authentication or authorization.**

- The API is intended for trusted environments (e.g. local network, PoC, dev). No API keys, tokens, or HTTPS enforcement are implemented.
- **Future / production-oriented measures:**
  - **API keys:** Support an API key in a header (e.g. X-API-Key or Authorization: Bearer <token>). Validate on each request; reject 401 if missing or invalid. Keys should be stored and compared securely (e.g. hashed); never log keys.
  - **HTTPS:** Serve only over TLS in production; redirect HTTP → HTTPS or disable HTTP. Protects payloads and headers in transit.
  - **Rate limiting:** Throttle by client IP or by API key to reduce abuse and DoS risk. Return 429 with Retry-After when exceeded.
  - **Input hardening:** Already in place: parameterized queries (no SQL injection), validation of DTO (required fields, types, timestamp format). Continue to reject invalid payloads with 400 and clear messages; avoid leaking internals.
- **Documentation:** When adding API keys, document the header name and format in this file and in the README. Keep secrets out of the repo and use environment or secret store.

---

## 4. Client complexity vs server complexity trade-offs

**Chosen: server does more; client stays simple.**

- **Validation:** Server validates all required fields and types (e.g. validate_snapshot_upload_dto). Client can send a minimal JSON body; server returns 400 with a clear message if invalid. This avoids duplicating validation logic on every client and keeps thin clients (e.g. scripts, agents) easy to write.
- **Persistence and resolution:** Server resolves device_id (string) to device row (or creates it), and metric names to metric_type ids. Client does not need to know internal PKs or to issue multiple requests (e.g. “create device then create snapshot”). One POST with device_id and metrics is enough.
- **Transactions:** Server wraps multi-step writes in a single transaction (TransactionManager or session). Client does not deal with partial writes or rollback; it only retries the same request on 5xx or network failure.
- **Pagination and filtering:** Server supports limit, offset, sort, and (for snapshots) device_id. Client can request a page and use total/limit/offset to drive UI or polling without custom aggregation logic.
- **Trade-off:** Richer server logic (validation, mapping, transactions, pagination) increases server code and responsibility but keeps clients simple and consistent. Alternative (e.g. client sends FKs, server does minimal work) would push complexity to every client and increase coupling to schema. For this PoC and for a small number of clients (agent, dashboards), the current split is preferred.

---

## Summary

| Topic | Decision |
|-------|----------|
| **Bulk vs granular** | Granular (one snapshot per request); bulk can be added later with a dedicated endpoint and clear partial-success contract. |
| **Versioning** | No prefix today; when breaking changes are needed, introduce /v1/ (or /v2/) and keep old paths during deprecation. |
| **Security** | None for PoC; plan for API key in header, HTTPS, and rate limiting for production. |
| **Client vs server** | Server handles validation, resolution, transactions, and pagination so clients stay thin and consistent. |
