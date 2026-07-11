import numpy as np

from floodcastminxiong.pipelines.torch_baseline_evaluation import (
    channels_first_to_sequence,
    common_evaluation_mask,
    denormalize_with_metadata,
    evaluate_prediction_arrays,
    normalize_with_metadata,
    sequence_to_channels_first,
)


def test_sequence_to_channels_first_flattens_time_and_channels():
    values = np.zeros((2, 3, 4, 2), dtype=np.float32)

    converted = sequence_to_channels_first(values)

    assert converted.shape == (1, 4, 3, 4)


def test_sequence_to_channels_first_keeps_sliding_window_samples():
    values = np.zeros((2, 3, 4, 5, 1), dtype=np.float32)

    converted = sequence_to_channels_first(values)

    assert converted.shape == (2, 3, 4, 5)


def test_channels_first_to_sequence_restores_sliding_window_shape():
    target = np.zeros((2, 3, 4, 5, 1), dtype=np.float32)
    values = np.zeros((2, 3, 4, 5), dtype=np.float32)

    restored = channels_first_to_sequence(values, target)

    assert restored.shape == target.shape


def test_normalize_and_denormalize_with_metadata_masks_inputs():
    values = np.array([[[[3.0, -999.0]]]], dtype=np.float32)
    mask = np.array([[[[True, False]]]])
    metadata = {"mean": 1.0, "std": 2.0}

    normalized = normalize_with_metadata(values, mask, metadata)
    denormalized = denormalize_with_metadata(normalized, metadata)

    assert normalized[0, 0, 0, 0] == 1.0
    assert normalized[0, 0, 0, 1] == 0.0
    assert denormalized[0, 0, 0, 0] == 3.0


def test_common_evaluation_mask_requires_latest_input_and_target_valid():
    archive = {
        "input": np.array(
            [
                [[[1.0], [1.0]]],
                [[[-999.0], [2.0]]],
            ],
            dtype=np.float32,
        ),
        "target": np.array([[[[3.0], [4.0]]]], dtype=np.float32),
        "metadata": {"nodata_values": [-999.0]},
    }

    mask = common_evaluation_mask(archive)

    assert mask.tolist() == [[[[False, True]]]]


def test_common_evaluation_mask_supports_sliding_windows():
    archive = {
        "input": np.array(
            [
                [
                    [[[1.0], [1.0]]],
                    [[[-999.0], [2.0]]],
                ],
                [
                    [[[1.0], [1.0]]],
                    [[[3.0], [4.0]]],
                ],
            ],
            dtype=np.float32,
        ),
        "target": np.array(
            [
                [
                    [[[3.0], [4.0]]],
                    [[[5.0], [-999.0]]],
                ],
                [
                    [[[5.0], [6.0]]],
                    [[[7.0], [8.0]]],
                ],
            ],
            dtype=np.float32,
        ),
        "metadata": {"nodata_values": [-999.0]},
    }

    mask = common_evaluation_mask(archive)

    assert mask.shape == (2, 2, 1, 2)
    assert mask.tolist() == [
        [[[False, True]], [[False, False]]],
        [[[True, True]], [[True, True]]],
    ]


def test_evaluate_prediction_arrays_uses_masked_pixels_only():
    prediction = np.array([[[[1.0, 10.0, 100.0]]]], dtype=np.float32)
    target = np.array([[[[2.0, 10.0, 0.0]]]], dtype=np.float32)
    mask = np.array([[[[True, True, False]]]])

    result = evaluate_prediction_arrays(
        prediction=prediction,
        target=target,
        evaluation_mask=mask,
        event_threshold=5.0,
    )

    assert result["rmse"] == 0.707107
    assert result["valid_pixel_count"] == 2
    assert result["ignored_pixel_count"] == 1
    assert result["event_metrics"]["hits"] == 1
    assert result["event_metrics"]["correct_negatives"] == 1
