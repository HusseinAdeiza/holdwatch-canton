# HoldWatch for Canton — working notes

**Status: Daml toolchain proven working. The HTTP JSON Ledger API is not yet up.**

---

## What is verified (run it, don't trust me)

```
Daml SDK 2.10.6 installed at ~/.daml
Java 17 already present (openjdk 17.0.20.1)
daml build   -> .daml/dist/holdwatch-probe-0.0.1.dar  (324 KB)
daml test    -> holdwatch_test: ok, 1 active contracts, 1 transactions
daml sandbox -> listening on 6865, DAR uploaded
```

`holdwatch_test` allocates Issuer / Holder / Observer, creates a USD 4,200 payment
in `HELD` with `reason = None`, reads it back, and returns it. Cost so far: **$0**.

## The contract

```daml
template RestrictedPayment
  with
    issuer, holder, observer : Party
    amount   : Decimal
    currency : Text
    status   : Text          -- "HELD" | "SETTLED" | "RETURNED"
    reason   : Optional Text -- None = "cause not disclosed"
  where
    signatory issuer
    observer  observer

    choice Settle : ContractId RestrictedPayment
      controller holder
      do assert (status == "HELD")
         create this with status = "SETTLED"

    choice RecordReason : ContractId RestrictedPayment
      controller issuer
      do assert (status /= "HELD")     -- cannot invent a reason while HELD
         assert (reason == None)
         create this with reason = Some "resolved after review"
```

**The honesty rule lives in the contract, not the UI.** Supplying a reason for a
held payment is a failed assertion. This is stronger than the PayPal version,
where the same rule is enforced in application code that a model can be talked
around; here the ledger itself refuses.

## Open: the two-party create

`Settle` is currently unexercisable by Holder. This is **Canton privacy working
correctly against a design mistake**, not a bug to route around:

- With `signatory issuer` alone, the contract is disclosed to Issuer and Observer
  but **not Holder**. A non-signatory cannot act on a contract:
  *"Attempt to fetch or exercise a contract not visible to the reading parties."*
- Making Holder a second signatory then requires **Holder's authorisation at
  creation**, which a single-party `createCmd` cannot supply:
  *"failed due to a missing authorization from 'Holder'."*

So the holder-settles path needs a genuine two-party create. The official route is
the JSON Ledger API, which is what the Daml Script harness cannot express.

## Blocked on: the HTTP JSON Ledger API

Not running yet. What was tried, so it isn't retried blindly:

| Attempt | Result |
|---|---|
| `daml sandbox --json-api-port 7575` | flag does not exist in 2.10.6 |
| `sandbox.json` with `httpPort` | key silently ignored |
| participant conf with `ledger-api.http` | gRPC bound on 6865, HTTP never bound |
| HOCON `canton { }` wrapper in the conf | `CANNOT_PARSE_CONFIG_FILES` — the conf body must not be wrapped |
| `daml-sdk.jar json-api --port 7575` | needs `java -jar`, and the flag is `--http-port` |
| `java -jar ... json-api --http-port 7575 --ledger-port 6865` | **process runs, port never binds** — current blocker |

Next step is to read the `json-api --help` output rather than guess flags again,
then verify with `/livez` before running `two_party_create.py`.

## Daml syntax notes (cost several compiles — read these first)

Learned the hard way, recorded so it is not learned again:

- The type is **`Optional Text`**, not `Option Text`. It comes from the Prelude.
- A Daml file **must be named after its module**: `module HoldWatch` lives in
  `HoldWatch.daml`, not `Main.daml`.
- Package names **cannot contain underscores**: `^[A-Za-z][A-Za-z0-9]*(-...)*$`.
- Choice syntax: `controller` is a **sibling** of the `with` block, and bodies use
  `do` + `assert` — not `if`/`then`, and not `controller` nested in `with`.
- `fetch` is an `Update`, so it cannot be the final statement of a `Script` and
  cannot be wrapped in `submit` either (that yields a `Scenario`). Use
  `queryContractId party cid` to read a contract back, which returns a value.
- `trySubmit` lives in `Daml.Script.Internal`, needs `daml-script-lts`, and that
  makes `Daml.Script` ambiguous. Avoid unless necessary.
- The SDK ships 817 real `.daml` files under `~/.daml/sdk/2.10.6/templates/`.
  **Read those instead of guessing** — `quickstart-java/daml/Tests/Iou.daml` and
  `script-example/src/ScriptExample.daml` had every answer that guessing did not.

## Track fit

**Data, Analytics & Ecosystem Dashboards** — *"A dashboard or analytics tool using
on-chain or ecosystem data… how the data supports real ecosystem decisions."*
That is HoldWatch pointed at Canton instead of PayPal.

**Deliverables are business-shaped**, not demo-shaped: a 1-page business brief
(ICP, who pays, why Canton), a pilot plan, a GTM outline.

## Timeline

Season 4 registration closes in ~39 days. **Build does not start until Nov 12**,
submission Dec 6, Grand Final Dec 16. So there is time to learn Daml properly
rather than fight it on the deadline.

## Reproduce

```bash
export PATH="$HOME/.daml/bin:$PATH"
daml build          # -> .daml/dist/*.dar
daml test           # -> holdwatch_test: ok
daml sandbox --dar .daml/dist/*.dar --port-file /tmp/canton-port.txt -c participant.conf
```
