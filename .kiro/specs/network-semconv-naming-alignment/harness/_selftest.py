"""Self-test for the complete-token matching rule (not part of the harness API).

Asserts the must-not-cross-match cases from rename-token-map.yaml hold, plus a
few positive matches. Run via: uv run --with pyyaml --no-project python3 _selftest.py
"""

from _common import complete_token_regex

CASES = [
    ("network.nat.ports", "network.nat.port_blocks", False),
    ("network.nat.ports", "network.nat.port.count", False),
    ("network.nat.ports", "  - name: network.nat.ports", True),
    ("network.admin_state", "network.interface.admin_state", False),
    ("network.admin_state", "ref: network.admin_state", True),
    ("network.l2.mac.entries", "network.l2.mac.entry.type", False),
    ("network.l2.mac.entries", "network.l2.mac.address", False),
    ("network.l2.mac.entries", "`network.l2.mac.entries`", True),
    ("network.interface.id", "network.interface.index", False),
    ("network.interface.id", "network.module.id", False),
    ("network.interface.id", "ref: network.interface.id", True),
    ("network.routing.routes", "network.routing.ecmp.routes", False),
    ("network.routing.routes", "network.routing.route.count", False),
    ("network.l3.adjacency.state", "network.l3.adjacency.entry.type", False),
]


def main() -> int:
    ok = True
    for tok, text, expected in CASES:
        got = bool(complete_token_regex(tok).search(text))
        flag = "OK  " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  {flag}  match({tok!r} in {text!r}) = {got} (want {expected})")
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
