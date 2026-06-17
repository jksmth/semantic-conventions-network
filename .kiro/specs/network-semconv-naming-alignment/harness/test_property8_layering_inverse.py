#!/usr/bin/env python3
"""Property 8 — `higher_layer` / `lower_layer` are an exact bidirectional inverse pair.

Feature: network-semconv-naming-alignment, Property 8: higher_layer and
lower_layer are an exact bidirectional inverse pair.

Validates: Requirements 8.1, 8.4.

This is the single genuinely data-instance-quantified invariant in the spec and
the only property-based test. This repo is a declarative semantic-convention
YAML registry — there is no application runtime. So this test validates the
INVARIANT that any conforming emitter must uphold for the D8 layering model
(`network.interface.higher_layer.id` ⇔ `network.interface.lower_layer.name`):

    given a fleet of interfaces each carrying a `lower_layer` name-set, the
    derived `higher_layer` name-set is the exact inverse relation, such that for
    all interfaces A, B:  B ∈ A.higher_layer  ⇔  A ∈ B.lower_layer.

The layering relation is realized here as code (`derive_higher_layer`), the form
the design (D8 / "Property-based testing (where applicable)") calls out as the
thing to exercise with randomized inputs. Hypothesis generates random *acyclic*
interface stacks — including LAG fan-out (one interface with several lower-layer
members) and multi-layer stacks (IP → VLAN → LAG → port) — and the property
asserts the bidirectional inverse holds.

Run (PBT library provisioned ephemerally, matching the harness tooling):

    uv run --with hypothesis --with pytest --no-project \
        python3 -m pytest test_property8_layering_inverse.py -v

or standalone:

    uv run --with hypothesis --no-project python3 test_property8_layering_inverse.py
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# --- The layering model under test -----------------------------------------
#
# An interface is modelled as a node identified by its `network.interface.name`.
# Each node carries a `lower_layer` set: the names of the interfaces running
# directly beneath it (D7 renamed this FK leaf to `lower_layer.name`; D8 adds the
# symmetric `higher_layer.id`, whose value is also interface *names*).
#
# `LowerLayerTopology` maps each interface name -> set of lower-layer names.
# It is the authoritative, emitter-supplied half of the pair. `higher_layer` is
# the DERIVED inverse relation.

LowerLayerTopology = dict[str, set[str]]


def derive_higher_layer(lower_layer: LowerLayerTopology) -> dict[str, set[str]]:
    """Derive the `higher_layer` relation as the exact inverse of `lower_layer`.

    B ∈ higher_layer[A]  iff  A ∈ lower_layer[B].

    Every interface present in the topology gets an entry (possibly empty, which
    models top-of-stack interfaces that omit `higher_layer` — Requirement 8.5).
    """
    higher_layer: dict[str, set[str]] = {iface: set() for iface in lower_layer}
    for upper, lowers in lower_layer.items():
        for lower in lowers:
            # `lower` runs beneath `upper`, so `upper` runs on top of `lower`.
            higher_layer.setdefault(lower, set()).add(upper)
    return higher_layer


# --- Generator: random acyclic interface stacks ----------------------------
#
# We build a DAG by ordering interfaces linearly (iface_0 .. iface_n-1) and only
# allowing a `lower_layer` edge from a higher-indexed node to a lower-indexed one
# (upper -> lower with index(upper) > index(lower)). This guarantees acyclicity
# while still admitting:
#   * LAG fan-out  — one upper node points at multiple lower members;
#   * multi-layer stacks (IP -> VLAN -> LAG -> port) — chains of depth > 2;
#   * shared lower layers — several uppers over one lower.


@st.composite
def lower_layer_topologies(draw) -> LowerLayerTopology:
    n = draw(st.integers(min_value=0, max_value=12))
    names = [f"if-{i}" for i in range(n)]

    topology: LowerLayerTopology = {name: set() for name in names}
    for upper_idx in range(n):
        # Candidate lower layers are strictly-lower-indexed interfaces, keeping
        # the relation acyclic regardless of which subset is chosen.
        candidates = names[:upper_idx]
        if not candidates:
            continue
        chosen = draw(
            st.lists(
                st.sampled_from(candidates),
                unique=True,
                max_size=len(candidates),
            )
        )
        topology[names[upper_idx]].update(chosen)
    return topology


# --- Property 8 -------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(lower_layer=lower_layer_topologies())
def test_property8_higher_lower_are_exact_inverse(lower_layer: LowerLayerTopology) -> None:
    """For all A, B: B ∈ A.higher_layer ⇔ A ∈ B.lower_layer.

    Feature: network-semconv-naming-alignment, Property 8.
    Validates: Requirements 8.1, 8.4.
    """
    higher_layer = derive_higher_layer(lower_layer)

    interfaces = set(lower_layer) | set(higher_layer)

    for a in interfaces:
        for b in interfaces:
            b_in_a_higher = b in higher_layer.get(a, set())
            a_in_b_lower = a in lower_layer.get(b, set())
            assert b_in_a_higher == a_in_b_lower, (
                f"inverse-pair violation: higher_layer[{a!r}]={higher_layer.get(a)} "
                f"lower_layer[{b!r}]={lower_layer.get(b)}; "
                f"B∈A.higher={b_in_a_higher} but A∈B.lower={a_in_b_lower}"
            )


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(lower_layer=lower_layer_topologies())
def test_property8_relations_acyclic_and_consistent(lower_layer: LowerLayerTopology) -> None:
    """Sanity companion: the derived relation references only known interfaces
    and no interface is its own layer (well-formed inverse over a DAG).

    Feature: network-semconv-naming-alignment, Property 8.
    """
    higher_layer = derive_higher_layer(lower_layer)
    known = set(lower_layer) | set(higher_layer)

    for iface, lowers in lower_layer.items():
        assert iface not in lowers, f"{iface!r} cannot be its own lower layer"
        assert lowers <= known
    for iface, uppers in higher_layer.items():
        assert iface not in uppers, f"{iface!r} cannot be its own higher layer"
        assert uppers <= known


if __name__ == "__main__":
    # Allow running without pytest: drive the @given tests directly.
    test_property8_higher_lower_are_exact_inverse()
    test_property8_relations_acyclic_and_consistent()
    print("Property 8 OK: higher_layer/lower_layer are an exact bidirectional inverse pair.")
