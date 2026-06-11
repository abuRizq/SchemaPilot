"""Adversarial regression suite — Domain 3: semantic & referential chaos
(FILE_1 §2.3)."""
from schemapilot.contracts.policy import Policy
from schemapilot.layer4_resolution.clustering import Cluster, cannot_link_pairs, chimera_veto
from schemapilot.layer4_resolution.fellegi_sunter import Decision
from schemapilot.layer4_resolution.phonetic import consonant_skeleton, name_phonetic_keys
from schemapilot.layer4_resolution.records import Record
from schemapilot.layer3_standardize.driver import Cell
from schemapilot.contracts.lineage import LineageChain


def _record(idx, system, **keys):
    cells = {}
    for concept, key in keys.items():
        concept_id = {
            "pid": "person.id", "name": "person.name.full",
        }[concept]
        cells[concept_id] = Cell(key, key, key.lower() if key else None, False,
                                 LineageChain("f", idx, concept_id))
    return Record(f"{system}:{idx}", system, "f", idx, cells, None)


class TestCrossScript:
    def test_chaos_3_1_2_cross_script_identity_converges_in_phonetic_space(self):
        """CHAOS-3.1.2: Mohammed/Muhammad/محمد reach one consonant skeleton."""
        assert consonant_skeleton("Mohammed") == consonant_skeleton("محمد") == "mhmd"
        assert consonant_skeleton("Muhammad") == "mhmd"
        assert consonant_skeleton("Al-Rashid") == consonant_skeleton("الراشد")
        assert consonant_skeleton("Khalil") == consonant_skeleton("خليل")
        assert consonant_skeleton("Fatimah") == consonant_skeleton("فاطمة")

    def test_chaos_3_1_2_blocking_keys_collide_across_scripts(self):
        latin = name_phonetic_keys("Mohammed Al-Rashid")
        arabic = name_phonetic_keys("محمد الراشد")
        assert latin & arabic, "cross-script names must share a blocking key"


class TestIdentifierUniverses:
    def test_chaos_3_3_3_same_system_distinct_ids_cannot_link(self):
        """Two records from one (presumed-deduplicated) system asserting
        different primary keys are hard cannot-link."""
        records = [
            _record(0, "crm", pid="C-1", name="Mohammed"),
            _record(1, "crm", pid="C-2", name="Mohammed"),
            _record(2, "billing", pid="B-9", name="Mohammed"),
        ]
        pairs = cannot_link_pairs(records)
        assert (0, 1) in pairs
        # Cross-system key inequality is meaningless — no constraint.
        assert (0, 2) not in pairs and (1, 2) not in pairs


class TestChimera:
    def test_chaos_3_2_7_high_entropy_cluster_is_vetoed_and_resplit(self):
        """CHAOS-3.2.7: the conflict resolver polices the entity resolver —
        a merged cluster whose members disagree on everything is re-split
        along its weakest edges (A6)."""
        policy = Policy()
        # A-B and B-C strong, A-C weak: the chained chimera shape.
        decisions = [
            Decision(0, 1, 8.0, 0.95, "auto-link"),
            Decision(1, 2, 8.0, 0.93, "auto-link"),
            Decision(0, 2, 0.5, 0.30, "clerical-review"),
        ]
        chained = Cluster("E000000", [0, 1, 2], 0.5, 0.3, 0.66)
        out = chimera_veto([chained], decisions, {"E000000": 2.5}, policy)
        assert len(out) > 1, "chimera must split"
        assert all(c.veto_split for c in out)

    def test_low_entropy_cluster_survives_veto(self):
        policy = Policy()
        decisions = [Decision(0, 1, 9.0, 0.97, "auto-link")]
        healthy = Cluster("E000000", [0, 1], 0.97, 0.97, 1.0)
        out = chimera_veto([healthy], decisions, {"E000000": 0.2}, policy)
        assert len(out) == 1 and out[0].members == [0, 1]
