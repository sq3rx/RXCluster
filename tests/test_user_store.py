import json

from rxcluster.config import UserStoreConfig
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import parse_command
from rxcluster.users.store import UserStore


def test_filter_state_round_trip():
    state = FilterState()
    parse_command("REJECT BAND ALL", state)
    parse_command("PASS BAND 20,40", state)
    parse_command("REJECT MODE FT8", state)
    parse_command("PASS MINSNR CW 10", state)
    parse_command("REJECT DECALL W3*", state)
    parse_command("REJECT BEACON", state)

    restored = FilterState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()
    # Unrestricted categories stay None; restricted-but-empty stays a set().
    assert restored.allow["mode"] is None
    assert restored.reject["band"] == set()
    assert restored.allow["band"] == {"20m", "40m"}
    assert restored.reject_patterns["decall"] == ["w3*"]
    assert restored.min_snr == {"CW": 10}
    assert restored.switches["beacon"] is False


def test_filter_state_from_dict_is_defensive():
    state = FilterState.from_dict({"allow": {"band": "nonsense"}, "min_snr": {"CW": "x"}})
    assert state.allow["band"] is None
    assert state.min_snr == {}


def test_store_round_trip(tmp_path):
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    record = UserStore.build_record("SQ9ABC", FilterState().to_dict(), grid="JO90AA")
    store.save("SQ9ABC", record)

    fresh = UserStore(UserStoreConfig(directory=str(tmp_path)))
    loaded = fresh.load("SQ9ABC")
    assert loaded is not None
    assert loaded["callsign"] == "SQ9ABC"
    assert loaded["grid"] == "JO90AA"
    assert loaded["version"] == 1


def test_store_missing_returns_none(tmp_path):
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    assert store.load("N0CALL") is None


def test_store_corrupt_file_returns_none(tmp_path):
    (tmp_path / "SQ9ABC.json").write_text("{not json", encoding="utf-8")
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    assert store.load("SQ9ABC") is None


def test_store_sanitizes_callsign(tmp_path):
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    store.save("vk9/abc", UserStore.build_record("VK9/ABC", FilterState().to_dict()))
    assert (tmp_path / "VK9-ABC.json").exists()
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())


def test_store_disabled_writes_nothing(tmp_path):
    store = UserStore(UserStoreConfig(enabled=False, directory=str(tmp_path / "nope")))
    store.save("SQ9ABC", UserStore.build_record("SQ9ABC", FilterState().to_dict()))
    assert store.load("SQ9ABC") is None
    assert not (tmp_path / "nope").exists()


def test_store_degrades_when_directory_unwritable(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    store = UserStore(UserStoreConfig(directory=str(blocker / "users")))
    assert store.enabled is False
    store.save("SQ9ABC", UserStore.build_record("SQ9ABC", FilterState().to_dict()))
    assert store.load("SQ9ABC") is None


def test_store_skips_identical_write(tmp_path):
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    record = UserStore.build_record("SQ9ABC", FilterState().to_dict())
    store.save("SQ9ABC", record)
    path = tmp_path / "SQ9ABC.json"
    first = path.read_text(encoding="utf-8")
    store.save("SQ9ABC", json.loads(first))
    assert path.read_text(encoding="utf-8") == first
