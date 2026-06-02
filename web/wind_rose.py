"""Wind rose helpers: time-window samples, vector mean, binned distribution."""
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def empty_wind_rose_figure():
    fig = go.Figure()
    fig.update_layout(
        height=200,
        width=200,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _wind_rose_cfg(config):
    return config.get("mapping", {}).get("wind_rose", {})


def instruments_for_map_query(config):
    """Map query instruments, plus wind rose instrument when enabled."""
    instruments = list(config.get("mapping", {}).get("instruments") or [])
    wr_cfg = _wind_rose_cfg(config)
    if wr_cfg.get("show"):
        wr_inst = wr_cfg.get("instrument")
        if wr_inst and wr_inst not in instruments:
            instruments.append(wr_inst)
    return instruments


def day_cache_missing_wind(config, df):
    """True if wind rose is on but cached day data has no wind rows."""
    wr_cfg = _wind_rose_cfg(config)
    if not wr_cfg.get("show"):
        return False
    wr_inst = wr_cfg.get("instrument")
    wr_speed = wr_cfg.get("wind_speed_param")
    wr_dir = wr_cfg.get("wind_dir_param")
    if not (wr_inst and wr_speed and wr_dir):
        return False
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False
    wind_mask = (
        (df["instrument"] == wr_inst)
        & (df["parameter"].isin([wr_speed, wr_dir]))
    )
    return not wind_mask.any()


def get_wind_window_df(config, df):
    """Speed/direction pairs in the trailing window, aligned by sample_time."""
    wr_cfg = _wind_rose_cfg(config)
    wr_instrument = wr_cfg.get("instrument")
    wr_speed_param = wr_cfg.get("wind_speed_param")
    wr_dir_param = wr_cfg.get("wind_dir_param")
    if not (wr_instrument and wr_speed_param and wr_dir_param):
        return None

    ws_recs = df[
        (df["instrument"] == wr_instrument) & (df["parameter"] == wr_speed_param)
    ].sort_index()
    wd_recs = df[
        (df["instrument"] == wr_instrument) & (df["parameter"] == wr_dir_param)
    ].sort_index()
    if ws_recs.empty or wd_recs.empty:
        return None

    window_minutes = wr_cfg.get("window_minutes", 5)
    if "window_minutes" not in wr_cfg and wr_cfg.get("num_points"):
        # Legacy: approximate window from last N points (~1 Hz)
        window_minutes = max(1, int(wr_cfg["num_points"]) / 60)

    end_time = max(ws_recs.index.max(), wd_recs.index.max())
    start_time = end_time - timedelta(minutes=window_minutes)

    ws = (
        ws_recs.loc[ws_recs.index >= start_time, ["value"]]
        .rename(columns={"value": "speed"})
        .reset_index()
        .sort_values("sample_time")
    )
    wd = (
        wd_recs.loc[wd_recs.index >= start_time, ["value"]]
        .rename(columns={"value": "direction"})
        .reset_index()
        .sort_values("sample_time")
    )
    if ws.empty or wd.empty:
        return None

    tolerance_secs = wr_cfg.get("merge_tolerance_secs", 2)
    merged = pd.merge_asof(
        ws,
        wd,
        on="sample_time",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=tolerance_secs),
    )
    merged = merged.dropna(subset=["speed", "direction"])
    if merged.empty:
        return None
    return merged


def wind_vector_mean(speeds, directions_deg):
    """Meteorological vector mean (direction wind comes from)."""
    speeds = np.asarray(speeds, dtype=float)
    dirs = np.asarray(directions_deg, dtype=float)
    rad = np.deg2rad(dirs)
    u = -speeds * np.sin(rad)
    v = -speeds * np.cos(rad)
    mean_u = u.mean()
    mean_v = v.mean()
    avg_speed = float(np.hypot(mean_u, mean_v))
    if avg_speed < 1e-9:
        return 0.0, float("nan")
    avg_dir = float(np.degrees(np.arctan2(-mean_u, -mean_v)) % 360)
    return avg_speed, avg_dir


def wind_rose_bins(speeds, directions_deg, num_bins=16):
    """Per-sector sample count and mean speed. Theta = bin center degrees."""
    speeds = np.asarray(speeds, dtype=float)
    dirs = np.asarray(directions_deg, dtype=float)
    bin_width = 360.0 / num_bins
    centers = [i * bin_width for i in range(num_bins)]
    counts = np.zeros(num_bins, dtype=float)
    speed_sums = np.zeros(num_bins, dtype=float)

    for speed, d in zip(speeds, dirs):
        idx = int((d % 360 + bin_width / 2) % 360 / bin_width) % num_bins
        counts[idx] += 1
        speed_sums[idx] += speed

    mean_speeds = np.full(num_bins, np.nan)
    active = counts > 0
    mean_speeds[active] = speed_sums[active] / counts[active]
    return centers, counts, mean_speeds


def _wind_rose_layout(fig, title_text):
    fig.update_layout(
        title=dict(text=title_text, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=0, r=0, t=36, b=20),
        polar=dict(
            radialaxis=dict(
                showticklabels=False,
                ticks="",
                range=[0, 1.05],
            ),
            angularaxis=dict(
                rotation=90,
                direction="clockwise",
                tickmode="array",
                tickvals=[0, 90, 180, 270],
                ticktext=["N", "E", "S", "W"],
            ),
        ),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        width=200,
        height=200,
    )


def build_wind_rose_figure(config, df):
    wr_cfg = _wind_rose_cfg(config)
    if not wr_cfg.get("show", False):
        return None

    merged = get_wind_window_df(config, df)
    if merged is None or len(merged) < 1:
        return None

    speeds = merged["speed"].to_numpy()
    dirs = merged["direction"].to_numpy()
    window_minutes = wr_cfg.get("window_minutes", 5)
    num_bins = wr_cfg.get("num_bins", 16)
    show_mean = wr_cfg.get("show_mean_vector", True)
    calm_threshold = wr_cfg.get("calm_threshold", 0.1)

    centers, counts, mean_speeds = wind_rose_bins(speeds, dirs, num_bins)
    total = counts.sum()
    if total < 1:
        return None

    bin_width = 360.0 / num_bins
    freq = counts / total
    max_freq = float(freq.max())
    r_bins = freq / max_freq if max_freq > 0 else freq

    color_vals = np.nan_to_num(mean_speeds, nan=0.0)
    cmax = float(max(color_vals.max(), calm_threshold, 0.1))

    fig = go.Figure()
    fig.add_trace(
        go.Barpolar(
            r=r_bins,
            theta=centers,
            width=bin_width * 0.92,
            marker_color=color_vals,
            marker_colorscale="Viridis",
            marker_cmin=0,
            marker_cmax=cmax,
            opacity=0.75,
            customdata=np.column_stack([counts, mean_speeds, 100 * freq]),
            hovertemplate=(
                "Direction: %{theta:.0f}°<br>"
                "Samples: %{customdata[0]:.0f}<br>"
                "Share: %{customdata[2]:.1f}%<br>"
                "Mean speed: %{customdata[1]:.2f} m/s<extra></extra>"
            ),
            name="Distribution",
        )
    )

    avg_speed, avg_dir = wind_vector_mean(speeds, dirs)
    title = f"Wind ({window_minutes} min)"
    if show_mean and avg_speed >= calm_threshold and np.isfinite(avg_dir):
        fig.add_trace(
            go.Scatterpolar(
                r=[1.02],
                theta=[avg_dir],
                mode="markers",
                marker=dict(symbol="triangle-up", size=14, color="red"),
                hovertemplate=(
                    f"Mean: {avg_speed:.2f} m/s<br>"
                    f"From: {avg_dir:.0f}°<extra></extra>"
                ),
                name="Mean",
            )
        )
        title = f"{title}<br><sup>{avg_speed:.1f} m/s · {avg_dir:.0f}°</sup>"
    elif show_mean and avg_speed < calm_threshold:
        title = f"{title}<br><sup>Calm</sup>"

    _wind_rose_layout(fig, title)
    return fig
