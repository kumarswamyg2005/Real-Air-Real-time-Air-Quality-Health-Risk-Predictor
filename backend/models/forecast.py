"""
LSTM + Prophet forecasting pipeline.

LSTM: input = last 72 hours × 6 features → output = next 48 hours PM2.5
Prophet: univariate PM2.5 baseline per city
"""

import os
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).parent / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)

FEATURES = ["pm25", "pm10", "no2", "temperature", "humidity", "wind_speed"]
SEQ_LEN = 72
PRED_LEN = 48
HIDDEN = 128
N_LAYERS = 2
DROPOUT = 0.2
BATCH_SIZE = 32
EPOCHS = 60
LR = 1e-3
PATIENCE = 8


# ─── Dataset ──────────────────────────────────────────────────────────────────

class AQISequenceDataset(Dataset):
    def __init__(self, data: np.ndarray, seq_len: int = SEQ_LEN, pred_len: int = PRED_LEN):
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.X, self.y = [], []
        for i in range(len(data) - seq_len - pred_len + 1):
            self.X.append(data[i: i + seq_len])
            # target = PM2.5 column (index 0)
            self.y.append(data[i + seq_len: i + seq_len + pred_len, 0])
        self.X = np.array(self.X, dtype=np.float32)
        self.y = np.array(self.y, dtype=np.float32)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return torch.tensor(self.X[idx]), torch.tensor(self.y[idx])


# ─── Model ────────────────────────────────────────────────────────────────────

class LSTMForecaster(nn.Module):
    def __init__(self, input_size: int = len(FEATURES), hidden: int = HIDDEN,
                 n_layers: int = N_LAYERS, dropout: float = DROPOUT, pred_len: int = PRED_LEN):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden, n_layers, batch_first=True,
                            dropout=dropout if n_layers > 1 else 0)
        self.fc = nn.Sequential(
            nn.Linear(hidden, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, pred_len),
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])  # last time-step hidden → pred_len


# ─── Metrics ──────────────────────────────────────────────────────────────────

def mape(y_true, y_pred):
    mask = y_true != 0
    if mask.sum() == 0:
        return np.nan
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mp = mape(y_true, y_pred)
    return {"MAE": round(float(mae), 3), "RMSE": round(float(rmse), 3), "MAPE": round(float(mp), 2)}


# ─── Trainer ──────────────────────────────────────────────────────────────────

class LSTMTrainer:
    def __init__(self, city: str):
        self.city = city
        self.scaler = MinMaxScaler()
        self.model: Optional[LSTMForecaster] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _ckpt_path(self, suffix=""):
        safe = self.city.lower().replace(" ", "_")
        return CHECKPOINT_DIR / f"lstm_{safe}{suffix}.pt"

    def _scaler_path(self):
        safe = self.city.lower().replace(" ", "_")
        return CHECKPOINT_DIR / f"scaler_{safe}.pkl"

    def prepare(self, df: pd.DataFrame):
        df = df[FEATURES].copy()
        df = df.ffill().bfill()
        # drop rows where all features are still NaN
        df = df.dropna()
        if len(df) < SEQ_LEN + PRED_LEN + 10:
            raise ValueError(f"Not enough data for {self.city}: {len(df)} rows")
        scaled = self.scaler.fit_transform(df.values)
        return scaled

    def train(self, df: pd.DataFrame) -> dict:
        scaled = self.prepare(df)
        n = len(scaled)
        split = int(n * 0.8)
        train_ds = AQISequenceDataset(scaled[:split])
        test_ds = AQISequenceDataset(scaled[split:])

        if len(train_ds) == 0 or len(test_ds) == 0:
            raise ValueError(f"Dataset too small for {self.city}")

        train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
        test_dl = DataLoader(test_ds, batch_size=BATCH_SIZE)

        self.model = LSTMForecaster().to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=LR)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=3, factor=0.5)
        criterion = nn.HuberLoss()

        best_val, patience_ctr = float("inf"), 0
        for epoch in range(1, EPOCHS + 1):
            self.model.train()
            for xb, yb in train_dl:
                xb, yb = xb.to(self.device), yb.to(self.device)
                opt.zero_grad()
                loss = criterion(self.model(xb), yb)
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()

            val_loss = 0.0
            self.model.eval()
            with torch.no_grad():
                for xb, yb in test_dl:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    val_loss += criterion(self.model(xb), yb).item()
            val_loss /= len(test_dl)
            scheduler.step(val_loss)

            if val_loss < best_val:
                best_val = val_loss
                torch.save(self.model.state_dict(), self._ckpt_path("_best"))
                patience_ctr = 0
            else:
                patience_ctr += 1
                if patience_ctr >= PATIENCE:
                    logger.info(f"{self.city}: early stop at epoch {epoch}")
                    break

        # save final + scaler
        torch.save(self.model.state_dict(), self._ckpt_path())
        with open(self._scaler_path(), "wb") as f:
            pickle.dump(self.scaler, f)

        # evaluate on test set
        self.model.load_state_dict(torch.load(self._ckpt_path("_best"), map_location=self.device))
        preds, targets = [], []
        self.model.eval()
        with torch.no_grad():
            for xb, yb in test_dl:
                xb = xb.to(self.device)
                out = self.model(xb).cpu().numpy()
                preds.append(out)
                targets.append(yb.numpy())
        preds = np.concatenate(preds)
        targets = np.concatenate(targets)

        # inverse transform PM2.5 only
        dummy = np.zeros((preds.shape[0] * PRED_LEN, len(FEATURES)))
        dummy[:, 0] = preds.flatten()
        pm25_pred = self.scaler.inverse_transform(dummy)[:, 0].reshape(-1, PRED_LEN)
        dummy[:, 0] = targets.flatten()
        pm25_true = self.scaler.inverse_transform(dummy)[:, 0].reshape(-1, PRED_LEN)

        metrics = evaluate(pm25_true.flatten(), pm25_pred.flatten())
        logger.info(f"{self.city} LSTM metrics: {metrics}")
        return metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Return next PRED_LEN PM2.5 predictions (µg/m³)."""
        ckpt = self._ckpt_path("_best")
        scaler_path = self._scaler_path()
        if not ckpt.exists() or not scaler_path.exists():
            raise FileNotFoundError(f"No saved model for {self.city}")

        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)

        if self.model is None:
            self.model = LSTMForecaster().to(self.device)
        self.model.load_state_dict(torch.load(ckpt, map_location=self.device))
        self.model.eval()

        recent = df[FEATURES].copy().ffill().bfill().dropna()
        if len(recent) < SEQ_LEN:
            # pad with last known value
            pad = pd.DataFrame([recent.iloc[-1]] * (SEQ_LEN - len(recent)), columns=FEATURES)
            recent = pd.concat([pad, recent], ignore_index=True)
        recent = recent.iloc[-SEQ_LEN:]

        scaled = self.scaler.transform(recent.values)
        x = torch.tensor(scaled[np.newaxis, :, :], dtype=torch.float32).to(self.device)
        with torch.no_grad():
            out = self.model(x).cpu().numpy().flatten()

        dummy = np.zeros((PRED_LEN, len(FEATURES)))
        dummy[:, 0] = out
        pm25 = self.scaler.inverse_transform(dummy)[:, 0]
        return np.clip(pm25, 0, None)


# ─── Prophet trainer ──────────────────────────────────────────────────────────

class ProphetTrainer:
    def __init__(self, city: str):
        self.city = city

    def _model_path(self):
        safe = self.city.lower().replace(" ", "_")
        return CHECKPOINT_DIR / f"prophet_{safe}.pkl"

    def train(self, df: pd.DataFrame) -> dict:
        try:
            from prophet import Prophet  # type: ignore
        except ImportError:
            raise ImportError("Install prophet: pip install prophet")

        series = df[["timestamp", "pm25"]].rename(columns={"timestamp": "ds", "pm25": "y"})
        series = series.dropna()
        series["ds"] = pd.to_datetime(series["ds"]).dt.tz_localize(None)
        if len(series) < 48:
            raise ValueError("Not enough data for Prophet")

        split = int(len(series) * 0.8)
        train_df, test_df = series.iloc[:split], series.iloc[split:]

        model = Prophet(
            seasonality_mode="multiplicative",
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,
        )
        model.fit(train_df)

        with open(self._model_path(), "wb") as f:
            pickle.dump(model, f)

        future = model.make_future_dataframe(periods=len(test_df), freq="h")
        forecast = model.predict(future)
        y_pred = forecast["yhat"].iloc[-len(test_df):].values
        y_true = test_df["y"].values
        y_pred = np.clip(y_pred, 0, None)

        metrics = evaluate(y_true, y_pred)
        logger.info(f"{self.city} Prophet metrics: {metrics}")
        return metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        try:
            from prophet import Prophet  # type: ignore
        except ImportError:
            raise ImportError("Install prophet")

        path = self._model_path()
        if not path.exists():
            raise FileNotFoundError(f"No saved Prophet model for {self.city}")

        with open(path, "rb") as f:
            model = pickle.load(f)

        last_ts = pd.to_datetime(df["timestamp"].max()).tz_localize(None)
        future = pd.DataFrame({"ds": pd.date_range(last_ts, periods=PRED_LEN + 1, freq="h")[1:]})
        forecast = model.predict(future)
        return np.clip(forecast["yhat"].values, 0, None)


# ─── Convenience ──────────────────────────────────────────────────────────────

def has_model(city: str) -> bool:
    safe = city.lower().replace(" ", "_")
    return (CHECKPOINT_DIR / f"lstm_{safe}_best.pt").exists()
