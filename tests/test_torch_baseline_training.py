import numpy as np

from floodcasttw.pipelines.torch_baseline_training import prepare_channels_first_arrays
from floodcasttw.pipelines.torch_baseline_training import repeat_training_batch


def test_prepare_channels_first_arrays_flattens_time_and_channels():
    archive = {
        "input": np.zeros((3, 4, 5, 2), dtype=np.float32),
        "target": np.zeros((2, 4, 5, 2), dtype=np.float32),
    }

    model_input, model_target = prepare_channels_first_arrays(archive)

    assert model_input.shape == (1, 6, 4, 5)
    assert model_target.shape == (1, 4, 4, 5)


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
