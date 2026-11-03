"""One look for every C7 figure: quiet axes, a faint grid, a soft palette."""

import matplotlib
from matplotlib.colors import LinearSegmentedColormap

# One colour per setting in every figure. Range is teal and k-NN amber,
# darker for larger r or k.
SETTING_COLORS = {"none": "#A6A6A6", "global": "#6A51A3", "oracle": "#444444"}
RANGE_COLOR, KNN_COLOR = "#2A9D8F", "#E09F3E"
RANGE_SHADES = LinearSegmentedColormap.from_list("range", ["#9FD8CF", "#1D6F66"])
KNN_SHADES = LinearSegmentedColormap.from_list("knn", ["#F5D49A", "#B9770E"])
RESPONSE_COLORS = {"wait": "#8DA0CB", "detour": "#66C2A5",
                   "retreat": "#F4B183", "proceed": "#D9C08C"}
QUIET_GREY = "#DADADA"
START_COLOR, GOAL_COLOR = "#2A9D8F", "#E09F3E"


def apply():
    matplotlib.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "normal",
        "axes.labelsize": 10,
        "axes.labelcolor": "#333333",
        "axes.edgecolor": "#888888",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#E6E6E6",
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "xtick.color": "#555555",
        "ytick.color": "#555555",
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 1.8,
        "lines.markersize": 6,
        "errorbar.capsize": 2.5,
        "figure.titlesize": 13,
        "figure.titleweight": "bold",
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })
