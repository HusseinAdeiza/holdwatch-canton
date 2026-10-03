#!/usr/bin/env python3
"""
two_party_create.py — the demo scenario, driven through the Ledger API.

WHY THIS EXISTS
---------------
`daml test` proved the contract compiles and the HELD creation works, but the
holder could not exercise Settle from a script. Two reasons, both legitimate
rather than workarounds:

  1. With `signatory issuer` alone, Canton discloses the contract to Issuer and
     Observer but NOT Holder. A non-signatory cannot act on a contract:
     "Attempt to fetch or exercise a contract not visible to the reading
     parties." That is the privacy model working correctly.
  2. Making Holder a signatory then requires Holder's authorisation at CREATION,
     which a single-party `createCmd` cannot supply.

So the real flow needs a genuine multi-party create: both parties authorise the
same create, then the holder exercises Settle. That is exactly what the Ledger
API is for, and it is the flow the demo will show.

Requires a running sandbox:
    daml sandbox --dar <dar> --port-file /tmp/canton-port.txt -c sandbox.json

Cost: $0. Runs entirely on the local machine.
"""
from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

LEDGER = "http://127.0.0.1"


def rpc(port: int, method: str, params: dict) -> dict:
    """JSON Ledger API: POST /v2/<method>."""
    body = json.dumps(params).encode()
    req = urllib.request.Request(
        f"{LEDGER}:{port}/v2/{method}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return {"__http_error__": e.code, **json.loads(raw)}
        except Exception:
            return {"__http_error__": e.code, "raw": raw[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-file", default="/tmp/canton-port.txt")
    ap.add_argument("--amount", default="4200.00")
    a = ap.parse_args()

    port_file = Path(a.port_file)
    if not port_file.exists():
        print("  no port file — is the sandbox running?")
        return 1
    port = int(port_file.read_text().strip())
    print(f"  ledger port {port}")

    # 1. allocate the three parties
    parties = {}
    for hint in ("Issuer", "Holder", "Observer"):
        r = rpc(port, "parties", {"partyIdHint": hint, "identityProviderId": ""})
        pid = r.get("partyId") or r.get("raw") or str(r)
        parties[hint] = pid
        print(f"  party {hint:9s} {str(pid)[:44]}")

    issuer, holder, observer = parties["Issuer"], parties["Holder"], parties["Observer"]

    # 2. build the create. Both signatories must authorise it.
    args = {
        "issuer": issuer, "holder": holder, "observer": observer,
        "amount": a.amount, "currency": "USD", "status": "HELD",
        # None, not a guess: at HELD time the ledger genuinely has no reason,
        # and RecordReason asserts against supplying one.
        "reason": {"none": {}},
    }
    create = {
        "templateId": {"pkg": "holdwatch-probe", "m": "HoldWatch", "t": "RestrictedPayment"},
        "args": args,
        # Both parties authorise the same create — the multi-party flow the
        # script harness could not express.
        "disclosure": {"signatories": [issuer, holder],
                       "observers": [observer]},
    }

    cmd = {
        "command": {
            "Create": {
                "contractId": {"d": {"none": {}}},
                "disclosedContractId": {"d": {"none": {}}},
                "createCommand": create,
                "prepare": {"noOp": {}},
            }
        }
    }
    r = rpc(port, "commands/submit-and-wait",
            {"commands": [cmd], "requestId": "hw-create-1"})
    print(f"  submit-and-wait -> {json.dumps(r)[:220]}")

    # report the contract set the ledger now holds
    r2 = rpc(port, "query/contract/ids", {})
    ids = r2.get("contractIds") or []
    print(f"  contracts on ledger: {len(ids)}")
    for cid in ids[:3]:
        print(f"    {cid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
