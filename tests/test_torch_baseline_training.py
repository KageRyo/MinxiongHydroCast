import numpy as np

from floodcasttw.pipelines.torch_baseline_training import build_loss_weights
from floodcasttw.pipelines.torch_baseline_training import masked_mse_loss
from floodcasttw.pipelines.torch_baseline_training import normalize_training_arrays
from floodcasttw.pipelines.torch_baseline_training import prepare_channels_first_arrays
from floodcasttw.pipelines.torch_baseline_training import prepare_channels_first_masks
from floodcasttw.pipelines.torch_baseline_training import repeat_training_batch
from floodcasttw.pipelines.torch_baseline_training import training_validation_indices


def test_prepare_channels_first_arrays_flattens_time_and_channels():
    archive = {
        "input": np.zeros((3, 4, 5, 2), dtype=np.float32),
        "target": np.zeros((2, 4, 5, 2), dtype=np.float32),
    }

    model_input, model_target = prepare_channels_first_arrays(archive)

    assert model_input.shape == (1, 6, 4, 5)
    assert model_target.shape == (1, 4, 4, 5)


def test_prepare_channels_first_arrays_keeps_sliding_window_samples():
    archive = {
        "input": np.zeros((2, 3, 4, 5, 1), dtype=np.float32),
        "target": np.zeros((2, 2, 4, 5, 1), dtype=np.float32),
    }

    model_input, model_target = prepare_channels_first_arrays(archive)

    assert model_input.shape == (2, 3, 4, 5)
    assert model_target.shape == (2, 2, 4, 5)


def test_repeat_training_batch_repeats_batch_axis():
    model_input = np.zeros((1, 6, 4, 5), dtype=np.float32)
    model_target = np.zeros((1, 4, 4, 5), dtype=np.float32)

    repeated_input, repeated_target = repeat_training_batch(
        model_input,
        model_target,
        batch_repeats=2,
    )

    assert repeated_input.shape == (2, 6, 4, 5)
    assert repeated_target.shape == (2, 4, 4, 5)


def test_prepare_channels_first_masks_uses_nodata_metadata():
    archive = {
        "input": np.array([[[[1.0], [-999.0]]]], dtype=np.float32),
        "target": np.array([[[[-99.0], [2.0]]]], dtype=np.float32),
        "metadata": {"nodata_values": [-999.0, -99.0]},
    }

    input_mask, target_mask, nodata_values = prepare_channels_first_masks(archive)

    assert nodata_values == (-999.0, -99.0)
    assert input_mask.tolist() == [[[[True, False]]]]
    assert target_mask.tolist() == [[[[False, True]]]]


def test_normalize_training_arrays_masks_invalid_pixels():
    model_input = np.array([[[[1.0, -999.0]]]], dtype=np.float32)
    model_target = np.array([[[[3.0, -999.0]]]], dtype=np.float32)
    input_mask = np.array([[[[True, False]]]])
    target_mask = np.array([[[[True, False]]]])

    normalized_input, normalized_target, metadata = normalize_training_arrays(
        model_input,
        model_target,
        input_mask,
        target_mask,
    )

    assert normalized_input[0, 0, 0, 1] == 0.0
    assert normalized_target[0, 0, 0, 1] == 0.0
    assert metadata["method"] == "z_score"
    assert metadata["mean"] == 2.0
    assert metadata["std"] == 1.0
    assert metadata["input_valid_pixel_count"] == 1
    assert metadata["target_valid_pixel_count"] == 1


def test_masked_mse_loss_uses_only_valid_targets():
    prediction = np.array([1.0, 10.0, 100.0], dtype=np.float32)
    target = np.array([2.0, 10.0, -999.0], dtype=np.float32)
    mask = np.array([True, True, False])

    assert float(masked_mse_loss(prediction, target, mask)) == 0.5


def test_masked_mse_loss_applies_valid_pixel_weights():
    prediction = np.array([1.0, 10.0, 100.0], dtype=np.float32)
    target = np.array([2.0, 12.0, -999.0], dtype=np.float32)
    mask = np.array([True, True, False])
    weights = np.array([1.0, 3.0, 100.0], dtype=np.float32)

    assert float(masked_mse_loss(prediction, target, mask, weights)) == 3.25


def test_build_loss_weights_upweights_threshold_events_and_masks_invalid_pixels():
    target = np.array([[[[10.0, 35.0, 50.0, -999.0]]]], dtype=np.float32)
    mask = np.array([[[[True, True, True, False]]]])

    weights = build_loss_weights(
        target,
        mask,
        loss_function="weighted_mse",
        event_threshold=35.0,
        event_weight=4.0,
    )

    assert weights.tolist() == [[[[1.0, 4.0, 4.0, 0.0]]]]


def test_build_loss_weights_supports_threshold_focal_term():
    target = np.array([[[[35.0, 70.0]]]], dtype=np.float32)
    mask = np.array([[[[True, True]]]])

    weights = build_loss_weights(
        target,
        mask,
        loss_function="threshold_focal_mse",
        event_threshold=35.0,
        event_weight=2.0,
        focal_gamma=3.0,
    )

    assert weights.tolist() == [[[[2.0, 8.0]]]]


def test_training_validation_indices_are_deterministic_and_disjoint():
    train, validation = training_validation_indices(10, validation_fraction=0.2, seed=7)
    train_again, validation_again = training_validation_indices(
        10,
        validation_fraction=0.2,
        seed=7,
    )

    assert train == train_again
    assert validation == validation_again
    assert len(train) == 8
    assert len(validation) == 2
    assert set(train).isdisjoint(validation)
    assert sorted(train + validation) == list(range(10))
