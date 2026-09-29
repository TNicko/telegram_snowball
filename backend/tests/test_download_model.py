from telegram_snowball.jobs.download_model import (
    download_percent,
    fallback_expected_bytes,
    progress_fields,
)


def test_download_percent_caps_until_finished() -> None:
    assert download_percent(0, 1000) == 0
    assert download_percent(250, 1000) == 25
    assert download_percent(999, 1000) == 99
    assert download_percent(5000, 1000) == 99
    assert download_percent(10, 0) is None


def test_fallback_expected_bytes() -> None:
    assert fallback_expected_bytes(0.6) == 600_000_000
    assert fallback_expected_bytes(0) is None
    assert fallback_expected_bytes(None) is None


def test_progress_fields_include_percent() -> None:
    live = progress_fields(
        label="CLIP ViT-B/32",
        model_id="clip-vit-base-patch32",
        slot="image",
        done=120_000_000,
        total=600_000_000,
    )
    assert live["percent"] == 20
    assert live["detail"] == "Downloading weights · 20% · 114 MB / 572 MB"

    done = progress_fields(
        label="CLIP ViT-B/32",
        model_id="clip-vit-base-patch32",
        slot="image",
        done=600_000_000,
        total=600_000_000,
        finished=True,
    )
    assert done["percent"] == 100
    assert done["detail"] == "CLIP ViT-B/32 is ready"
