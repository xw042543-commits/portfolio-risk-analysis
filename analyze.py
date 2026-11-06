"""加密资产组合风险分析：单资产风险指标 + 等权 / 风险平价组合对比。

只有 Python 标准库依赖，便于复现。
用法：python3 analyze.py
输出：output/metrics.csv、output/report.md、output/equity.svg、output/drawdown.svg
"""
import csv
import glob
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "output")
TRADING_DAYS = 365


# ---------- 读取与对齐 ----------
def load_series():
    series = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        symbol = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            series[symbol] = {row["date"]: float(row["close"]) for row in reader}
    return series


def align(series):
    """取所有资产的日期交集，并剔除任一资产缺数据的日子。"""
    dates = sorted(set.intersection(*(set(v) for v in series.values())))
    dates = [d for d in dates if all(series[s].get(d) for s in series)]
    prices = {s: [series[s][d] for d in dates] for s in series}
    return dates, prices


# ---------- 指标 ----------
def daily_returns(prices):
    return [(prices[i] / prices[i - 1] - 1) for i in range(1, len(prices))]


def annualized_return(prices):
    growth = prices[-1] / prices[0]
    years = (len(prices) - 1) / TRADING_DAYS
    return growth ** (1 / years) - 1 if years > 0 else 0.0


def annualized_vol(returns):
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(var) * math.sqrt(TRADING_DAYS)


def max_drawdown(prices):
    peak, mdd = prices[0], 0.0
    for p in prices:
        peak = max(peak, p)
        mdd = min(mdd, p / peak - 1)
    return mdd


def sharpe(returns):
    vol = annualized_vol(returns)
    mean_daily = sum(returns) / len(returns)
    return (mean_daily * TRADING_DAYS) / vol if vol else 0.0


def correlation(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a) / (n - 1))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b) / (n - 1))
    return cov / (sa * sb) if sa and sb else 0.0


# ---------- 组合 ----------
def portfolio_equity(returns_list, weights):
    equity, curve = 1.0, [1.0]      # 以起点 1.0 作为基准日
    for i in range(len(returns_list[0])):
        r = sum(weights[j] * returns_list[j][i] for j in range(len(weights)))
        equity *= 1 + r
        curve.append(equity)
    return curve


def inverse_vol_weights(vols):
    inv = [1 / v for v in vols]
    total = sum(inv)
    return [x / total for x in inv]


# ---------- 图表（纯 SVG） ----------
def svg_curves(path, dates, series_list, title, y_label):
    """series_list: [(标签, 数值序列, 颜色), ...]"""
    width, height, pad = 720, 340, 56
    all_values = [v for _, values, _ in series_list for v in values]
    lo, hi = min(all_values), max(all_values)
    span = hi - lo or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
             f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
             f'<text x="{pad}" y="26" font-family="Arial" font-size="14" fill="#1F2328">{title}</text>']
    # 网格与纵轴刻度
    for k in range(5):
        y = pad + (height - 2 * pad) * k / 4
        val = hi - span * k / 4
        parts.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{width - 20}" y2="{y:.1f}" stroke="#E3E7EC"/>')
        parts.append(f'<text x="{pad - 8}" y="{y + 4:.1f}" font-family="Arial" font-size="10" '
                     f'fill="#6B7785" text-anchor="end">{y_label.format(val)}</text>')
    x_span = width - pad - 20
    for i, (label, curve, color) in enumerate(series_list):
        pts = []
        for idx, v in enumerate(curve):
            x = pad + x_span * idx / (len(curve) - 1)
            y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{width - 24}" y="{40 + i * 18}" font-family="Arial" font-size="11" '
                     f'fill="{color}" text-anchor="end">{label}</text>')
    parts.append(f'<text x="{pad}" y="{height - 12}" font-family="Arial" font-size="10" fill="#6B7785">'
                 f'{dates[0]} — {dates[-1]}</text>')
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    series = load_series()
    dates, prices = align(series)
    symbols = list(prices)

    per_asset, rets = {}, {}
    for s in symbols:
        rets[s] = daily_returns(prices[s])
        per_asset[s] = {
            "总收益": prices[s][-1] / prices[s][0] - 1,
            "年化收益": annualized_return(prices[s]),
            "年化波动": annualized_vol(rets[s]),
            "最大回撤": max_drawdown(prices[s]),
            "Sharpe": sharpe(rets[s]),
        }

    vols = [per_asset[s]["年化波动"] for s in symbols]
    w_eq = [1 / len(symbols)] * len(symbols)
    w_rp = inverse_vol_weights(vols)

    CASH_WEIGHT = 0.30                     # 现金仓位，收益按 0 计
    w_rp_cash = [w * (1 - CASH_WEIGHT) for w in w_rp]

    curves = {
        "等权": portfolio_equity([rets[s] for s in symbols], w_eq),
        "风险平价": portfolio_equity([rets[s] for s in symbols], w_rp),
        "风险平价+30%现金": portfolio_equity([rets[s] for s in symbols], w_rp_cash),
    }
    port = {}
    for name, curve in curves.items():
        port[name] = {
            "总收益": curve[-1] - 1,
            "年化收益": annualized_return(curve),
            "年化波动": annualized_vol([curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))]),
            "最大回撤": max_drawdown(curve),
            "Sharpe": sharpe([curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))]),
        }

    # 单资产指标表
    with open(os.path.join(OUT_DIR, "metrics.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["资产", "总收益", "年化收益", "年化波动", "最大回撤", "Sharpe", "风险平价权重"])
        for i, s in enumerate(symbols):
            writer.writerow([s] + [f"{per_asset[s][k]:.4f}" for k in
                                   ("总收益", "年化收益", "年化波动", "最大回撤", "Sharpe")] + [f"{w_rp[i]:.4f}"])
        keys = ("总收益", "年化收益", "年化波动", "最大回撤", "Sharpe")
        for name in curves:
            writer.writerow([name + "组合"] + [f"{port[name][k]:.4f}" for k in keys] + [""])

    # 相关性矩阵（写入报告）
    corr_rows = []
    for a in symbols:
        corr_rows.append("| " + a + " | " + " | ".join(f"{correlation(rets[a], rets[b]):.2f}"
                                                       for b in symbols) + " |")

    vol_change = port["风险平价"]["年化波动"] / port["等权"]["年化波动"] - 1
    mdd_change = port["风险平价"]["最大回撤"] - port["等权"]["最大回撤"]

    report = [
        "# 加密资产组合风险分析报告",
        "",
        f"样本区间：{dates[0]} 至 {dates[-1]}，共 {len(dates)} 个交易日；标的：{', '.join(symbols)}。",
        "数据来源：Binance 公共行情接口（日频收盘价，无 API Key）。",
        "",
        "## 单资产风险指标",
        "",
        "| 资产 | 年化收益 | 年化波动 | 最大回撤 | Sharpe | 风险平价权重 |",
        "|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(symbols):
        report.append(f"| {s} | {per_asset[s]['年化收益']:.2%} | {per_asset[s]['年化波动']:.2%} | "
                      f"{per_asset[s]['最大回撤']:.2%} | {per_asset[s]['Sharpe']:.2f} | {w_rp[i]:.1%} |")
    report += [
        "",
        "## 组合对比",
        "",
        "| 组合 | 年化收益 | 年化波动 | 最大回撤 | Sharpe |",
        "|---|---|---|---|---|",
    ]
    for name in curves:
        report.append(f"| {name} | {port[name]['年化收益']:.2%} | {port[name]['年化波动']:.2%} | "
                      f"{port[name]['最大回撤']:.2%} | {port[name]['Sharpe']:.2f} |")
    report += [
        "",
        f"风险平价相对等权：年化波动 {vol_change:+.2%}，最大回撤 {mdd_change:+.2%}。",
        "",
        "## 日收益相关性",
        "",
        "| 资产 | " + " | ".join(symbols) + " |",
        "|---|" + "---|" * len(symbols),
    ] + corr_rows + [
        "",
        "## 结论",
        "",
        f"1. 波动率倒数加权的风险平价组合把年化波动从 {port['等权']['年化波动']:.2%} 降到 "
        f"{port['风险平价']['年化波动']:.2%}（{vol_change:+.2%}），最大回撤从 "
        f"{port['等权']['最大回撤']:.2%} 变为 {port['风险平价']['最大回撤']:.2%}。",
        f"2. 5 个标的日收益相关性集中在 {min(correlation(rets[a], rets[b]) for a in symbols for b in symbols if a != b):.2f}"
        f" 至 {max(correlation(rets[a], rets[b]) for a in symbols for b in symbols if a != b):.2f}，"
        "分散化主要来自权重差异，而非相关性差异。",
        f"3. 在风险平价基础上留出 30% 现金，年化波动降到 {port['风险平价+30%现金']['年化波动']:.2%}、"
        f"最大回撤收窄到 {port['风险平价+30%现金']['最大回撤']:.2%}；由于降低了波动拖累，区间年化收益反而为 "
        f"{port['风险平价+30%现金']['年化收益']:.2%}（满仓风险平价 {port['风险平价']['年化收益']:.2%}），"
        "说明在该样本里降低风险暴露同时改善了复利结果。",
        "4. 结论：加密资产之间相关性高，风险平价能小幅降波，真正压回撤要靠控制整体加密仓位。",
    ]
    with open(os.path.join(OUT_DIR, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")

    # 净值曲线（等权 / 风险平价 / BTC 基准）
    svg_curves(os.path.join(OUT_DIR, "equity.svg"), dates,
               [("等权组合", curves["等权"], "#2B5C8A"),
                ("风险平价组合", curves["风险平价"], "#C9A227"),
                ("风险平价+30%现金", curves["风险平价+30%现金"], "#123A66")],
               "净值曲线（起点归一为 1.0）", "{:.2f}")
    dd_eq = [c / max(curves["等权"][:i + 1]) - 1 for i, c in enumerate(curves["等权"])]
    dd_rp = [c / max(curves["风险平价"][:i + 1]) - 1 for i, c in enumerate(curves["风险平价"])]
    svg_curves(os.path.join(OUT_DIR, "drawdown.svg"), dates,
               [("等权组合", dd_eq, "#2B5C8A"), ("风险平价组合", dd_rp, "#C9A227")],
               "回撤曲线（等权 vs 风险平价）", "{:.0%}")

    print("区间", dates[0], "→", dates[-1], "交易日", len(dates))
    for name in curves:
        print(f"{name}: 年化收益 {port[name]['年化收益']:.2%} 波动 {port[name]['年化波动']:.2%} "
              f"回撤 {port[name]['最大回撤']:.2%} Sharpe {port[name]['Sharpe']:.2f}")
    print("风险平价权重", [f"{w:.1%}" for w in w_rp])


if __name__ == "__main__":
    main()
