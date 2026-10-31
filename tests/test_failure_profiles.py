from compute_provisioner.worker import FAILURE_PROFILES, choose_provider_scenario


def test_failure_profile_weights_sum_to_one() -> None:
    for profile in FAILURE_PROFILES.values():
        assert sum(weight for _, weight in profile) == 1.0


def test_normal_profile_is_always_healthy() -> None:
    assert {choose_provider_scenario("normal") for _ in range(100)} == {"healthy"}


def test_explicit_scenario_bypasses_profile_selection() -> None:
    assert choose_provider_scenario("timeout") == "timeout"
