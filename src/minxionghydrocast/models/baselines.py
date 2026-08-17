"""Baseline models that are useful before deep-learning training is justified."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class ArrayLike(Protocol):
    @property
    def shape(self) -> tuple[int, ...]:
        ...


@dataclass(frozen=True)
class PersistenceNowcaster:
    """Repeat the latest radar/rainfall frame for every future step."""

    horizon: int = 6

    def predict(self, frames: ArrayLike) -> np.ndarray:
        array = np.asarray(frames)
        if array.ndim < 3:
            raise ValueError("frames must be at least [time, height, width]")
        latest = array[-1]
        return np.repeat(latest[np.newaxis, ...], self.horizon, axis=0)


def _spatial_frame(frame: np.ndarray) -> np.ndarray:
    """Return the first channel used for motion estimation."""

    array = np.asarray(frame, dtype=np.float32)
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[-1] >= 1:
        return array[..., 0]
    raise ValueError("a motion frame must be [height, width] or [height, width, channels]")


def _spatial_mask(mask: np.ndarray | None, frame: np.ndarray) -> np.ndarray:
    """Normalize a frame mask to [height, width] and reject shape drift."""

    spatial = _spatial_frame(frame)
    if mask is None:
        return np.isfinite(spatial)
    array = np.asarray(mask, dtype=bool)
    if array.shape == spatial.shape:
        return array
    frame_array = np.asarray(frame)
    if frame_array.ndim == 3 and array.shape == frame_array.shape:
        return np.all(array, axis=-1)
    raise ValueError(
        f"motion mask shape {array.shape} does not match frame shape {frame_array.shape}"
    )


def _hann_window(height: int, width: int) -> np.ndarray:
    """Build a deterministic 2D Hann window, including one-pixel dimensions."""

    y_window = np.hanning(height) if height > 1 else np.ones(1, dtype=np.float32)
    x_window = np.hanning(width) if width > 1 else np.ones(1, dtype=np.float32)
    return np.outer(y_window, x_window).astype(np.float32)


def estimate_translation(
    reference: np.ndarray,
    moving: np.ndarray,
    *,
    reference_mask: np.ndarray | None = None,
    moving_mask: np.ndarray | None = None,
    max_displacement: int | None = 128,
    min_valid_pixels: int = 16,
    min_signal_std: float = 1e-6,
) -> tuple[int, int]:
    """Estimate integer ``(row, column)`` motion with FFT phase correlation.

    The returned displacement describes where ``moving`` is located relative to
    ``reference``.  Invalid pixels are excluded from the signal and the result
    is intentionally integer-valued so prediction remains deterministic without
    an interpolation dependency.
    """

    reference_array = _spatial_frame(reference)
    moving_array = _spatial_frame(moving)
    if reference_array.shape != moving_array.shape:
        raise ValueError(
            f"motion frames must have identical spatial shapes: "
            f"{reference_array.shape} != {moving_array.shape}"
        )
    if min_valid_pixels < 1:
        raise ValueError("min_valid_pixels must be at least 1")
    if min_signal_std < 0.0:
        raise ValueError("min_signal_std must be non-negative")
    if max_displacement is not None and max_displacement < 0:
        raise ValueError("max_displacement must be non-negative or None")

    reference_valid = _spatial_mask(reference_mask, reference) & np.isfinite(reference_array)
    moving_valid = _spatial_mask(moving_mask, moving) & np.isfinite(moving_array)
    overlap_count = int(np.logical_and(reference_valid, moving_valid).sum())
    if overlap_count < min_valid_pixels:
        return 0, 0
    if (
        float(np.std(reference_array[reference_valid])) <= min_signal_std
        or float(np.std(moving_array[moving_valid])) <= min_signal_std
    ):
        return 0, 0

    reference_centered = np.where(
        reference_valid,
        reference_array - float(np.mean(reference_array[reference_valid])),
        0.0,
    )
    moving_centered = np.where(
        moving_valid,
        moving_array - float(np.mean(moving_array[moving_valid])),
        0.0,
    )
    window = _hann_window(*reference_array.shape)
    reference_spectrum = np.fft.fft2(reference_centered * window)
    moving_spectrum = np.fft.fft2(moving_centered * window)
    cross_power = moving_spectrum * np.conjugate(reference_spectrum)
    magnitude = np.abs(cross_power)
    if not np.any(magnitude > 0.0):
        return 0, 0
    cross_power /= np.where(magnitude > 0.0, magnitude, 1.0)
    response = np.real(np.fft.ifft2(cross_power))

    if max_displacement is not None:
        row_indices = np.arange(response.shape[0])
        column_indices = np.arange(response.shape[1])
        signed_rows = np.where(
            row_indices <= response.shape[0] // 2,
            row_indices,
            row_indices - response.shape[0],
        )
        signed_columns = np.where(
            column_indices <= response.shape[1] // 2,
            column_indices,
            column_indices - response.shape[1],
        )
        allowed = (np.abs(signed_rows[:, None]) <= max_displacement) & (
            np.abs(signed_columns[None, :]) <= max_displacement
        )
        if not np.any(allowed):
            return 0, 0
        response = np.where(allowed, response, -np.inf)

    peak = np.unravel_index(int(np.argmax(response)), response.shape)
    row_shift = int(peak[0] if peak[0] <= response.shape[0] // 2 else peak[0] - response.shape[0])
    column_shift = int(
        peak[1] if peak[1] <= response.shape[1] // 2 else peak[1] - response.shape[1]
    )
    return row_shift, column_shift


def _translate_frame(frame: np.ndarray, *, row_shift: int, column_shift: int, fill_value: float) -> np.ndarray:
    """Translate a frame without wraparound and fill newly exposed pixels."""

    array = np.asarray(frame, dtype=np.float32)
    if array.ndim not in (2, 3):
        raise ValueError("a frame must be [height, width] or [height, width, channels]")
    height, width = array.shape[:2]
    output = np.full(array.shape, fill_value, dtype=np.float32)

    source_row_start = max(0, -row_shift)
    source_row_end = min(height, height - row_shift)
    source_column_start = max(0, -column_shift)
    source_column_end = min(width, width - column_shift)
    if source_row_start >= source_row_end or source_column_start >= source_column_end:
        return output

    target_row_start = source_row_start + row_shift
    target_row_end = source_row_end + row_shift
    target_column_start = source_column_start + column_shift
    target_column_end = source_column_end + column_shift
    source_slice = np.s_[source_row_start:source_row_end, source_column_start:source_column_end]
    target_slice = np.s_[target_row_start:target_row_end, target_column_start:target_column_end]
    output[target_slice] = array[source_slice]
    return output


@dataclass(frozen=True)
class OpticalFlowNowcaster:
    """CPU optical-flow baseline using global integer phase-correlation motion.

    The model estimates one translation per adjacent input-frame pair, takes
    the component-wise median velocity, and advects the latest frame forward.
    This is deliberately a transparent global-motion baseline, not a dense
    learned optical-flow model.
    """

    horizon: int = 6
    max_displacement: int | None = 128
    min_valid_pixels: int = 16
    min_signal_std: float = 1e-6
    fill_value: float = 0.0

    def predict(
        self,
        frames: ArrayLike,
        *,
        valid_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        array = np.asarray(frames, dtype=np.float32)
        if array.ndim not in (3, 4):
            raise ValueError(
                "frames must be [time, height, width] or [time, height, width, channels]"
            )
        if array.shape[0] < 1:
            raise ValueError("frames must contain at least one time step")
        if self.horizon < 1:
            raise ValueError("horizon must be at least 1")
        if valid_mask is None:
            mask = np.isfinite(array)
        else:
            mask = np.asarray(valid_mask, dtype=bool)
            if mask.shape not in (array.shape, array.shape[:-1] if array.ndim == 4 else ()):
                raise ValueError(
                    f"valid_mask shape {mask.shape} does not match frames shape {array.shape}"
                )

        motions = []
        for index in range(1, array.shape[0]):
            motions.append(
                estimate_translation(
                    array[index - 1],
                    array[index],
                    reference_mask=mask[index - 1],
                    moving_mask=mask[index],
                    max_displacement=self.max_displacement,
                    min_valid_pixels=self.min_valid_pixels,
                    min_signal_std=self.min_signal_std,
                )
            )
        velocity = np.median(np.asarray(motions, dtype=np.float32), axis=0) if motions else (0.0, 0.0)
        latest = array[-1]
        latest_valid = _spatial_mask(mask[-1], latest)
        if latest.ndim == 3:
            latest = np.where(latest_valid[..., np.newaxis], latest, self.fill_value)
        else:
            latest = np.where(latest_valid, latest, self.fill_value)
        predictions = [
            _translate_frame(
                latest,
                row_shift=int(np.rint(velocity[0] * lead_index)),
                column_shift=int(np.rint(velocity[1] * lead_index)),
                fill_value=self.fill_value,
            )
            for lead_index in range(1, self.horizon + 1)
        ]
        return np.stack(predictions, axis=0)


@dataclass(frozen=True)
class RainfallThresholdRiskScorer:
    """Simple flood-risk score from rainfall accumulations and local thresholds."""

    warning_1h: float
    warning_3h: float
    warning_6h: float

    def score(self, rain_1h: float, rain_3h: float, rain_6h: float) -> float:
        ratios = [
            rain_1h / self.warning_1h if self.warning_1h else 0.0,
            rain_3h / self.warning_3h if self.warning_3h else 0.0,
            rain_6h / self.warning_6h if self.warning_6h else 0.0,
        ]
        return float(max(0.0, min(1.0, max(ratios))))

    def label(self, rain_1h: float, rain_3h: float, rain_6h: float) -> str:
        score = self.score(rain_1h, rain_3h, rain_6h)
        if score >= 1.0:
            return "warning"
        if score >= 0.8:
            return "watch"
        return "normal"
