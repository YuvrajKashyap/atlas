from atlas.enums import ChangeKind
from atlas.similarity import (
    classify_change,
    decode_simhash,
    encode_simhash,
    hamming_distance,
    simhash64,
    simhash_bands,
)


def test_simhash_is_stable_and_supports_bands() -> None:
    fingerprint = simhash64("the quick brown fox jumps over the distributed queue")

    assert fingerprint == simhash64("THE quick brown fox jumps over the distributed queue")
    assert decode_simhash(encode_simhash(fingerprint)) == fingerprint
    assert len(simhash_bands(fingerprint)) == 4
    assert hamming_distance(fingerprint, fingerprint ^ 0b1011) == 3
    assert simhash64("") == 0
    assert simhash64("single") != 0
    assert decode_simhash(None) is None


def test_change_classification_covers_version_transitions() -> None:
    current = simhash64("stable page text for comparison")

    assert (
        classify_change(
            previous_hash=None,
            current_hash="new",
            previous_simhash=None,
            current_simhash=current,
            metadata_changed=False,
        )
        == ChangeKind.INITIAL
    )
    assert (
        classify_change(
            previous_hash="same",
            current_hash="same",
            previous_simhash=encode_simhash(current),
            current_simhash=current,
            metadata_changed=False,
        )
        == ChangeKind.UNCHANGED
    )
    assert (
        classify_change(
            previous_hash="same",
            current_hash="same",
            previous_simhash=encode_simhash(current),
            current_simhash=current,
            metadata_changed=True,
        )
        == ChangeKind.METADATA_ONLY
    )
    assert (
        classify_change(
            previous_hash="old",
            current_hash="new",
            previous_simhash=encode_simhash(current ^ 1),
            current_simhash=current,
            metadata_changed=False,
        )
        == ChangeKind.MINOR
    )
    assert (
        classify_change(
            previous_hash="old",
            current_hash="new",
            previous_simhash=encode_simhash(current ^ 0xFFFF),
            current_simhash=current,
            metadata_changed=False,
        )
        == ChangeKind.SUBSTANTIAL
    )
