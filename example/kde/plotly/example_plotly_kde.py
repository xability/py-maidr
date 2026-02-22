import numpy as np
import plotly.graph_objects as go
from scipy.stats import gaussian_kde

import maidr

# Generate sample data
np.random.seed(42)
data = np.concatenate([np.random.normal(0, 1, 300), np.random.normal(4, 1.5, 200)])

# Compute KDE
kde = gaussian_kde(data)
x_range = np.linspace(data.min() - 1, data.max() + 1, 200)
kde_values = kde(x_range)

# Create histogram + KDE overlay
fig = go.Figure()
fig.add_trace(go.Histogram(x=data.tolist(), nbinsx=30, histnorm="probability density",
                           name="Histogram", opacity=0.6))
fig.add_trace(go.Scatter(x=x_range.tolist(), y=kde_values.tolist(), mode="lines",
                         name="KDE", line=dict(color="red", width=2)))
fig.update_layout(title="Histogram with KDE Overlay",
                  xaxis=dict(title="Value", tickformat=".1f"),
                  yaxis=dict(title="Density", tickformat=".3f"))

maidr.show(fig)
