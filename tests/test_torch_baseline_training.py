import numpy as np

from floodcasttw.pipelines.torch_baseline_training import masked_mse_loss
from floodcasttw.pipelines.torch_baseline_training import normalize_training_arrays
from floodcasttw.pipelines.torch_baseline_training import prepare_channels_first_arrays
from floodcasttw.pipelines.torch_baseline_training import prepare_channels_first_masks
from floodcasttw.pipelines.torch_baseline_training import repeat_training_batch


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
