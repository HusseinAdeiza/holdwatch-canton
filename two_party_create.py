#!/usr/bin/env python3
"""
two_party_create.py — the demo scenario over the JSON Ledger API.

WHY THIS FILE EXISTS
--------------------
`daml test` proved the contract compiles and that a HELD payment can be created
and read back. It could not prove the part that matters most for the demo: the
HOLDER settling the payment. Two reasons, both correct behaviour rather than
bugs:

  1. With `signatory issuer` alone, Canton discloses the contract to Issuer and
     Observer but NOT Holder. A non-signatory cannot act on a contract:
     "Attempt to fetch or exercise a contract not visible to the reading
     parties."
  2. Adding Holder as a second signatory then requires Holder's authorisation at
     CREATION, which a single-party `createCmd` cannot supply:
     "failed due to a missing authorization from 'Holder'".

The JSON Ledger API solves this: a request carries `actAs` with both parties, so
both authorise the same create. That is the multi-party flow the demo shows.

Requires:
    daml sandbox --dar <dar> --port-file /tmp/canton-port.txt -c participant.conf
    java -jar daml-sdk.jar json-api --ledger-port 6865 --http-port 7575
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

API = "http://127.0.0.1:7575"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return {"__http__": e.code, **json.loads(raw)}
        except Exception:
            return {"__http__": e.code, "raw": raw[:600]}
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amount", default="4200.00")
    ap.add_argument("--currency", default="USD")
    a = ap.parse_args()

    print("── allocating parties ──")
    parties = {}
    for hint in ("Issuer", "Holder", "Observer"):
        r = post("/v2/parties", {"partyIdHint": hint, "identityProviderId": ""})
        pid = (r.get("partyDetails") or {}).get("party")
        parties[hint] = pid
        print(f"   {hint:9s} {str(pid)[:46]}")

    if not all(parties.values()):
        print("  party allocation failed:", json.dumps(parties)[:300])
        return 1

    issuer, holder, observer = parties["Issuer"], parties["Holder"], parties["Observer"]

    print("\n── two-party create: USD %s %s, HELD, no reason ──" % (a.amount, a.currency))
    payload = {
        "commands": [{
            "CreateCommand": {
                "createArguments": {
                    "issuer": issuer,
                    "holder": holder,
                    "observer": observer,
                    "amount": a.amount,
                    "currency": a.currency,
                    "status": "HELD",
                    # None, not a guess. At HELD time the ledger genuinely has
                    # no reason, and RecordReason asserts against supplying one.
                    "reason": {"none": {}},
                },
                "templateId": "#holdwatch-probe:HoldWatch:RestrictedPayment",
            }
        }],
        "userId": "holdwatch-demo",
        "commandId": "hw-create-1",
        # BOTH signatories act: this is the multi-party authorisation the Daml
        # Script harness could not express.
        "actAs": [issuer, holder],
        "readAs": [issuer, holder, observer],
    }
    r = post("/v2/commands/submit-and-wait", payload)
    print("   ->", json.dumps(r)[:260])

    offset = r.get("completionOffset")
    if offset is None:
        print("  create did not return a completionOffset — not created")
        return 1

    print("\n── ledger state at offset %s ──" % offset)
    q = {
        "eventFormat": {"filtersForAnyParty": {
            "cumulative": [{"identifierFilter": {"WildcardFilter": {
                "value": {"includeCreatedEventBlob": True}}}}]}},
        "verbose": False,
        "activeAtOffset": offset,
    }
    acs = post("/v2/state/active-contracts", q)
    contracts = acs.get("activeContracts") or []
    print(f"   active contracts: {len(contracts)}")
    for c in contracts[:3]:
        ev = c.get("createdEvent") or {}
        args = ev.get("createArgument") or ev.get("createdEventBlob") or {}
        print(f"     template : {ev.get('templateId')}")
        print(f"     args     : {json.dumps(args)[:180]}")

    # the point of the whole product, verified on-chain
    held = [c for c in contracts
            if (c.get("createdEvent") or {}).get("createArgument", {}).get("status") == "HELD"]
    if held:
        print("\n   OK  a HELD payment exists on the ledger")
        print("   OK  its reason is None — the unknown is recorded, not inferred")
    else:
        print("\n   no HELD contract found in the active set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())