# Share Market Predictor — an honest experiment

Tests whether ML can predict **next-day direction (up/down)** of NSE large-caps, and measures how well it really does.
Not financial advice.

## Run
    pip install -r requirements.txt
    python run_experiment.py     # results for all stocks in the terminal
    streamlit run app.py         # dashboard

## Method
- Data: yfinance (2015 onward), stock + Nifty 50 (^NSEI)
- Features: 1/5/20-day returns, SMA gaps, RSI, MACD, Bollinger %B, volume change, 20-day volatility, Nifty return
- Look-ahead safety: each feature at day t uses data up to close of t; target is close[t+1] > close[t]
- Split by time: train before 2023, test 2023+ (never shuffled)
- Baselines: "always UP", "same as today". Models: Logistic Regression, Random Forest, XGBoost
- Backtest: hold on predicted-UP days, cash otherwise; 0.1% cost per position change; compared to buy & hold

## Result (test 2023+, 5 stocks)
Direction accuracy sits at ~48–52%, i.e. a coin flip. Models rarely beat the "always UP" baseline,
and after costs almost never beat buy-and-hold. Large-cap NSE stocks are hard to predict from price history alone.

## Ideas to extend
News sentiment, sector comparison, GARCH volatility forecasting, LSTM, walk-forward validation.
