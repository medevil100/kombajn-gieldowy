"""Versioned, immutable parameters for technical events, setups and scenarios."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class TechnicalConfig:
    version: str = 'KI_TECHNICAL_RULES_20261106_1'
    reference_bars: int = 20
    sma_fast: int = 10
    sma_slow: int = 30
    breakout_fraction: float = .005
    bb_squeeze_ratio: float = .5
    bb_expansion_ratio: float = 1.5
    doji_fraction: float = .05
    pivot_width: int = 3
    pivot_lookback: int = 80
    pivot_min_separation: int = 6
    divergence_price_fraction: float = .005
    rsi_period: int = 14
    rsi_divergence_points: float = 5.
    obv_divergence_volume: float = .5
    closed_volume_ratio: float = 2.
    max_setups: int = 1

    def __post_init__(self):
        bounds = {'reference_bars': (5, 100), 'sma_fast': (2, 50), 'sma_slow': (3, 100),
                  'pivot_width': (2, 8), 'pivot_lookback': (30, 240), 'pivot_min_separation': (3, 30),
                  'rsi_period': (5, 30), 'max_setups': (1, 3)}
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Niepoprawny parametr techniczny: ' + key)
        for key in ('breakout_fraction', 'bb_squeeze_ratio', 'bb_expansion_ratio', 'doji_fraction',
                    'divergence_price_fraction', 'rsi_divergence_points', 'obv_divergence_volume', 'closed_volume_ratio'):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Niepoprawny parametr techniczny: ' + key)
        if (self.sma_fast >= self.sma_slow or self.bb_squeeze_ratio >= 1 or self.bb_expansion_ratio <= 1
                or self.doji_fraction >= 1 or self.breakout_fraction >= 1 or self.divergence_price_fraction >= 1
                or self.closed_volume_ratio < 1 or self.rsi_divergence_points > 100
                or self.pivot_lookback < 2*self.pivot_width + self.pivot_min_separation + 1):
            raise ValueError('Niespójna konfiguracja techniczna.')

    @property
    def identifier(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


DEFAULT_CONFIG = TechnicalConfig()
